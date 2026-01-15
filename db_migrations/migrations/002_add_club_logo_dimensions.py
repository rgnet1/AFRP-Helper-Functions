"""
Migration 002: Add club logo dimensions to badge_template table

Adds club_logo_width and club_logo_height columns to support automatic
sizing of uploaded club logos on badges.
"""


def upgrade(conn):
    """Add club_logo_width and club_logo_height columns"""
    cursor = conn.cursor()
    
    # Check if columns already exist
    cursor.execute("PRAGMA table_info(badge_template)")
    columns = {row[1] for row in cursor.fetchall()}
    
    if 'club_logo_width' in columns and 'club_logo_height' in columns:
        print("  ℹ Club logo dimension columns already exist, skipping")
        return
    
    # Add club_logo_width column if it doesn't exist
    if 'club_logo_width' not in columns:
        cursor.execute("""
            ALTER TABLE badge_template 
            ADD COLUMN club_logo_width INTEGER
        """)
        print("  ✓ Added club_logo_width column")
    
    # Add club_logo_height column if it doesn't exist
    if 'club_logo_height' not in columns:
        cursor.execute("""
            ALTER TABLE badge_template 
            ADD COLUMN club_logo_height INTEGER
        """)
        print("  ✓ Added club_logo_height column")
    
    conn.commit()


def downgrade(conn):
    """
    Remove club logo dimension columns
    
    Note: SQLite doesn't support DROP COLUMN directly.
    This would require recreating the table without these columns.
    For now, we'll leave them as they don't cause issues if unused.
    """
    print("  ⚠ SQLite doesn't support DROP COLUMN - columns will remain but unused")
    # Could implement full table recreation if needed
    pass
