"""Bearer tokens and the command list a future CLI can call."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

TOKEN_MAX_AGE = 12 * 60 * 60

# Stable JSON commands. HTML pages are not listed.
API_COMMANDS = (
    {"id": "auth.token", "method": "POST", "path": "/api/auth/token", "feature": None,
     "summary": "Trade a Helper username and password for a 12-hour bearer token."},
    {"id": "auth.keys", "method": "POST", "path": "/api/auth/keys", "feature": None,
     "summary": "Administrators only. Create an API key. The raw key is returned once. GET lists keys. DELETE /api/auth/keys/<id> revokes one."},
    {"id": "auth.me", "method": "GET", "path": "/api/me", "feature": None,
     "summary": "Who the token belongs to, and which features they can use."},
    {"id": "auth.commands", "method": "GET", "path": "/api", "feature": None,
     "summary": "List the commands this user is allowed to call."},
    {"id": "auth.docs", "method": "GET", "path": "/docs", "feature": None,
     "summary": "OpenAPI documentation. The spec file is GET /openapi.yaml."},
    {"id": "seating.events", "method": "GET", "path": "/api/seating/events", "feature": "seating",
     "summary": "Open events and the sub-events that have seating charts."},
    {"id": "seating.board", "method": "GET", "path": "/api/seating/<event_id>", "feature": "seating",
     "summary": "Floor plan, table types, and who is seated. Add ?sketch=1 to skip guest names."},
    {"id": "seating.guests", "method": "GET", "path": "/api/seating/<event_id>/guests", "feature": "seating",
     "summary": "Search people on a sub-event. Query parameter q."},
    {"id": "seating.questions", "method": "GET", "path": "/api/seating/<event_id>/questions", "feature": "seating",
     "summary": "Meal questions for a sub-event. Pass contact_id to include saved answers."},
    {"id": "seating.assign", "method": "POST", "path": "/api/seating/<event_id>/assign-batch", "feature": "seating",
     "summary": "Move one or more people. Body: {moves:[{contact_id, table_id, from_event_id, to_event_id, answers}]}."},
    {"id": "campaigns.open", "method": "GET", "path": "/api/campaigns/open", "feature": "badges",
     "summary": "Open conventions the user can use for badges."},
    {"id": "campaigns.sub_events", "method": "GET", "path": "/api/campaigns/<campaign_id>/sub-events", "feature": "badges",
     "summary": "Sub-events under one convention."},
    {"id": "badges.templates", "method": "GET", "path": "/api/badge-templates", "feature": "badges",
     "summary": "Saved badge templates."},
    {"id": "badges.preprocessing", "method": "GET", "path": "/api/preprocessing-templates", "feature": "badges",
     "summary": "Saved badge preprocessing templates."},
    {"id": "badges.generate", "method": "POST", "path": "/api/badges/pull-process-generate-async", "feature": "badges",
     "summary": "Start a badge job. Poll /api/badges/jobs/<job_id>."},
    {"id": "badges.job", "method": "GET", "path": "/api/badges/jobs/<job_id>", "feature": "badges",
     "summary": "Status of a badge job."},
    {"id": "badges.download", "method": "GET", "path": "/api/badges/jobs/<job_id>/download", "feature": "badges",
     "summary": "Download the PDF when the job is finished."},
    {"id": "magazine.schedules", "method": "GET", "path": "/api/schedules", "feature": "magazine",
     "summary": "List magazine download schedules. POST creates one. DELETE removes one."},
    {"id": "event.urls", "method": "POST", "path": "/event", "feature": "event",
     "summary": "JSON body or form field crmUrl. Returns the private registration and summary URLs."},
)


def _sign(payload: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def issue_token(user_id: int, secret: str, now: float = None) -> str:
    body = json.dumps({"uid": int(user_id), "exp": int((now if now is not None else time.time()) + TOKEN_MAX_AGE)}, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")
    return encoded + "." + _sign(encoded.encode("ascii"), secret)


def read_token(token: str, secret: str, max_age: int = TOKEN_MAX_AGE, now: float = None):
    try:
        encoded, signature = token.split(".", 1)
    except (AttributeError, ValueError):
        return None
    if not hmac.compare_digest(_sign(encoded.encode("ascii"), secret), signature):
        return None
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        expires = int(data["exp"])
        user_id = int(data["uid"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    current = now if now is not None else time.time()
    if expires < current or expires - current > max_age + 5:
        return None
    return user_id


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple:
    """Return (raw key, sha256 hex, display prefix). The raw key is not stored."""
    raw = "afrp_" + secrets.token_urlsafe(32)
    return raw, hash_api_key(raw), raw[:12]


def user_id_for_api_key(raw_key: str, lookup):
    """lookup(hash) -> dict with user_id and revoked_at, or None."""
    if not raw_key or not str(raw_key).startswith("afrp_"):
        return None
    row = lookup(hash_api_key(raw_key))
    if not row or row.get("revoked_at"):
        return None
    return row.get("user_id")


def commands_for(user) -> list:
    """Commands this user may call. Admins see every command."""
    allowed = []
    is_admin = bool(getattr(user, "is_admin", False))
    for command in API_COMMANDS:
        feature = command["feature"]
        if command["id"] == "auth.keys" and not is_admin:
            continue
        if feature and not is_admin and not user.has_feature(feature):
            continue
        allowed.append({key: command[key] for key in ("id", "method", "path", "summary")})
    return allowed
