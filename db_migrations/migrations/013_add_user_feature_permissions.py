"""
Migration 013: Add feature_permissions to user table

Stores per-feature access flags (qr, event, magazine, badges) as JSON.
Existing non-admin users receive all features for backward compatibility.
"""

import json

ALL_FEATURES = json.dumps({"qr": True, "event": True, "magazine": True, "badges": True})


def upgrade(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(user)")
    columns = {row[1] for row in cursor.fetchall()}

    if "feature_permissions" not in columns:
        cursor.execute(
            "ALTER TABLE user ADD COLUMN feature_permissions TEXT DEFAULT '{}'"
        )
        conn.commit()
        print("  ✓ Added feature_permissions to user")
    else:
        print("  ℹ feature_permissions already exists, skipping")

    cursor.execute(
        "UPDATE user SET feature_permissions = ? WHERE is_admin = 0",
        (ALL_FEATURES,),
    )
    conn.commit()
    print("  ✓ Backfilled feature_permissions for existing non-admin users")


def downgrade(conn):
    print("  ℹ Manual rollback required: remove feature_permissions from user")
