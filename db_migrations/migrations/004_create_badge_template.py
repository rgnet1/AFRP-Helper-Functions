"""
Migration 004: Create badge_template table

Creates table for storing badge template configurations including
SVG templates, club logos, column mappings, and Avery template settings.
"""


def upgrade(conn):
    """Create badge_template table with all columns"""
    cursor = conn.cursor()
    
    # Check if table already exists
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='badge_template'
    """)
    
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE badge_template (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(200) NOT NULL UNIQUE,
                svg_filename VARCHAR(255) NOT NULL,
                club_logo_filename VARCHAR(255),
                club_logo_width INTEGER,
                club_logo_height INTEGER,
                column_mappings TEXT NOT NULL,
                avery_template VARCHAR(50) DEFAULT '5392',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("  ✓ Created badge_template table with all columns")
    else:
        print("  ℹ Badge_template table already exists, skipping")
    
    conn.commit()


def downgrade(conn):
    """Drop badge_template table (rollback)"""
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS badge_template")
    conn.commit()
    print("  ✓ Dropped badge_template table")
