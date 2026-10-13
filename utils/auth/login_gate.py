"""Whitelist and optional Dynamics checks for Google sign-in."""

import logging
import os

logger = logging.getLogger(__name__)

DENIED_MESSAGE = "This account is not authorized for AFRP CRM Helper."


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def crm_login_gate_enabled() -> bool:
    return _env_flag("CRM_LOGIN_GATE_ENABLED", False)


def crm_login_fail_open() -> bool:
    return _env_flag("CRM_LOGIN_GATE_FAIL_OPEN", False)


def _odata_quote(value: str) -> str:
    return value.replace("'", "''")


def resolve_user_for_portal(email: str):
    """Return the whitelisted active user for this portal email, or None."""
    from utils.magazine.scheduler import User

    normalized = (email or "").strip().lower()
    if not normalized:
        return None

    matches = User.query.filter(User.email.isnot(None)).all()
    user = next(
        (row for row in matches if (row.email or "").strip().lower() == normalized),
        None,
    )
    if user is None or not user.is_active:
        return None
    return user


def resolve_user_for_google(email: str, google_sub: str):
    """Return the whitelisted active user for this Google identity, or None."""
    from utils.magazine.scheduler import User

    normalized = (email or "").strip().lower()
    subject = (google_sub or "").strip()
    if not normalized or not subject:
        return None

    linked = User.query.filter_by(google_sub=subject).first()
    if linked is not None:
        if not linked.is_active:
            return None
        if (linked.email or "").strip().lower() != normalized:
            return None
        return linked

    matches = User.query.filter(User.email.isnot(None)).all()
    user = next(
        (row for row in matches if (row.email or "").strip().lower() == normalized),
        None,
    )
    if user is None or not user.is_active:
        return None
    if user.google_sub and user.google_sub != subject:
        return None
    return user


def crm_allows_login(email: str, crm_client=None) -> bool:
    """Return True when the CRM gate is off or the contact is allowed.

    Fail closed when Dynamics cannot be reached, unless CRM_LOGIN_GATE_FAIL_OPEN
    is set.
    """
    if not crm_login_gate_enabled():
        return True
    try:
        return contact_meets_gate(email, crm_client=crm_client)
    except Exception:
        logger.exception("CRM login gate failed")
        return crm_login_fail_open()


def contact_meets_gate(email: str, crm_client=None) -> bool:
    """True when a contact with this email exists and has the required web role."""
    if crm_client is None:
        from utils.dynamics_crm import DynamicsCRMClient

        crm_client = DynamicsCRMClient()

    normalized = (email or "").strip().lower()
    if not normalized:
        return False

    escaped = _odata_quote(normalized)
    response = crm_client._make_request(
        "contacts?$select=contactid,emailaddress1"
        f"&$filter=emailaddress1 eq '{escaped}'&$top=5"
    )
    contacts = response.get("value") or []
    contact = next(
        (
            row
            for row in contacts
            if (row.get("emailaddress1") or "").strip().lower() == normalized
        ),
        None,
    )
    if contact is None:
        return False

    role_name = (os.getenv("CRM_REQUIRED_WEB_ROLE_NAME") or "").strip()
    if not role_name:
        return True
    return contact_has_web_role(crm_client, contact["contactid"], role_name)


def contact_has_web_role(crm_client, contact_id: str, role_name: str) -> bool:
    escaped_role = _odata_quote(role_name)
    roles = crm_client._make_request(
        "adx_webroles?$select=adx_webroleid,adx_name"
        f"&$filter=adx_name eq '{escaped_role}'"
    )
    role_ids = [
        row.get("adx_webroleid")
        for row in (roles.get("value") or [])
        if row.get("adx_webroleid")
    ]
    if not role_ids:
        return False

    for role_id in role_ids:
        linked = crm_client._make_request(
            "adx_webrole_contactset?$select=adx_webrole_contactid"
            f"&$filter=contactid eq {contact_id} and adx_webroleid eq {role_id}&$top=1"
        )
        if linked.get("value"):
            return True
    return False
