"""Google OpenID Connect login for AFRP CRM Helper."""

import os
import secrets
from typing import Dict
from urllib.parse import urlencode

import requests

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


class GoogleOidcError(Exception):
    """Raised when Google sign-in cannot be completed."""


def auth_mode() -> str:
    mode = (os.getenv("AUTH_MODE") or "hybrid").strip().lower()
    if mode not in ("local", "google", "portal", "hybrid"):
        return "hybrid"
    return mode


def google_login_enabled() -> bool:
    return auth_mode() in ("google", "hybrid") and bool(google_client_id())


def local_login_enabled() -> bool:
    return auth_mode() in ("local", "hybrid")


def google_client_id() -> str:
    return (os.getenv("GOOGLE_CLIENT_ID") or "").strip()


def google_client_secret() -> str:
    return (os.getenv("GOOGLE_CLIENT_SECRET") or "").strip()


def google_redirect_uri(fallback: str) -> str:
    configured = (os.getenv("GOOGLE_OIDC_REDIRECT_URI") or "").strip()
    return configured or fallback


def new_oauth_state() -> str:
    return secrets.token_urlsafe(32)


def build_authorize_url(redirect_uri: str, state: str) -> str:
    client_id = google_client_id()
    if not client_id or not google_client_secret():
        raise GoogleOidcError("Google sign-in is not configured")
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        }
    )
    return f"{GOOGLE_AUTH_URL}?{query}"


def exchange_code(code: str, redirect_uri: str) -> Dict[str, str]:
    """Exchange an authorization code and return verified email, sub, and name."""
    if not code:
        raise GoogleOidcError("Missing authorization code")
    response = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": google_client_id(),
            "client_secret": google_client_secret(),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    if response.status_code != 200:
        raise GoogleOidcError("Google token exchange failed")
    id_token = (response.json() or {}).get("id_token")
    if not id_token:
        raise GoogleOidcError("Google did not return an ID token")
    return verify_id_token(id_token)


def verify_id_token(id_token: str) -> Dict[str, str]:
    """Validate an ID token with Google's tokeninfo endpoint."""
    response = requests.get(
        GOOGLE_TOKENINFO_URL,
        params={"id_token": id_token},
        timeout=20,
    )
    if response.status_code != 200:
        raise GoogleOidcError("Google ID token was rejected")
    payload = response.json() or {}
    audience = payload.get("aud")
    if audience != google_client_id():
        raise GoogleOidcError("Google ID token audience mismatch")
    issuer = payload.get("iss")
    if issuer not in ("accounts.google.com", "https://accounts.google.com"):
        raise GoogleOidcError("Google ID token issuer mismatch")
    if str(payload.get("email_verified")).lower() not in ("true", "1"):
        raise GoogleOidcError("Google email is not verified")
    email = (payload.get("email") or "").strip().lower()
    subject = (payload.get("sub") or "").strip()
    if not email or not subject:
        raise GoogleOidcError("Google ID token is missing email or subject")
    return {
        "email": email,
        "sub": subject,
        "name": (payload.get("name") or "").strip(),
    }
