"""
Migration 014: Add meal_preference_mappings to badge_template

Stores per-template mappings from raw CRM meal responses to badge labels
(e.g. Yes -> V, Steak -> S).
"""


def upgrade(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(badge_template)")
    columns = {row[1] for row in cursor.fetchall()}

    if "meal_preference_mappings" not in columns:
        cursor.execute(
            "ALTER TABLE badge_template ADD COLUMN meal_preference_mappings TEXT DEFAULT '{}'"
        )
        conn.commit()
        print("  ✓ Added meal_preference_mappings to badge_template")
    else:
        print("  ℹ meal_preference_mappings already exists, skipping")


def downgrade(conn):
    print(
        "  ℹ Manual rollback required: remove meal_preference_mappings from badge_template"
    )
