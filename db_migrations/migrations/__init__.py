"""
Database Migrations

Individual migration files follow the naming convention:
###_description.py

Where ### is a zero-padded version number (e.g., 001, 002, 003)

Each migration file must contain:
- upgrade(conn): Function to apply the migration
- downgrade(conn): Function to rollback the migration (optional)
"""
