"""
Migration 009: Add background_id to badge_template

Stores the selected badge background template (e.g. white, afrp_green_header).
"""


def upgrade(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(badge_template)")
    columns = {row[1] for row in cursor.fetchall()}

    if "background_id" not in columns:
        cursor.execute(
            "ALTER TABLE badge_template ADD COLUMN background_id VARCHAR(50) DEFAULT 'white'"
        )
        conn.commit()
        print("  ✓ Added background_id to badge_template")
    else:
        print("  ℹ background_id already exists, skipping")


def downgrade(conn):
    pass
