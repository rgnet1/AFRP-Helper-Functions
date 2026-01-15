"""
Authentication utilities for password and username validation.
"""
import re
from typing import Tuple


def validate_password(password: str) -> Tuple[bool, str]:
    """
    Validate password meets complexity requirements.
    
    Requirements:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one number
    - At least one special character
    
    Args:
        password: Password string to validate
        
    Returns:
        Tuple of (is_valid, error_message)
        If valid, error_message will be empty string
    """
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
    """
    Validate username format.
    
    Requirements:
    - Minimum 3 characters
    - Maximum 80 characters
    - Only letters, numbers, hyphens, and underscores
    
    Args:
        username: Username string to validate
        
    Returns:
        Tuple of (is_valid, error_message)
        If valid, error_message will be empty string
    """
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
    """
    Validate email format (basic validation).
    
    Args:
        email: Email string to validate
        
    Returns:
        Tuple of (is_valid, error_message)
        If valid, error_message will be empty string
    """
    if not email:
        # Email is optional
        return True, ""
    
    # Basic email regex
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False, "Invalid email format"
    
    return True, ""
