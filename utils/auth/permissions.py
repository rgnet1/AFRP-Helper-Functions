"""Feature-based access control for home page modules."""

import json

FEATURES = {
    "qr": {
        "label": "QR Code Generator",
        "home_tile": True,
        "path_prefixes": ["/qr"],
    },
    "event": {
        "label": "Generate Private Event URL",
        "home_tile": True,
        "path_prefixes": ["/event"],
    },
    "magazine": {
        "label": "Magazine Downloader",
        "home_tile": True,
        "path_prefixes": ["/magazine", "/api/schedules", "/run-magazine-download"],
    },
    "badges": {
        "label": "Badge Generator",
        "home_tile": True,
        "path_prefixes": [
            "/badges",
            "/badge-mapping",
            "/preprocessing-designer",
            "/api/badges",
            "/api/badge-",
            "/api/campaigns",
            "/api/avery-templates",
            "/api/preprocessing-templates",
            "/badge_logos/",
            "/badge_background_templates/",
            "/badge_templates/",
        ],
    },
}

ALL_FEATURES_BACKFILL = json.dumps({fid: True for fid in FEATURES})

PUBLIC_PATH_PREFIXES = ("/login", "/setup", "/logout")
ADMIN_PATH_PREFIX = "/users"
HOME_PATH = "/"


def default_feature_permissions() -> dict:
    return {feature_id: False for feature_id in FEATURES}


def normalize_feature_permissions(raw) -> dict:
    """Merge stored permissions with defaults for known features."""
    merged = default_feature_permissions()
    if not raw:
        return merged
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return merged
    if not isinstance(raw, dict):
        return merged
    for feature_id in FEATURES:
        if feature_id in raw:
            merged[feature_id] = bool(raw[feature_id])
    return merged


def permissions_from_form(form, prefix="feature_") -> dict:
    """Build permissions dict from request form checkboxes."""
    return {
        feature_id: form.get(f"{prefix}{feature_id}") == "on"
        for feature_id in FEATURES
    }


def feature_for_path(path: str) -> str | None:
    """Return the feature id that owns this path, or None if unmapped."""
    if not path:
        return None
    best_match = None
    best_len = -1
    for feature_id, meta in FEATURES.items():
        for prefix in meta["path_prefixes"]:
            if path == prefix.rstrip("/") or path.startswith(prefix):
                if len(prefix) > best_len:
                    best_len = len(prefix)
                    best_match = feature_id
    return best_match


def path_is_public(path: str) -> bool:
    if path.startswith("/static"):
        return True
    return any(path == p or path.startswith(p + "/") or path.startswith(p)
               for p in PUBLIC_PATH_PREFIXES if p != "/logout") or path == "/logout"


def path_requires_admin(path: str) -> bool:
    return path == ADMIN_PATH_PREFIX or path.startswith(ADMIN_PATH_PREFIX + "/")


def user_can_access_path(user, path: str) -> bool:
    """Return True if user may access the given path."""
    if user is None:
        return False
    if getattr(user, "is_admin", False):
        return True
    if path_is_public(path):
        return True
    if path_requires_admin(path):
        return False
    if path == HOME_PATH:
        return True
    feature_id = feature_for_path(path)
    if feature_id is None:
        return False
    return user.has_feature(feature_id)


def allowed_features_for_user(user) -> list:
    if user is None:
        return []
    if getattr(user, "is_admin", False):
        return list(FEATURES.keys())
    return [fid for fid in FEATURES if user.has_feature(fid)]
