"""
Migration 015: Add meal_preference_sources to badge_template

Stores per-event toggles for which meal questionnaire responses appear on badges.
"""


def upgrade(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(badge_template)")
    columns = {row[1] for row in cursor.fetchall()}

    if "meal_preference_sources" not in columns:
        cursor.execute(
            "ALTER TABLE badge_template ADD COLUMN meal_preference_sources TEXT DEFAULT '{}'"
        )
        conn.commit()
        print("  ✓ Added meal_preference_sources to badge_template")
    else:
        print("  ℹ meal_preference_sources already exists, skipping")


def downgrade(conn):
    print(
        "  ℹ Manual rollback required: remove meal_preference_sources from badge_template"
    )
