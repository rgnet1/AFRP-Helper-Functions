"""
Migration 020: Days-before setting for coordinator portal password access.

Default 0 means coordinators can reset passwords only on the event dates.
"""


def upgrade(conn):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='app_setting'"
    )
    if cursor.fetchone() is None:
        cursor.execute(
            """
            CREATE TABLE app_setting (
                key VARCHAR(80) PRIMARY KEY,
                value VARCHAR(255) NOT NULL
            )
            """
        )
        print("  ✓ Created app_setting")
    else:
        print("  ℹ app_setting already exists, skipping create")
    cursor.execute(
        "SELECT key FROM app_setting WHERE key = ?",
        ("password_reset_days_before",),
    )
    if cursor.fetchone() is None:
        cursor.execute(
            "INSERT INTO app_setting (key, value) VALUES (?, ?)",
            ("password_reset_days_before", "0"),
        )
        print("  ✓ Set password_reset_days_before to 0")
    else:
        print("  ℹ password_reset_days_before already set, skipping")
    conn.commit()


def downgrade(conn):
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM app_setting WHERE key = ?",
        ("password_reset_days_before",),
    )
    conn.commit()
