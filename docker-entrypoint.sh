#!/bin/bash
set -e

# Initialize SQLite database if it doesn't exist
if [ ! -f "/app/data/magazine.db" ]; then
    echo "Initializing database..."
    python -c "
from app import app, db
with app.app_context():
    db.create_all()
"
fi

# Start the application with gunicorn
# The scheduler will be initialized by the app
exec gunicorn --bind 0.0.0.0:5066 --workers 1 --threads 2 app:app
