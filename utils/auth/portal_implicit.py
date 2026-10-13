"""Power Pages OAuth implicit-grant ID token validation for Helper login."""

from __future__ import annotations

import logging
import os
import secrets
import threading
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import jwt
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from utils.auth.google_oidc import auth_mode

logger = logging.getLogger(__name__)

PUBLIC_KEY_TTL_SECONDS = 3600
PUBLIC_KEY_PATH = "/_services/auth/publickey"
TOKEN_PATH = "/_services/auth/token"
DEFAULT_BRIDGE_PATH = "/afrp-helper-auth"

# Power Pages limits state/nonce to 20 characters.
PORTAL_OAUTH_RANDOM_BYTES = 10

# Allowed clock skew between portal and Helper when checking token issue time.
ISSUED_AT_SKEW_SECONDS = 120

_cached_public_key_pem: Optional[str] = None
_cached_public_key_at: float = 0.0

# Power Pages omits the nonce claim, so accepted tokens are remembered until
# they expire to stop a captured token being replayed.
_used_tokens: Dict[str, float] = {}
_used_tokens_lock = threading.Lock()


class PortalTokenError(Exception):
    """Raised when a portal ID token cannot be validated."""


def portal_login_enabled() -> bool:
    return auth_mode() in ("portal", "hybrid") and bool(portal_client_id())


def portal_base_url() -> str:
    raw = (os.getenv("PORTAL_BASE_URL") or "https://my.afrp.org").strip()
    return raw.rstrip("/")


def portal_client_id() -> str:
    return (os.getenv("PORTAL_OAUTH_CLIENT_ID") or "").strip()


def portal_redirect_uri(fallback: str) -> str:
    configured = (os.getenv("PORTAL_OAUTH_REDIRECT_URI") or "").strip()
    return configured or fallback


def portal_issuer() -> str:
    configured = (os.getenv("PORTAL_OAUTH_ISSUER") or "").strip()
    return configured.rstrip("/") if configured else portal_base_url()


def new_portal_state() -> str:
    return secrets.token_hex(PORTAL_OAUTH_RANDOM_BYTES)


def new_portal_nonce() -> str:
    return secrets.token_hex(PORTAL_OAUTH_RANDOM_BYTES)


def portal_callback_state_ok(provided: Optional[str], expected: Optional[str]) -> bool:
    """True only when both values are present and match (timing-safe)."""
    got = (provided or "").strip()
    want = (expected or "").strip()
    if not got or not want or len(got) != len(want):
        return False
    return secrets.compare_digest(got, want)


def portal_bridge_path() -> str:
    """Path on my.afrp.org that POSTs to the token endpoint (see power_pages/ bridge HTML)."""
    path = (os.getenv("PORTAL_AUTH_BRIDGE_PATH") or DEFAULT_BRIDGE_PATH).strip()
    if not path.startswith("/"):
        path = f"/{path}"
    return path


def build_portal_bridge_url(redirect_uri: str, state: str, nonce: str) -> str:
    """Open the portal bridge page, which POSTs to /_services/auth/token (GET returns 404)."""
    client_id = portal_client_id()
    if not client_id:
        raise PortalTokenError("Portal sign-in is not configured")

    query = urlencode(
        {
            "client_id": client_id,
            "response_type": "token",
            "state": state,
            "nonce": nonce,
            "redirect_uri": redirect_uri,
        }
    )
    return f"{portal_base_url()}{portal_bridge_path()}?{query}"


def build_portal_signin_url(redirect_uri: str, state: str, nonce: str) -> str:
    """Alias for build_portal_bridge_url (legacy name)."""
    return build_portal_bridge_url(redirect_uri, state, nonce)


def _public_key_url() -> str:
    return f"{portal_base_url()}{PUBLIC_KEY_PATH}"


def fetch_public_key_pem(force_refresh: bool = False) -> str:
    global _cached_public_key_pem, _cached_public_key_at
    now = time.time()
    if (
        not force_refresh
        and _cached_public_key_pem
        and (now - _cached_public_key_at) < PUBLIC_KEY_TTL_SECONDS
    ):
        return _cached_public_key_pem

    response = requests.get(_public_key_url(), timeout=20)
    if response.status_code != 200:
        raise PortalTokenError("Could not load portal public signing key")
    pem = (response.text or "").strip()
    if "BEGIN PUBLIC KEY" not in pem:
        raise PortalTokenError("Portal public key response was invalid")
    _cached_public_key_pem = pem
    _cached_public_key_at = now
    return pem


