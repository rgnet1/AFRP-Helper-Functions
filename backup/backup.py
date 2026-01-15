#!/usr/bin/env python3
"""
AFRP CRM Helper - Backup Script

This script creates a complete backup of the system including:
- SQLite database (users, schedules, templates)
- Badge templates (SVG files)
- Badge logos (uploaded club logos)
- Configuration files

Usage:
    python3 backup/backup.py [--output-dir /path/to/backups] [--compress]
    
Docker Usage:
    docker-compose exec afrp-helper python3 backup/backup.py
"""

import os
import sys
import shutil
import sqlite3
import argparse
from datetime import datetime
from pathlib import Path
import json

# Check if running in Docker
IN_DOCKER = os.environ.get('DOCKER_CONTAINER', False)
BASE_PATH = '/app' if IN_DOCKER else '.'

# Define paths
DB_PATH = os.path.join(BASE_PATH, 'data', 'magazine_schedules.db')
BADGE_TEMPLATES_PATH = os.path.join(BASE_PATH, 'badge_templates')
BADGE_LOGOS_PATH = os.path.join(BASE_PATH, 'badge_logos')
CONFIG_PATH = '/config' if IN_DOCKER else os.path.join(BASE_PATH, 'config')

# Default backup directory
DEFAULT_BACKUP_DIR = os.path.join(BASE_PATH, 'backups')


