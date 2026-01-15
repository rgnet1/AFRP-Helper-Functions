"""
Database Migration Runner

Automatically discovers and applies pending database migrations at startup.
Tracks applied migrations in a schema_migrations table.
"""

import os
import sys
import sqlite3
import importlib.util
from pathlib import Path
from datetime import datetime
from typing import List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MigrationRunner:
    """Manages database migrations with automatic detection and application"""
    
    def __init__(self, db_path: str, migrations_dir: str = None):
        """
        Initialize migration runner
        
        Args:
            db_path: Path to SQLite database file
            migrations_dir: Path to migrations directory (default: ./migrations)
        """
        self.db_path = db_path
        
        if migrations_dir is None:
            # Default to migrations subdirectory
            current_dir = Path(__file__).parent
            self.migrations_dir = current_dir / "migrations"
        else:
            self.migrations_dir = Path(migrations_dir)
        
        self.conn = None
    
    def connect(self):
        """Connect to database"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        return self.conn
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def ensure_migrations_table(self):
        """Create schema_migrations table if it doesn't exist"""
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                execution_time_ms INTEGER
            )
        """)
        self.conn.commit()
        print("✓ Schema migrations table ready")
    
    def get_applied_migrations(self) -> set:
        """Get set of already applied migration versions"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
        return {row['version'] for row in cursor.fetchall()}
    
    def discover_migrations(self) -> List[Tuple[str, str, Path]]:
        """
        Discover migration files in migrations directory
        
        Returns:
            List of tuples: (version, name, filepath)
            Sorted by version number
        """
        migrations = []
        
        if not self.migrations_dir.exists():
            print(f"⚠ Migrations directory not found: {self.migrations_dir}")
            return migrations
        
        # Find all Python files that match migration pattern: ###_name.py
        for filepath in sorted(self.migrations_dir.glob("[0-9][0-9][0-9]_*.py")):
            if filepath.name == "__init__.py":
                continue
            
            # Parse version and name from filename
            # Format: 001_create_user_table.py
            filename = filepath.stem  # Remove .py extension
            parts = filename.split("_", 1)
            
            if len(parts) != 2:
                print(f"⚠ Skipping invalid migration filename: {filepath.name}")
                continue
            
            version = parts[0]
            name = parts[1]
            
            migrations.append((version, name, filepath))
        
        return migrations
    
    def load_migration_module(self, filepath: Path):
        """
        Dynamically load a migration module
        
        Args:
            filepath: Path to migration Python file
            
        Returns:
            Loaded module object
        """
        spec = importlib.util.spec_from_file_location(filepath.stem, filepath)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    
    def apply_migration(self, version: str, name: str, filepath: Path) -> bool:
        """
        Apply a single migration
        
        Args:
            version: Migration version number
            name: Migration name
            filepath: Path to migration file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            print(f"\n▶ Applying migration {version}: {name}")
            
            # Load the migration module
            module = self.load_migration_module(filepath)
            
            # Check if upgrade function exists
            if not hasattr(module, 'upgrade'):
                print(f"  ✗ Migration {version} missing upgrade() function")
                return False
            
            # Execute migration
            start_time = datetime.now()
            module.upgrade(self.conn)
            end_time = datetime.now()
            
            execution_time_ms = int((end_time - start_time).total_seconds() * 1000)
            
            # Record migration in tracking table
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO schema_migrations (version, name, execution_time_ms) VALUES (?, ?, ?)",
                (version, name, execution_time_ms)
            )
            self.conn.commit()
            
            print(f"  ✓ Migration {version} applied successfully ({execution_time_ms}ms)")
            return True
            
        except Exception as e:
            print(f"  ✗ Migration {version} failed: {e}")
            self.conn.rollback()
            return False
    
    def run_migrations(self, dry_run: bool = False) -> Tuple[int, int]:
        """
        Run all pending migrations
        
        Args:
            dry_run: If True, only show what would be run without applying
            
        Returns:
            Tuple of (applied_count, failed_count)
        """
        print("\n" + "="*60)
        print("DATABASE MIGRATION RUNNER")
        print("="*60)
        print(f"Database: {self.db_path}")
        print(f"Migrations directory: {self.migrations_dir}")
        
        try:
            self.connect()
            self.ensure_migrations_table()
            
            # Get applied migrations
            applied = self.get_applied_migrations()
            print(f"\n✓ {len(applied)} migration(s) already applied")
            
            # Discover available migrations
            all_migrations = self.discover_migrations()
            print(f"✓ {len(all_migrations)} migration(s) discovered")
            
            # Find pending migrations
            pending = [
                (version, name, filepath)
                for version, name, filepath in all_migrations
                if version not in applied
            ]
            
            if not pending:
                print("\n✓ Database is up to date - no pending migrations")
                return (0, 0)
            
            print(f"\n📋 {len(pending)} pending migration(s) found:")
            for version, name, _ in pending:
                print(f"   - {version}: {name}")
            
            if dry_run:
                print("\n⚠ DRY RUN - No migrations applied")
                return (0, 0)
            
            # Apply pending migrations
            print("\n" + "-"*60)
            print("APPLYING MIGRATIONS")
            print("-"*60)
            
            applied_count = 0
            failed_count = 0
            
            for version, name, filepath in pending:
                if self.apply_migration(version, name, filepath):
                    applied_count += 1
                else:
                    failed_count += 1
                    # Stop on first failure
                    print("\n⚠ Stopping migration process due to error")
                    break
            
            # Summary
            print("\n" + "="*60)
            print("MIGRATION SUMMARY")
            print("="*60)
            print(f"✓ Applied: {applied_count}")
            if failed_count > 0:
                print(f"✗ Failed:  {failed_count}")
            print("="*60 + "\n")
            
            return (applied_count, failed_count)
            
        except Exception as e:
            print(f"\n✗ Migration runner error: {e}")
            import traceback
            traceback.print_exc()
            return (0, 1)
        
        finally:
            self.close()


def main():
    """Main entry point for migration runner"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Database Migration Runner")
    parser.add_argument(
        "--db",
        default="data/magazine_schedules.db",
        help="Path to database file (default: data/magazine_schedules.db)"
    )
    parser.add_argument(
        "--migrations-dir",
        help="Path to migrations directory (default: ./migrations)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show pending migrations without applying them"
    )
    
    args = parser.parse_args()
    
    runner = MigrationRunner(args.db, args.migrations_dir)
    applied, failed = runner.run_migrations(dry_run=args.dry_run)
    
    # Exit with error code if any migrations failed
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
