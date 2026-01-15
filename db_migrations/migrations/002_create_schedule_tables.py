"""
Migration 002: Create schedule and job_run tables

Creates tables for the magazine downloader scheduling system.
"""


def upgrade(conn):
    """Create schedule and job_run tables"""
    cursor = conn.cursor()
    
    # Check if schedule table already exists
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='schedule'
    """)
    
    if not cursor.fetchone():
        # Create schedule table
        cursor.execute("""
            CREATE TABLE schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                frequency VARCHAR(20) NOT NULL,
                time VARCHAR(20) NOT NULL,
                day_of_week INTEGER,
                day_of_month INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                active BOOLEAN DEFAULT 1 NOT NULL,
                CHECK (active IN (0, 1))
            )
        """)
        print("  ✓ Created schedule table")
    else:
        print("  ℹ Schedule table already exists, skipping")
    
    # Check if job_run table already exists
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='job_run'
    """)
    
    if not cursor.fetchone():
        # Create job_run table
        cursor.execute("""
            CREATE TABLE job_run (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id INTEGER,
                start_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP,
                logs TEXT,
                status VARCHAR(20),
                FOREIGN KEY (schedule_id) REFERENCES schedule (id)
            )
        """)
        print("  ✓ Created job_run table")
    else:
        print("  ℹ Job_run table already exists, skipping")
    
    conn.commit()


def downgrade(conn):
    """Drop schedule and job_run tables (rollback)"""
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS job_run")
    cursor.execute("DROP TABLE IF EXISTS schedule")
    conn.commit()
    print("  ✓ Dropped schedule and job_run tables")
