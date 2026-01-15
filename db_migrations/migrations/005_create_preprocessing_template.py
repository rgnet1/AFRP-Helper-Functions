"""
Migration 005: Create preprocessing_template table

Creates table for storing user-configurable preprocessing templates
for data transformation with value and contains mappings.
"""


def upgrade(conn):
    """Create preprocessing_template table"""
    cursor = conn.cursor()
    
    # Check if table already exists
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='preprocessing_template'
    """)
    
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE preprocessing_template (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(200) NOT NULL UNIQUE,
                description TEXT,
                value_mappings TEXT NOT NULL DEFAULT '{}',
                contains_mappings TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("  ✓ Created preprocessing_template table")
    else:
        print("  ℹ Preprocessing_template table already exists, skipping")
    
    conn.commit()


def downgrade(conn):
    """Drop preprocessing_template table (rollback)"""
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS preprocessing_template")
    conn.commit()
    print("  ✓ Dropped preprocessing_template table")
