#!/usr/bin/env python3
"""
AFRP CRM Helper - Restore Script

This script restores a backup created by backup.py

Usage:
    python3 backup/restore.py backup_folder_name [--dry-run]
    
Docker Usage:
    docker-compose exec afrp-helper python3 backup/restore.py backup_folder_name

IMPORTANT: Stop the application before restoring!
    docker-compose down
"""

import os
import sys
import shutil
import argparse
import json
from datetime import datetime
from pathlib import Path

# Check if running in Docker
IN_DOCKER = os.environ.get('DOCKER_CONTAINER', False)
BASE_PATH = '/app' if IN_DOCKER else '.'

# Define paths
DB_PATH = os.path.join(BASE_PATH, 'data', 'magazine_schedules.db')
BADGE_TEMPLATES_PATH = os.path.join(BASE_PATH, 'badge_templates')
BADGE_LOGOS_PATH = os.path.join(BASE_PATH, 'badge_logos')
CONFIG_PATH = '/config' if IN_DOCKER else os.path.join(BASE_PATH, 'config')
BACKUPS_PATH = os.path.join(BASE_PATH, 'backups')


def extract_backup(backup_path):
    """Extract backup if it's a compressed archive."""
    if backup_path.endswith('.tar.gz'):
        print(f"📦 Extracting compressed backup...")
        import tarfile
        
        extract_dir = os.path.dirname(backup_path)
        
        try:
            with tarfile.open(backup_path, "r:gz") as tar:
                tar.extractall(extract_dir)
            
            # Get the extracted folder name
            backup_name = os.path.basename(backup_path).replace('.tar.gz', '')
            extracted_path = os.path.join(extract_dir, backup_name)
            
            print(f"  ✓ Extracted to: {extracted_path}")
            return extracted_path, True  # True = we extracted it
            
        except Exception as e:
            print(f"  ✗ Extraction failed: {e}")
            return None, False
    
    return backup_path, False  # Not compressed


def verify_backup(backup_path):
    """Verify backup integrity and read manifest."""
    print("\n🔍 Verifying backup...")
    
    manifest_path = os.path.join(backup_path, 'BACKUP_MANIFEST.json')
    
    if not os.path.exists(manifest_path):
        print("  ✗ Manifest file not found - invalid backup")
        return None
    
    try:
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        
        print(f"  ✓ Backup Version: {manifest.get('backup_version', 'Unknown')}")
        print(f"  ✓ Created: {manifest.get('backup_date', 'Unknown')}")
        print(f"  ✓ Environment: {manifest.get('environment', 'Unknown')}")
        
        # Verify expected directories exist
        required_dirs = ['database']
        for dir_name in required_dirs:
            dir_path = os.path.join(backup_path, dir_name)
            if not os.path.exists(dir_path):
                print(f"  ⚠ Warning: {dir_name} directory not found")
        
        return manifest
        
    except Exception as e:
        print(f"  ✗ Failed to read manifest: {e}")
        return None


def create_backup_of_current(suffix='pre_restore'):
    """Create a backup of current state before restoring."""
    print("\n💾 Creating safety backup of current state...")
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safety_backup_name = f'afrp_backup_{suffix}_{timestamp}'
    safety_backup_path = os.path.join(BACKUPS_PATH, safety_backup_name)
    
    os.makedirs(safety_backup_path, exist_ok=True)
    
    # Backup current database
    if os.path.exists(DB_PATH):
        db_backup = os.path.join(safety_backup_path, 'database')
        os.makedirs(db_backup, exist_ok=True)
        shutil.copy2(DB_PATH, os.path.join(db_backup, 'magazine_schedules.db'))
        print(f"  ✓ Current database backed up")
    
    # Backup templates and logos
    for source, name in [
        (BADGE_TEMPLATES_PATH, 'badge_templates'),
        (BADGE_LOGOS_PATH, 'badge_logos')
    ]:
        if os.path.exists(source) and os.listdir(source):
            dest = os.path.join(safety_backup_path, name)
            shutil.copytree(source, dest, dirs_exist_ok=True)
            print(f"  ✓ Current {name} backed up")
    
    print(f"  ✓ Safety backup created: {safety_backup_path}")
    return safety_backup_path


