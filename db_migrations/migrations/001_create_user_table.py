"""
Migration 001: Create User table for authentication

This migration creates the User table with all necessary fields for
Flask-Login authentication system with Bcrypt password hashing.
"""


def upgrade(conn):
    """Create User table"""
    cursor = conn.cursor()
    
    # Check if table already exists
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='user'
    """)
    
    if cursor.fetchone():
        print("  ℹ User table already exists, skipping creation")
        return
    
    # Create User table
    cursor.execute("""
        CREATE TABLE user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(80) UNIQUE NOT NULL,
            email VARCHAR(120) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            is_admin BOOLEAN DEFAULT 0 NOT NULL,
            is_active BOOLEAN DEFAULT 1 NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            CHECK (is_admin IN (0, 1)),
            CHECK (is_active IN (0, 1))
        )
    """)
    
    # Create indexes for better query performance
    cursor.execute("CREATE UNIQUE INDEX ix_user_username ON user (username)")
    cursor.execute("CREATE UNIQUE INDEX ix_user_email ON user (email)")
    
    conn.commit()
    print("  ✓ User table created with indexes")


def downgrade(conn):
    """Drop User table (rollback)"""
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS user")
    conn.commit()
    print("  ✓ User table dropped")
