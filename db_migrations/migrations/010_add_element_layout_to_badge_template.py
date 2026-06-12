"""
Migration 010: Add element_layout to badge_template

Stores JSON layout overrides for corner logos, QR code, and sub-event blocks.
"""


def upgrade(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(badge_template)")
    columns = {row[1] for row in cursor.fetchall()}

    if "element_layout" not in columns:
        cursor.execute(
            "ALTER TABLE badge_template ADD COLUMN element_layout TEXT DEFAULT '{}'"
        )
        conn.commit()
        print("  ✓ Added element_layout to badge_template")
    else:
        print("  ℹ element_layout already exists, skipping")


def downgrade(conn):
    print("  ℹ Manual rollback required: remove element_layout from badge_template")