def create_backup_directory(output_dir):
    """Create timestamped backup directory."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'afrp_backup_{timestamp}'
    backup_path = os.path.join(output_dir, backup_name)
    
    os.makedirs(backup_path, exist_ok=True)
    print(f"✓ Created backup directory: {backup_path}")
    return backup_path, backup_name


def backup_database(backup_path):
    """Backup SQLite database with integrity check."""
    print("\n📊 Backing up database...")
    
    if not os.path.exists(DB_PATH):
        print(f"⚠ Database not found at: {DB_PATH}")
        return False
    
    try:
        # Verify database integrity before backup
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        
        if result[0] != 'ok':
            print(f"⚠ Database integrity check failed: {result[0]}")
            conn.close()
            return False
        
        # Get database statistics
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        stats = {}
        for table in tables:
            table_name = table[0]
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            stats[table_name] = count
        
        conn.close()
        
        # Copy database file
        db_backup_path = os.path.join(backup_path, 'database')
        os.makedirs(db_backup_path, exist_ok=True)
        shutil.copy2(DB_PATH, os.path.join(db_backup_path, 'magazine_schedules.db'))
        
        # Save database statistics
        with open(os.path.join(db_backup_path, 'db_stats.json'), 'w') as f:
            json.dump(stats, f, indent=2)
        
        print("  ✓ Database backed up successfully")
        print(f"  ✓ Tables backed up: {', '.join(stats.keys())}")
        for table, count in stats.items():
            print(f"    - {table}: {count} records")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Database backup failed: {e}")
        return False


def backup_directory(source_path, backup_path, name):
    """Backup a directory recursively."""
    if not os.path.exists(source_path):
        print(f"  ⚠ {name} directory not found at: {source_path}")
        return 0
    
    dest_path = os.path.join(backup_path, name.lower().replace(' ', '_'))
    
    try:
        # Count files before copying
        file_count = sum(len(files) for _, _, files in os.walk(source_path))
        
        if file_count == 0:
            print(f"  ⚠ No files found in {name}")
            return 0
        
        shutil.copytree(source_path, dest_path, dirs_exist_ok=True)
        print(f"  ✓ {name} backed up: {file_count} files")
        return file_count
        
    except Exception as e:
        print(f"  ✗ {name} backup failed: {e}")
        return 0


def backup_config(backup_path):
    """Backup configuration files (excluding sensitive .env)."""
    print("\n⚙️  Backing up configuration...")
    
    if not os.path.exists(CONFIG_PATH):
        print(f"  ⚠ Config directory not found at: {CONFIG_PATH}")
        return False
    
    config_backup_path = os.path.join(backup_path, 'config')
    os.makedirs(config_backup_path, exist_ok=True)
    
    backed_up = 0
    try:
        for item in os.listdir(CONFIG_PATH):
            # Skip .env files (sensitive data)
            if item.startswith('.env'):
                print(f"  ⊘ Skipping {item} (sensitive)")
                continue
            
            source = os.path.join(CONFIG_PATH, item)
            dest = os.path.join(config_backup_path, item)
            
            if os.path.isfile(source):
                shutil.copy2(source, dest)
                backed_up += 1
            elif os.path.isdir(source):
                shutil.copytree(source, dest, dirs_exist_ok=True)
                backed_up += 1
        
        print(f"  ✓ Configuration backed up: {backed_up} items")
        return True
        
    except Exception as e:
        print(f"  ✗ Config backup failed: {e}")
        return False


def create_manifest(backup_path, stats):
    """Create a manifest file with backup information."""
    manifest = {
        'backup_date': datetime.now().isoformat(),
        'backup_version': '1.0',
        'system': 'AFRP CRM Helper',
        'environment': 'Docker' if IN_DOCKER else 'Local',
        'statistics': stats,
        'contents': {
            'database': 'SQLite database with users, schedules, and templates',
            'badge_templates': 'User-uploaded SVG badge templates',
            'badge_logos': 'User-uploaded club logos',
            'config': 'Configuration files (excluding .env)'
        },
        'restore_instructions': [
            '1. Stop the application: docker-compose down',
            '2. Run restore script: python3 restore.py backup_folder_name',
            '3. Start the application: docker-compose up -d',
            '4. Verify at http://localhost:5066'
        ]
    }
    
    manifest_path = os.path.join(backup_path, 'BACKUP_MANIFEST.json')
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    # Also create a README
    readme_path = os.path.join(backup_path, 'README.txt')
    with open(readme_path, 'w') as f:
        f.write("AFRP CRM Helper - Backup\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Backup Date: {manifest['backup_date']}\n")
        f.write(f"Environment: {manifest['environment']}\n\n")
        f.write("Contents:\n")
        for key, desc in manifest['contents'].items():
            f.write(f"  - {key}/: {desc}\n")
        f.write("\n")
        f.write("Statistics:\n")
        for key, value in stats.items():
            f.write(f"  - {key}: {value}\n")
        f.write("\n")
        f.write("To Restore:\n")
        for step in manifest['restore_instructions']:
            f.write(f"  {step}\n")
    
    print(f"\n✓ Manifest created: {manifest_path}")


def compress_backup(backup_path, backup_name):
    """Compress the backup directory into a tar.gz file."""
    print("\n📦 Compressing backup...")
    
    try:
        import tarfile
        
        parent_dir = os.path.dirname(backup_path)
        archive_path = os.path.join(parent_dir, f"{backup_name}.tar.gz")
        
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(backup_path, arcname=backup_name)
        
        # Get archive size
        size_mb = os.path.getsize(archive_path) / (1024 * 1024)
        print(f"  ✓ Compressed: {archive_path}")
        print(f"  ✓ Size: {size_mb:.2f} MB")
        
        # Remove uncompressed directory
        shutil.rmtree(backup_path)
        print(f"  ✓ Removed uncompressed backup")
        
        return archive_path
        
    except Exception as e:
        print(f"  ✗ Compression failed: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description='Backup AFRP CRM Helper system data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 backup/backup.py
  python3 backup/backup.py --output-dir /backups
  python3 backup/backup.py --compress
  
Docker:
  docker-compose exec afrp-helper python3 backup/backup.py
  docker-compose exec afrp-helper python3 backup/backup.py --compress
        """
    )
    
    parser.add_argument(
        '--output-dir',
        default=DEFAULT_BACKUP_DIR,
        help=f'Output directory for backups (default: {DEFAULT_BACKUP_DIR})'
    )
    
    parser.add_argument(
        '--compress',
        action='store_true',
        help='Compress backup into .tar.gz file'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("AFRP CRM Helper - System Backup")
    print("=" * 60)
    print(f"Environment: {'Docker' if IN_DOCKER else 'Local'}")
    print(f"Output directory: {args.output_dir}")
    print(f"Compression: {'Enabled' if args.compress else 'Disabled'}")
    print("=" * 60)
    
    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Create backup directory
    backup_path, backup_name = create_backup_directory(args.output_dir)
    
    # Track statistics
    stats = {}
    success = True
    
    # Backup database
    if backup_database(backup_path):
        stats['Database'] = 'Backed up'
    else:
        stats['Database'] = 'Failed'
        success = False
    
    # Backup badge templates
    print("\n🎨 Backing up badge templates...")
    template_count = backup_directory(BADGE_TEMPLATES_PATH, backup_path, 'Badge Templates')
    stats['Badge Templates'] = f"{template_count} files"
    
    # Backup badge logos
    print("\n🖼️  Backing up badge logos...")
    logo_count = backup_directory(BADGE_LOGOS_PATH, backup_path, 'Badge Logos')
    stats['Badge Logos'] = f"{logo_count} files"
    
    # Backup configuration
    if backup_config(backup_path):
        stats['Configuration'] = 'Backed up'
    else:
        stats['Configuration'] = 'Failed'
    
    # Create manifest
    create_manifest(backup_path, stats)
    
    # Compress if requested
    if args.compress:
        archive_path = compress_backup(backup_path, backup_name)
        if archive_path:
            final_path = archive_path
        else:
            final_path = backup_path
    else:
        final_path = backup_path
    
    # Summary
    print("\n" + "=" * 60)
    if success:
        print("✅ Backup completed successfully!")
        print(f"📁 Backup location: {final_path}")
        print("\nTo restore this backup, run:")
        print(f"  python3 restore.py {os.path.basename(final_path).replace('.tar.gz', '')}")
    else:
        print("⚠️  Backup completed with warnings")
        print(f"📁 Backup location: {final_path}")
        print("⚠️  Review the output above for details")
    print("=" * 60)
    
    return 0 if success else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Backup cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
