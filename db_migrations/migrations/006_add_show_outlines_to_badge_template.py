"""
Migration 006: Add show_outlines to badge_template table

Adds a boolean field to enable/disable badge outlines for alignment testing.
"""


def upgrade(conn):
    """Add show_outlines column to badge_template table"""
    cursor = conn.cursor()
    
    # Check if column exists
    cursor.execute("PRAGMA table_info(badge_template)")
    columns = {row[1] for row in cursor.fetchall()}
    
    if 'show_outlines' not in columns:
        cursor.execute("""
            ALTER TABLE badge_template 
            ADD COLUMN show_outlines BOOLEAN DEFAULT 0
        """)
        conn.commit()
        print("  ✓ Added show_outlines column to badge_template")
    else:
        print("  ℹ show_outlines column already exists")


def downgrade(conn):
    """Remove show_outlines column (requires table recreation in SQLite)"""
    # SQLite doesn't support DROP COLUMN easily
    print("  ⚠ Manual rollback required for show_outlines column")
    pass
