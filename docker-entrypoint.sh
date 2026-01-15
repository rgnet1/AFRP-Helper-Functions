#!/bin/bash
set -e

echo "=========================================="
echo "AFRP CRM Helper - Container Startup"
echo "=========================================="

# Ensure data directory exists
mkdir -p /app/data

# Run database migrations
echo ""
echo "Running database migrations..."
python3 /app/db_migrations/migration_runner.py --db /app/data/magazine_schedules.db

# Check migration exit code
if [ $? -ne 0 ]; then
    echo "⚠ Database migrations failed! Check logs above."
    echo "Application may not function correctly."
    # Continue anyway - don't block startup
fi

echo ""
echo "=========================================="
echo "Starting application server..."
echo "=========================================="

# Start the application with gunicorn
# The scheduler will be initialized by the app
exec gunicorn --bind 0.0.0.0:5066 --workers 1 --threads 2 app:app
