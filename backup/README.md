# Backup & Restore Scripts

This folder contains all backup and restore utilities for the AFRP CRM Helper system.

## Files

- **backup.py** - Python script for creating system backups
- **restore.py** - Python script for restoring from backups  
- **backup.sh** - Bash wrapper for easier backup execution

## Quick Start

### Creating a Backup

```bash
# From Docker (recommended)
docker-compose exec afrp-helper python3 backup/backup.py --compress

# Using bash wrapper
./backup/backup.sh --compress

# From local machine
python3 backup/backup.py --compress
```

### Restoring a Backup

```bash
# Stop application first
docker-compose down

# Restore from backup
docker-compose exec afrp-helper python3 backup/restore.py afrp_backup_20260115_120000

# Start application
docker-compose up -d
```

## Documentation

For complete documentation, see:
- **User Guide**: Main [README.md](../README.md) - "Backup & Restore" section
- **Developer Guide**: [.cursor/rules/backup-restore-system.mdc](../.cursor/rules/backup-restore-system.mdc)

## What Gets Backed Up

✅ Database (users, schedules, templates)  
✅ Badge templates (SVG files)  
✅ Badge logos (uploaded images)  
✅ Configuration files (excluding .env)

## Options

### backup.py
```bash
python3 backup/backup.py [options]

Options:
  --output-dir DIR    Output directory (default: ./backups)
  --compress          Create .tar.gz archive
  -h, --help          Show help
```

### restore.py
```bash
python3 backup/restore.py backup_name [options]

Options:
  --dry-run               Preview without applying
  --skip-safety-backup    Skip pre-restore backup
  -h, --help              Show help
```

### backup.sh
```bash
./backup/backup.sh [--compress]

Interactive wrapper that detects Docker environment and guides you through the backup process.
```

## Safety Features

- ✅ Automatic pre-restore safety backup
- ✅ Database integrity verification
- ✅ Dry-run mode for testing
- ✅ Detailed backup manifests

## Examples

```bash
# Compressed backup
python3 backup/backup.py --compress

# Custom output directory
python3 backup/backup.py --output-dir /mnt/external/backups --compress

# Dry run restore (test without changes)
python3 backup/restore.py afrp_backup_20260115_120000 --dry-run

# Actual restore
python3 backup/restore.py afrp_backup_20260115_120000
```
