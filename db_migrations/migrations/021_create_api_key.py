"""
Migration 021: API keys for command-line access.

Stores a hash of each key. The raw key is shown once when it is created.
"""


def upgrade(conn):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='api_key'"
    )
    if cursor.fetchone() is None:
        cursor.execute(
            """
            CREATE TABLE api_key (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name VARCHAR(80) NOT NULL,
                prefix VARCHAR(16) NOT NULL,
                key_hash VARCHAR(64) NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP,
                revoked_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user (id)
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_api_key_user_id ON api_key (user_id)")
        conn.commit()
        print("  ✓ Created api_key")
    else:
        print("  ℹ api_key already exists, skipping")


def downgrade(conn):
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS api_key")
    conn.commit()
