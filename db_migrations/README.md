# Database Migration System

Automatic database migration system that runs at container startup and tracks applied migrations.

## How It Works

1. **Automatic Execution**: Migrations run automatically when the Docker container starts
2. **Tracking**: Applied migrations are recorded in `schema_migrations` table
3. **Idempotent**: Safe to run multiple times - already applied migrations are skipped
4. **Ordered**: Migrations run in version order (001, 002, 003, etc.)

## Directory Structure

```
db_migrations/
├── migration_runner.py          # Main migration engine
├── migrations/                  # Individual migration files
│   ├── 001_create_user_table.py
│   ├── 002_add_club_logo_dimensions.py
│   └── ...
└── README.md                    # This file
```

## Creating a New Migration

### Step 1: Create Migration File

Create a new file in `migrations/` following the naming convention:

```
###_descriptive_name.py
```

Where `###` is the next sequential version number (zero-padded to 3 digits).

**Example**: `003_add_notification_settings.py`

### Step 2: Write Migration Code

Each migration file must contain an `upgrade()` function:

```python
"""
Migration 003: Add notification settings to User table

Adds email notification preferences for users.
"""


def upgrade(conn):
    """
    Apply the migration
    
    Args:
        conn: SQLite database connection object
    """
    cursor = conn.cursor()
    
    # Check if column already exists (idempotent)
    cursor.execute("PRAGMA table_info(user)")
    columns = {row[1] for row in cursor.fetchall()}
    
    if 'email_notifications' in columns:
        print("  ℹ Column already exists, skipping")
        return
    
    # Add new column
    cursor.execute("""
        ALTER TABLE user 
        ADD COLUMN email_notifications BOOLEAN DEFAULT 1
    """)
    
    conn.commit()
    print("  ✓ Added email_notifications column")


def downgrade(conn):
    """
    Rollback the migration (optional)
    
    Args:
        conn: SQLite database connection object
    """
    # SQLite doesn't support DROP COLUMN easily
    # Document the rollback process or leave empty
    print("  ⚠ Manual rollback required")
    pass
```

### Step 3: Test the Migration

Test locally before deploying:

```bash
# Dry run - shows what would be applied without making changes
python3 db_migrations/migration_runner.py --dry-run

# Apply migrations
python3 db_migrations/migration_runner.py
```

### Step 4: Deploy

Commit your migration file:

```bash
git add db_migrations/migrations/003_add_notification_settings.py
git commit -m "Add migration for notification settings"
```

When the container restarts, the migration will run automatically!

## Migration Best Practices

### 1. Make Migrations Idempotent

Always check if changes already exist before applying:

```python
# Good: Check before creating
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='my_table'")
if not cursor.fetchone():
    cursor.execute("CREATE TABLE my_table (...)")
```

```python
# Good: Check before adding column
cursor.execute("PRAGMA table_info(user)")
columns = {row[1] for row in cursor.fetchall()}
if 'new_column' not in columns:
    cursor.execute("ALTER TABLE user ADD COLUMN new_column TEXT")
```

### 2. Use Descriptive Names

```
✓ Good: 003_add_email_verification.py
✗ Bad:  003_update.py
```

### 3. Keep Migrations Small

One logical change per migration:

```
✓ Good: 004_add_two_factor_auth.py
        005_add_session_timeout.py

✗ Bad:  004_add_lots_of_security_features.py
```

### 4. Test Before Committing

```bash
# Always test migrations before committing
python3 db_migrations/migration_runner.py --dry-run
python3 db_migrations/migration_runner.py
```

### 5. Handle SQLite Limitations

SQLite has limited ALTER TABLE support:
- Can ADD COLUMN
- Cannot DROP COLUMN (requires table recreation)
- Cannot ALTER COLUMN (requires table recreation)

For complex changes, you may need to:
1. Create new table
2. Copy data
3. Drop old table
4. Rename new table

### 6. Add Print Statements

Help with debugging:

```python
def upgrade(conn):
    print("  ✓ Creating index on username")
    cursor = conn.cursor()
    cursor.execute("CREATE INDEX idx_username ON user(username)")
    conn.commit()
    print("  ✓ Index created successfully")
```

## Manual Migration Execution

### Run All Pending Migrations

```bash
python3 db_migrations/migration_runner.py
```

### Dry Run (Preview)

```bash
python3 db_migrations/migration_runner.py --dry-run
```

### Custom Database Path

```bash
python3 db_migrations/migration_runner.py --db /path/to/database.db
```

### Docker Execution

```bash
# Run migrations in running container
docker-compose exec afrp-helper python3 db_migrations/migration_runner.py

# Dry run
docker-compose exec afrp-helper python3 db_migrations/migration_runner.py --dry-run
```

## Viewing Applied Migrations

Query the tracking table:

```bash
sqlite3 data/magazine_schedules.db "SELECT * FROM schema_migrations ORDER BY version"
```

Or use Python:

```python
import sqlite3
conn = sqlite3.connect('data/magazine_schedules.db')
cursor = conn.cursor()
cursor.execute("SELECT version, name, applied_at, execution_time_ms FROM schema_migrations ORDER BY version")
for row in cursor.fetchall():
    print(f"{row[0]}: {row[1]} (applied {row[2]}, took {row[3]}ms)")
```

## Troubleshooting

### "Migration failed" Error

1. Check the error message in console output
2. Fix the migration file
3. If migration was partially applied, you may need to manually rollback:
   ```sql
   -- Remove from tracking table
   DELETE FROM schema_migrations WHERE version='003';
   
   -- Manually undo changes (if needed)
   ```
4. Re-run migrations

### Migration Not Running

1. Check filename format: `###_name.py` (3 digits, underscore, name)
2. Verify file is in `db_migrations/migrations/` folder
3. Check file has `upgrade()` function
4. Run with `--dry-run` to see if it's detected

### Migration Already Applied

Migrations are tracked in `schema_migrations` table. To re-run:

```sql
DELETE FROM schema_migrations WHERE version='003';
```

Then restart container or run migration manually.

## Example Migrations

### Adding a Column

```python
def upgrade(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(user)")
    columns = {row[1] for row in cursor.fetchall()}
    
    if 'phone_number' not in columns:
        cursor.execute("ALTER TABLE user ADD COLUMN phone_number VARCHAR(20)")
        conn.commit()
        print("  ✓ Added phone_number column")
```

### Creating a Table

```python
def upgrade(conn):
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='notifications'
    """)
    
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                read BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user (id)
            )
        """)
        conn.commit()
        print("  ✓ Created notifications table")
```

### Creating an Index

```python
def upgrade(conn):
    cursor = conn.cursor()
    
    # Check if index exists
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='index' AND name='idx_user_email'
    """)
    
    if not cursor.fetchone():
        cursor.execute("CREATE INDEX idx_user_email ON user(email)")
        conn.commit()
        print("  ✓ Created index on user.email")
```

### Modifying Data

```python
def upgrade(conn):
    cursor = conn.cursor()
    
    # Update existing records
    cursor.execute("UPDATE user SET is_active = 1 WHERE is_active IS NULL")
    affected = cursor.rowcount
    
    conn.commit()
    print(f"  ✓ Updated {affected} user records")
```

## Integration with Cursor Rules

See `.cursor/rules/database-migrations.mdc` for AI assistance when creating migrations.
