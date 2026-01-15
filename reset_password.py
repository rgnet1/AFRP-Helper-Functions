#!/usr/bin/env python3
"""
Password Reset Script

Allows resetting user passwords from the command line.
Useful for recovering locked-out admin accounts.

Usage:
    python3 reset_password.py username
    python3 reset_password.py username --password "newpassword"
    
Interactive mode (prompts for password):
    python3 reset_password.py admin

Non-interactive mode (for scripts):
    python3 reset_password.py admin --password "MyNewPass123!"
"""

import os
import sys
import getpass
import argparse

# Add the project directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from utils.magazine.scheduler import User
from utils.auth import validate_password


def reset_password(username, new_password=None, force=False):
    """
    Reset password for a user.
    
    Args:
        username: Username to reset password for
        new_password: New password (if None, will prompt)
        force: Skip password validation (not recommended)
    
    Returns:
        True if successful, False otherwise
    """
    with app.app_context():
        # Find user
        user = User.query.filter_by(username=username).first()
        
        if not user:
            print(f"✗ User '{username}' not found")
            print("\nAvailable users:")
            all_users = User.query.all()
            for u in all_users:
                admin_badge = " (admin)" if u.is_admin else ""
                active_badge = "" if u.is_active else " (inactive)"
                print(f"  - {u.username}{admin_badge}{active_badge}")
            return False
        
        # Get password if not provided
        if new_password is None:
            print(f"\nResetting password for: {user.username}")
            if user.is_admin:
                print("⚠ Warning: This is an admin account")
            
            while True:
                new_password = getpass.getpass("Enter new password: ")
                confirm_password = getpass.getpass("Confirm new password: ")
                
                if new_password != confirm_password:
                    print("✗ Passwords do not match. Try again.\n")
                    continue
                
                if not new_password:
                    print("✗ Password cannot be empty. Try again.\n")
                    continue
                
                break
        
        # Validate password strength (unless forced)
        if not force:
            valid, message = validate_password(new_password)
            if not valid:
                print(f"✗ Password validation failed: {message}")
                print("\nPassword requirements:")
                print("  - At least 8 characters long")
                print("  - Contains at least one uppercase letter")
                print("  - Contains at least one lowercase letter")
                print("  - Contains at least one number")
                print("  - Contains at least one special character (!@#$%^&*(),.?\":{}|<>)")
                print("\nUse --force to bypass validation (not recommended)")
                return False
        
        # Update password
        try:
            user.set_password(new_password)
            db.session.commit()
            
            print("\n" + "="*60)
            print("✓ Password reset successful!")
            print("="*60)
            print(f"Username: {user.username}")
            print(f"Email: {user.email or 'N/A'}")
            print(f"Admin: {'Yes' if user.is_admin else 'No'}")
            print(f"Active: {'Yes' if user.is_active else 'No'}")
            print("="*60)
            
            return True
            
        except Exception as e:
            print(f"✗ Failed to reset password: {e}")
            db.session.rollback()
            return False


def main():
    parser = argparse.ArgumentParser(
        description="Reset user password",
        epilog="""
Examples:
  # Interactive mode (prompts for password)
  python3 reset_password.py admin
  
  # Non-interactive mode
  python3 reset_password.py admin --password "MyNewPass123!"
  
  # Force password (skip validation)
  python3 reset_password.py admin --password "weak" --force
  
  # In Docker
  docker-compose exec afrp-helper python3 reset_password.py admin
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        'username',
        help='Username to reset password for'
    )
    
    parser.add_argument(
        '--password',
        help='New password (if not provided, will prompt interactively)',
        default=None
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='Skip password validation (not recommended)'
    )
    
    parser.add_argument(
        '--list',
        action='store_true',
        help='List all users and exit'
    )
    
    args = parser.parse_args()
    
    # List users if requested
    if args.list:
        with app.app_context():
            users = User.query.all()
            print("\nAll users:")
            print("-" * 60)
            for user in users:
                admin_badge = " (admin)" if user.is_admin else ""
                active_badge = "" if user.is_active else " (inactive)"
                print(f"  {user.username}{admin_badge}{active_badge}")
                if user.email:
                    print(f"    Email: {user.email}")
                if user.last_login:
                    print(f"    Last login: {user.last_login}")
            print("-" * 60)
        return
    
    # Reset password
    success = reset_password(args.username, args.password, args.force)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
