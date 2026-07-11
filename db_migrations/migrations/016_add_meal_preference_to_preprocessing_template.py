"""
Migration 016: Add meal preference config to preprocessing_template

Stores per-event meal source toggles and CRM response label mappings on the
preprocessing template (single source of truth for badge meal text).
"""


def upgrade(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(preprocessing_template)")
    columns = {row[1] for row in cursor.fetchall()}

    if "meal_preference_mappings" not in columns:
        cursor.execute(
            "ALTER TABLE preprocessing_template ADD COLUMN meal_preference_mappings TEXT DEFAULT '{}'"
        )
        conn.commit()
        print("  ✓ Added meal_preference_mappings to preprocessing_template")
    else:
        print("  ℹ meal_preference_mappings already exists, skipping")

    cursor.execute("PRAGMA table_info(preprocessing_template)")
    columns = {row[1] for row in cursor.fetchall()}

    if "meal_preference_sources" not in columns:
        cursor.execute(
            "ALTER TABLE preprocessing_template ADD COLUMN meal_preference_sources TEXT DEFAULT '{}'"
        )
        conn.commit()
        print("  ✓ Added meal_preference_sources to preprocessing_template")
    else:
        print("  ℹ meal_preference_sources already exists, skipping")


def downgrade(conn):
    print(
        "  ℹ Manual rollback required: remove meal_preference_mappings and "
        "meal_preference_sources from preprocessing_template"
    )