def _load_signing_key(pem: str):
    return serialization.load_pem_public_key(pem.encode("utf-8"))


def _normalize_issuer(value: str) -> str:
    """Power Pages emits a bare host (``my.afrp.org``) as ``iss``; compare hosts only."""
    normalized = (value or "").strip().rstrip("/").lower()
    for prefix in ("https://", "http://"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
    return normalized


def _audience_matches(payload: Dict[str, Any], client_id: str) -> bool:
    aud = payload.get("aud") or payload.get("appid")
    if aud is None:
        return False
    if isinstance(aud, list):
        return client_id in aud
    return str(aud) == client_id


def _email_from_claims(payload: Dict[str, Any]) -> str:
    candidates = (
        payload.get("email"),
        payload.get("preferred_username"),
        payload.get("upn"),
        payload.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"),
    )
    for value in candidates:
        if value:
            normalized = str(value).strip().lower()
            if "@" in normalized:
                return normalized
    return ""


def verify_portal_id_token(
    id_token: str,
    *,
    expected_state: Optional[str] = None,
    expected_nonce: Optional[str] = None,
    issued_after: Optional[float] = None,
    public_key_pem: Optional[str] = None,
) -> Dict[str, str]:
    """Validate portal JWT signature, issuer, audience, freshness, and one-time use."""
    token = (id_token or "").strip()
    if not token:
        raise PortalTokenError("Missing ID token")

    client_id = portal_client_id()
    if not client_id:
        raise PortalTokenError("Portal sign-in is not configured")

    pem = public_key_pem or fetch_public_key_pem()
    key = _load_signing_key(pem)
    try:
        payload = jwt.decode(
            token,
            key=key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as exc:
        raise PortalTokenError("Portal ID token was rejected") from exc

    issuer = _normalize_issuer(str(payload.get("iss") or ""))
    allowed = _normalize_issuer(portal_issuer())
    base = _normalize_issuer(portal_base_url())
    if issuer not in (allowed, base):
        raise PortalTokenError("Portal ID token issuer mismatch")

    if not _audience_matches(payload, client_id):
        raise PortalTokenError("Portal ID token audience mismatch")

    token_nonce = payload.get("nonce")
    if token_nonce is not None and expected_nonce is not None:
        if str(token_nonce) != expected_nonce:
            raise PortalTokenError("Portal ID token nonce mismatch")

    if issued_after is not None:
        try:
            issued_at = float(payload.get("iat"))
        except (TypeError, ValueError):
            raise PortalTokenError("Portal ID token is missing iat")
        if issued_at < issued_after - ISSUED_AT_SKEW_SECONDS:
            raise PortalTokenError("Portal ID token was issued before this sign-in started")

    _claim_one_time_use(token, payload)

    if expected_state is not None:
        token_state = str(payload.get("state") or "")
        if token_state and token_state != expected_state:
            raise PortalTokenError("Portal ID token state mismatch")

    email = _email_from_claims(payload)
    if not email:
        raise PortalTokenError("Portal ID token is missing an email claim")

    contact_id = (
        payload.get("contactid")
        or payload.get("ContactId")
        or payload.get("http://schemas.microsoft.com/crm/2011/claims/contactid")
    )
    return {
        "email": email,
        "contact_id": str(contact_id or "").strip(),
        "sub": str(payload.get("sub") or payload.get("nameid") or "").strip(),
    }


def _claim_one_time_use(token: str, payload: Dict[str, Any]) -> None:
    import hashlib

    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = time.time()
    try:
        expires = float(payload.get("exp"))
    except (TypeError, ValueError):
        expires = now + 3600
    with _used_tokens_lock:
        for key in [k for k, exp in _used_tokens.items() if exp < now]:
            _used_tokens.pop(key, None)
        if digest in _used_tokens:
            raise PortalTokenError("Portal ID token was already used")
        _used_tokens[digest] = expires


def reset_used_tokens() -> None:
    with _used_tokens_lock:
        _used_tokens.clear()


def reset_public_key_cache() -> None:
    global _cached_public_key_pem, _cached_public_key_at
    _cached_public_key_pem = None
    _cached_public_key_at = 0.0
