"""
Migration 022: Membership for event coordinators.

Existing coordinator users and groups were saved before Membership was part of
that role. Turn the feature on so the stored permissions match what they can open.
"""

import json


def _with_membership(raw):
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    if data.get("membership") is True:
        return None
    data["membership"] = True
    return json.dumps(data)


def upgrade(conn):
    cursor = conn.cursor()
    changed = 0
    for table in ("user", "access_group"):
        cursor.execute(
            f"SELECT id, feature_permissions FROM {table} WHERE role = 'event_coordinator'"
        )
        for row_id, raw in cursor.fetchall():
            updated = _with_membership(raw)
            if updated is None:
                continue
            cursor.execute(
                f"UPDATE {table} SET feature_permissions = ? WHERE id = ?",
                (updated, row_id),
            )
            changed += 1
    conn.commit()
    print(f"  ✓ Enabled membership on {changed} event coordinator rows")


def downgrade(conn):
    cursor = conn.cursor()
    for table in ("user", "access_group"):
        cursor.execute(
            f"SELECT id, feature_permissions FROM {table} WHERE role = 'event_coordinator'"
        )
        for row_id, raw in cursor.fetchall():
            try:
                data = json.loads(raw or "{}")
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict) or "membership" not in data:
                continue
            data["membership"] = False
            cursor.execute(
                f"UPDATE {table} SET feature_permissions = ? WHERE id = ?",
                (json.dumps(data), row_id),
            )
    conn.commit()
