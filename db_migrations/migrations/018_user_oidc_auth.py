"""
Migration 018: Google sign-in fields on user.

Adds google_sub and auth_provider, and allows password_hash to be NULL
for accounts that sign in with Google only.
"""


def upgrade(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(user)")
    columns = {row[1]: row for row in cursor.fetchall()}
    if not columns:
        print("  ℹ user table missing, skipping")
        return

    if "google_sub" not in columns:
        cursor.execute("ALTER TABLE user ADD COLUMN google_sub TEXT")
        print("  ✓ Added google_sub to user")
    else:
        print("  ℹ google_sub already exists, skipping")

    if "auth_provider" not in columns:
        cursor.execute(
            "ALTER TABLE user ADD COLUMN auth_provider TEXT DEFAULT 'local'"
        )
        print("  ✓ Added auth_provider to user")
    else:
        print("  ℹ auth_provider already exists, skipping")

    cursor.execute(
        "UPDATE user SET auth_provider = 'local' "
        "WHERE auth_provider IS NULL OR auth_provider = ''"
    )
    conn.commit()

    cursor.execute("PRAGMA table_info(user)")
    password_col = next(
        (row for row in cursor.fetchall() if row[1] == "password_hash"), None
    )
    if password_col and password_col[3] == 1:
        _make_password_hash_nullable(conn)
    else:
        print("  ℹ password_hash already nullable, skipping rebuild")

    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_user_google_sub ON user (google_sub)"
    )
    conn.commit()
    print("  ✓ Ensured unique index on google_sub")


def _make_password_hash_nullable(conn):
    """Rebuild user so password_hash may be NULL (SQLite cannot ALTER nullability)."""
    cursor = conn.cursor()
    cursor.execute("ALTER TABLE user RENAME TO user_pre_oidc")
    cursor.execute(
        """
        CREATE TABLE user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(80) NOT NULL,
            email VARCHAR(120),
            password_hash VARCHAR(255),
            is_admin BOOLEAN DEFAULT 0 NOT NULL,
            is_active BOOLEAN DEFAULT 1 NOT NULL,
            feature_permissions TEXT DEFAULT '{}',
            role TEXT DEFAULT 'user',
            assigned_campaign_id TEXT,
            assigned_campaign_name TEXT,
            google_sub TEXT,
            auth_provider TEXT DEFAULT 'local',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
        """
    )
    cursor.execute("PRAGMA table_info(user_pre_oidc)")
    old_cols = {row[1] for row in cursor.fetchall()}
    cursor.execute("PRAGMA table_info(user)")
    new_cols = [row[1] for row in cursor.fetchall() if row[1] != "id"]
    shared = [name for name in new_cols if name in old_cols]
    # id is copied explicitly so existing primary keys stay stable
    insert_cols = ["id"] + shared
    col_sql = ", ".join(insert_cols)
    cursor.execute(
        f"INSERT INTO user ({col_sql}) SELECT {col_sql} FROM user_pre_oidc"
    )
    cursor.execute("DROP TABLE user_pre_oidc")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_user_username ON user (username)")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_user_email ON user (email)")
    conn.commit()
    print("  ✓ Rebuilt user so password_hash is nullable")


def downgrade(conn):
    print(
        "  ℹ Manual rollback: drop google_sub and auth_provider; "
        "password_hash nullability cannot be restored automatically"
    )
