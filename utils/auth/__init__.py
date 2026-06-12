"""
Authentication utilities for password validation and feature permissions.
"""
import re
from typing import Tuple

from utils.auth.permissions import (  # noqa: F401
    FEATURES,
    allowed_features_for_user,
    feature_for_path,
    path_is_public,
    path_requires_admin,
    permissions_from_form,
    user_can_access_path,
)


def validate_password(password: str) -> Tuple[bool, str]:
    if not password:
        return False, "Password is required"
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least one number"
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character (!@#$%^&*(),.?\":{}|<>)"
    return True, ""


def validate_username(username: str) -> Tuple[bool, str]:
    if not username:
        return False, "Username is required"
    if len(username) < 3:
        return False, "Username must be at least 3 characters long"
    if len(username) > 80:
        return False, "Username must be less than 80 characters"
    if not re.match(r'^[a-zA-Z0-9_-]+$', username):
        return False, "Username can only contain letters, numbers, hyphens, and underscores"
    return True, ""


def validate_email(email: str) -> Tuple[bool, str]:
    if not email:
        return True, ""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False, "Invalid email format"
    return True, ""
