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
# %(U)s is the path without the query string so id_token never appears in access logs.
exec gunicorn --bind 0.0.0.0:5066 --workers 1 --threads 2 --timeout 120 \
  --access-logformat '%(h)s %(l)s %(u)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(b)s' \
  app:app
