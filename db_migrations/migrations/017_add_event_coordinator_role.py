"""
Migration 017: Add Event Coordinator role and assigned campaign fields

Adds role, assigned_campaign_id, and assigned_campaign_name to user table.
Backfills role from is_admin for existing users.
"""


def upgrade(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(user)")
    columns = {row[1] for row in cursor.fetchall()}

    if "role" not in columns:
        cursor.execute(
            "ALTER TABLE user ADD COLUMN role TEXT DEFAULT 'user'"
        )
        conn.commit()
        print("  ✓ Added role to user")
    else:
        print("  ℹ role already exists, skipping")

    if "assigned_campaign_id" not in columns:
        cursor.execute(
            "ALTER TABLE user ADD COLUMN assigned_campaign_id TEXT"
        )
        conn.commit()
        print("  ✓ Added assigned_campaign_id to user")
    else:
        print("  ℹ assigned_campaign_id already exists, skipping")

    if "assigned_campaign_name" not in columns:
        cursor.execute(
            "ALTER TABLE user ADD COLUMN assigned_campaign_name TEXT"
        )
        conn.commit()
        print("  ✓ Added assigned_campaign_name to user")
    else:
        print("  ℹ assigned_campaign_name already exists, skipping")

    cursor.execute(
        "UPDATE user SET role = 'admin' WHERE is_admin = 1 AND (role IS NULL OR role = 'user')"
    )
    cursor.execute(
        "UPDATE user SET role = 'user' WHERE is_admin = 0 AND role IS NULL"
    )
    conn.commit()
    print("  ✓ Backfilled role from is_admin")


def downgrade(conn):
    print(
        "  ℹ Manual rollback required: remove role, assigned_campaign_id, "
        "assigned_campaign_name from user"
    )