def restore_database(backup_path, dry_run=False):
    """Restore database from backup."""
    print("\n📊 Restoring database...")
    
    source_db = os.path.join(backup_path, 'database', 'magazine_schedules.db')
    
    if not os.path.exists(source_db):
        print("  ⚠ Database backup not found")
        return False
    
    if dry_run:
        print(f"  [DRY RUN] Would restore: {source_db} -> {DB_PATH}")
        return True
    
    try:
        # Ensure data directory exists
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        
        # Remove existing database
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        
        # Copy backup database
        shutil.copy2(source_db, DB_PATH)
        
        # Verify restored database
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        conn.close()
        
        if result[0] == 'ok':
            print("  ✓ Database restored and verified")
            
            # Show stats if available
            stats_file = os.path.join(backup_path, 'database', 'db_stats.json')
            if os.path.exists(stats_file):
                with open(stats_file, 'r') as f:
                    stats = json.load(f)
                print("  ✓ Restored tables:")
                for table, count in stats.items():
                    print(f"    - {table}: {count} records")
            
            return True
        else:
            print(f"  ✗ Database integrity check failed: {result[0]}")
            return False
            
    except Exception as e:
        print(f"  ✗ Database restore failed: {e}")
        return False


def restore_directory(backup_path, dest_path, name, dry_run=False):
    """Restore a directory from backup."""
    backup_dir = os.path.join(backup_path, name.lower().replace(' ', '_'))
    
    if not os.path.exists(backup_dir):
        print(f"  ⚠ {name} backup not found")
        return True  # Not critical
    
    if dry_run:
        file_count = sum(len(files) for _, _, files in os.walk(backup_dir))
        print(f"  [DRY RUN] Would restore {file_count} files to: {dest_path}")
        return True
    
    try:
        # Clear existing directory
        if os.path.exists(dest_path):
            shutil.rmtree(dest_path)
        
        # Copy backup directory
        shutil.copytree(backup_dir, dest_path)
        
        file_count = sum(len(files) for _, _, files in os.walk(dest_path))
        print(f"  ✓ {name} restored: {file_count} files")
        return True
        
    except Exception as e:
        print(f"  ✗ {name} restore failed: {e}")
        return False


