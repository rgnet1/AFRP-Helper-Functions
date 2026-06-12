"""
Migration 011: Add display_name_config to badge_template

Stores per-template rules for building {{DISPLAY_NAME}} (middle/maiden inclusion
and optional parentheses around each part).
"""


def upgrade(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(badge_template)")
    columns = {row[1] for row in cursor.fetchall()}

    if "display_name_config" not in columns:
        cursor.execute(
            "ALTER TABLE badge_template ADD COLUMN display_name_config TEXT DEFAULT '{}'"
        )
        conn.commit()
        print("  ✓ Added display_name_config to badge_template")
    else:
        print("  ℹ display_name_config already exists, skipping")


def downgrade(conn):
    print("  ℹ Manual rollback required: remove display_name_config from badge_template")
