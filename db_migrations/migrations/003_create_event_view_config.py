"""
Migration 003: Create event_view_config table

Creates table for storing Dynamics CRM view configurations for Badge Generator.
Groups all 4 view IDs under a single event name for easy management.
"""


def upgrade(conn):
    """Create event_view_config table"""
    cursor = conn.cursor()
    
    # Check if table already exists
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='event_view_config'
    """)
    
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE event_view_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_name VARCHAR(200) UNIQUE NOT NULL,
                event_guests_view_id VARCHAR(100) NOT NULL,
                qr_codes_view_id VARCHAR(100) NOT NULL,
                table_reservations_view_id VARCHAR(100) NOT NULL,
                form_responses_view_id VARCHAR(100) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_default BOOLEAN DEFAULT 0,
                CHECK (is_default IN (0, 1))
            )
        """)
        print("  ✓ Created event_view_config table")
    else:
        print("  ℹ Event_view_config table already exists, skipping")
    
    conn.commit()


def downgrade(conn):
    """Drop event_view_config table (rollback)"""
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS event_view_config")
    conn.commit()
    print("  ✓ Dropped event_view_config table")