def restore_config(backup_path, dry_run=False):
    """Restore configuration files from backup."""
    print("\n⚙️  Restoring configuration...")
    
    backup_config = os.path.join(backup_path, 'config')
    
    if not os.path.exists(backup_config):
        print("  ⚠ Config backup not found")
        return True  # Not critical
    
    if dry_run:
        items = len(os.listdir(backup_config))
        print(f"  [DRY RUN] Would restore {items} config items")
        return True
    
    try:
        # Ensure config directory exists
        os.makedirs(CONFIG_PATH, exist_ok=True)
        
        # Copy config files (excluding .env which should not be in backup)
        restored = 0
        for item in os.listdir(backup_config):
            source = os.path.join(backup_config, item)
            dest = os.path.join(CONFIG_PATH, item)
            
            if os.path.isfile(source):
                shutil.copy2(source, dest)
                restored += 1
            elif os.path.isdir(source):
                if os.path.exists(dest):
                    shutil.rmtree(dest)
                shutil.copytree(source, dest)
                restored += 1
        
        print(f"  ✓ Configuration restored: {restored} items")
        return True
        
    except Exception as e:
        print(f"  ✗ Config restore failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Restore AFRP CRM Helper from backup',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 backup/restore.py afrp_backup_20260115_120000
  python3 backup/restore.py afrp_backup_20260115_120000.tar.gz
  python3 backup/restore.py afrp_backup_20260115_120000 --dry-run
  
Docker:
  docker-compose down
  docker-compose exec afrp-helper python3 backup/restore.py backup_name
  docker-compose up -d

WARNING: This will replace your current data!
        """
    )
    
    parser.add_argument(
        'backup_name',
        help='Name of backup folder or .tar.gz file'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be restored without making changes'
    )
    
    parser.add_argument(
        '--skip-safety-backup',
        action='store_true',
        help='Skip creating safety backup of current state'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("AFRP CRM Helper - System Restore")
    print("=" * 60)
    print(f"Environment: {'Docker' if IN_DOCKER else 'Local'}")
    print(f"Backup: {args.backup_name}")
    print(f"Dry Run: {'Yes' if args.dry_run else 'No'}")
    print("=" * 60)
    
    # Find backup path
    backup_path = args.backup_name
    
    # If just a name, look in backups directory
    if not os.path.exists(backup_path):
        backup_path = os.path.join(BACKUPS_PATH, args.backup_name)
    
    # If ends with .tar.gz, try that
    if not os.path.exists(backup_path) and not backup_path.endswith('.tar.gz'):
        backup_path = backup_path + '.tar.gz'
    
    if not os.path.exists(backup_path):
        print(f"\n✗ Backup not found: {args.backup_name}")
        print(f"  Searched: {backup_path}")
        return 1
    
    # Extract if compressed
    backup_path, was_extracted = extract_backup(backup_path)
    if backup_path is None:
        return 1
    
    # Verify backup
    manifest = verify_backup(backup_path)
    if manifest is None:
        return 1
    
    # Confirm restore
    if not args.dry_run:
        print("\n" + "⚠️ " * 20)
        print("WARNING: This will REPLACE your current data!")
        print("A safety backup will be created first.")
        print("⚠️ " * 20)
        
        response = input("\nType 'yes' to continue: ")
        if response.lower() != 'yes':
            print("\n✗ Restore cancelled")
            # Clean up extracted backup if we extracted it
            if was_extracted:
                shutil.rmtree(backup_path)
            return 0
    
    # Create safety backup of current state
    if not args.skip_safety_backup and not args.dry_run:
        safety_backup = create_backup_of_current()
    
    # Perform restore
    success = True
    
    # Restore database
    if not restore_database(backup_path, args.dry_run):
        success = False
    
    # Restore badge templates
    print("\n🎨 Restoring badge templates...")
    if not restore_directory(backup_path, BADGE_TEMPLATES_PATH, 'Badge Templates', args.dry_run):
        success = False
    
    # Restore badge logos
    print("\n🖼️  Restoring badge logos...")
    if not restore_directory(backup_path, BADGE_LOGOS_PATH, 'Badge Logos', args.dry_run):
        success = False
    
    # Restore configuration
    if not restore_config(backup_path, args.dry_run):
        success = False
    
    # Clean up extracted backup if we extracted it
    if was_extracted:
        try:
            shutil.rmtree(backup_path)
        except:
            pass
    
    # Summary
    print("\n" + "=" * 60)
    if args.dry_run:
        print("✅ Dry run completed - no changes made")
        print("   Remove --dry-run flag to perform actual restore")
    elif success:
        print("✅ Restore completed successfully!")
        print("\nNext steps:")
        print("  1. Start the application: docker-compose up -d")
        print("  2. Verify at: http://localhost:5066")
        if not args.skip_safety_backup:
            print(f"\n💾 Safety backup created: {os.path.basename(safety_backup)}")
            print("   You can restore it if something went wrong")
    else:
        print("⚠️  Restore completed with errors")
        print("   Review the output above for details")
        if not args.skip_safety_backup:
            print(f"\n💾 Safety backup available: {os.path.basename(safety_backup)}")
    print("=" * 60)
    
    return 0 if success else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Restore cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
