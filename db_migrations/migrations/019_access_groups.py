"""
Migration 019: Shared access groups.

Creates access_group and access_group_member. Puts every current admin in an
Administrators group, and each event-coordinator campaign into its own group.
"""

import json


ADMIN_FEATURES = json.dumps(
    {"qr": True, "event": True, "magazine": True, "badges": True}
)
COORDINATOR_FEATURES = json.dumps(
    {"qr": False, "event": False, "magazine": False, "badges": True}
)


def upgrade(conn):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='access_group'"
    )
    if cursor.fetchone() is None:
        cursor.execute(
            """
            CREATE TABLE access_group (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(120) NOT NULL,
                role VARCHAR(50) NOT NULL DEFAULT 'user',
                assigned_campaign_id TEXT,
                assigned_campaign_name TEXT,
                feature_permissions TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        print("  ✓ Created access_group")
    else:
        print("  ℹ access_group already exists, skipping create")

    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='access_group_member'"
    )
    if cursor.fetchone() is None:
        cursor.execute(
            """
            CREATE TABLE access_group_member (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                UNIQUE (user_id, group_id),
                FOREIGN KEY (user_id) REFERENCES user (id),
                FOREIGN KEY (group_id) REFERENCES access_group (id)
            )
            """
        )
        print("  ✓ Created access_group_member")
    else:
        print("  ℹ access_group_member already exists, skipping create")

    cursor.execute("SELECT id FROM access_group WHERE role = 'admin' LIMIT 1")
    admin_row = cursor.fetchone()
    if admin_row is None:
        cursor.execute(
            """
            INSERT INTO access_group (name, role, feature_permissions)
            VALUES ('Administrators', 'admin', ?)
            """,
            (ADMIN_FEATURES,),
        )
        admin_group_id = cursor.lastrowid
        print("  ✓ Created Administrators group")
    else:
        admin_group_id = admin_row[0]
        print("  ℹ Administrators group already exists")

    cursor.execute("PRAGMA table_info(user)")
    columns = {row[1] for row in cursor.fetchall()}
    if "is_admin" in columns:
        cursor.execute("SELECT id FROM user WHERE is_admin = 1")
        for (user_id,) in cursor.fetchall():
            cursor.execute(
                """
                INSERT OR IGNORE INTO access_group_member (user_id, group_id)
                VALUES (?, ?)
                """,
                (user_id, admin_group_id),
            )
        print("  ✓ Added existing admins to Administrators")

    if "role" in columns and "assigned_campaign_id" in columns:
        cursor.execute(
            """
            SELECT DISTINCT assigned_campaign_id, assigned_campaign_name
            FROM user
            WHERE role = 'event_coordinator'
              AND assigned_campaign_id IS NOT NULL
              AND TRIM(assigned_campaign_id) != ''
            """
        )
        for campaign_id, campaign_name in cursor.fetchall():
            label = (campaign_name or campaign_id or "Event").strip()
            cursor.execute(
                """
                SELECT id FROM access_group
                WHERE role = 'event_coordinator' AND assigned_campaign_id = ?
                """,
                (campaign_id,),
            )
            existing = cursor.fetchone()
            if existing:
                group_id = existing[0]
            else:
                cursor.execute(
                    """
                    INSERT INTO access_group
                        (name, role, assigned_campaign_id, assigned_campaign_name, feature_permissions)
                    VALUES (?, 'event_coordinator', ?, ?, ?)
                    """,
                    (f"Event coordinators — {label}", campaign_id, label, COORDINATOR_FEATURES),
                )
                group_id = cursor.lastrowid
                print(f"  ✓ Created coordinator group for {label}")
            cursor.execute(
                """
                SELECT id FROM user
                WHERE role = 'event_coordinator' AND assigned_campaign_id = ?
                """,
                (campaign_id,),
            )
            for (user_id,) in cursor.fetchall():
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO access_group_member (user_id, group_id)
                    VALUES (?, ?)
                    """,
                    (user_id, group_id),
                )

    conn.commit()


def downgrade(conn):
    print("  ℹ Manual rollback: drop access_group_member and access_group")
