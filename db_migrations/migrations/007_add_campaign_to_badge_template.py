"""
Migration 007: Add campaign_id and campaign_name to badge_template

Associates each badge template with a specific main event (campaign)
so sub-event columns can be auto-discovered from CRM.
"""


def upgrade(conn):
    """Apply the migration."""
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(badge_template)")
    columns = {row[1] for row in cursor.fetchall()}

    if 'campaign_id' not in columns:
        cursor.execute("ALTER TABLE badge_template ADD COLUMN campaign_id VARCHAR(64)")
        conn.commit()
        print("  ✓ Added campaign_id to badge_template")
    else:
        print("  ℹ campaign_id already exists, skipping")

    if 'campaign_name' not in columns:
        cursor.execute("ALTER TABLE badge_template ADD COLUMN campaign_name VARCHAR(255)")
        conn.commit()
        print("  ✓ Added campaign_name to badge_template")
    else:
        print("  ℹ campaign_name already exists, skipping")


def downgrade(conn):
    """Rollback the migration (SQLite doesn't support DROP COLUMN easily)."""
    print("  ℹ Manual rollback required: remove campaign_id and campaign_name from badge_template")
