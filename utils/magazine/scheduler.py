from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import re
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from io import StringIO
from contextlib import redirect_stdout
import sys
import logging
import os
from logging.handlers import RotatingFileHandler

db = SQLAlchemy()

# Check if running in Docker
IN_DOCKER = os.environ.get('DOCKER_CONTAINER', False)
BASE_PATH = '/app' if IN_DOCKER else '.'

from utils.magazine.config import MagazineConfig

# Set up logging
config = MagazineConfig()
log_file = config.log_file

# Configure root logger
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Add console handler to show logs in terminal
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logging.getLogger().addHandler(console_handler)

# Create loggers with source identification
scheduler_logger = logging.getLogger('SCHEDULER')
job_logger = logging.getLogger('JOB')

class JobRun(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=True)  # Allow manual runs without schedule
    start_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    end_time = db.Column(db.DateTime)
    logs = db.Column(db.Text)
    status = db.Column(db.String(20))  # 'success' or 'error'

    schedule = db.relationship('Schedule', back_populates='runs')

def validate_time_format(time_str):
    """Validate time string format (HH:MM AM/PM)"""
    pattern = r'^(1[0-2]|0?[1-9]):([0-5][0-9]) (AM|PM)$'
    if not re.match(pattern, time_str):
        return False
    try:
        datetime.strptime(time_str, "%I:%M %p")
        return True
    except ValueError:
        return False

VALID_FREQUENCIES = ['daily', 'weekly', 'monthly']

class Schedule(db.Model):
    runs = db.relationship('JobRun', back_populates='schedule', order_by=JobRun.start_time.desc())
    id = db.Column(db.Integer, primary_key=True)
    _frequency = db.Column('frequency', db.String(20), nullable=False)  # 'daily', 'weekly', 'monthly'
    _time = db.Column('time', db.String(20), nullable=False)  # HH:MM AM/PM format
    _day_of_week = db.Column('day_of_week', db.Integer, nullable=True)  # 0-6 for weekly (0 is Monday)
    _day_of_month = db.Column('day_of_month', db.Integer, nullable=True)  # 1-31 for monthly
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    active = db.Column(db.Boolean, default=True)

    def __init__(self, **kwargs):
        super(Schedule, self).__init__(**kwargs)
        # Validate all fields on initialization
        self.frequency = kwargs.get('frequency')
        self.time = kwargs.get('time')
        self.day_of_week = kwargs.get('day_of_week')
        self.day_of_month = kwargs.get('day_of_month')

    @property
    def frequency(self):
        return self._frequency

    @frequency.setter
    def frequency(self, value):
        if value not in VALID_FREQUENCIES:
            raise ValueError(f"Invalid frequency. Must be one of: {', '.join(VALID_FREQUENCIES)}")
        self._frequency = value

    @property
    def time(self):
        return self._time

    @time.setter
    def time(self, value):
        if not value:
            raise ValueError("Time is required")
        if not validate_time_format(value):
            raise ValueError("Invalid time format. Use HH:MM AM/PM format (e.g., 09:30 AM)")
        self._time = value

    @property
    def day_of_week(self):
        return self._day_of_week

    @day_of_week.setter
    def day_of_week(self, value):
        if self._frequency == 'weekly':
            if value is None:
                raise ValueError("day_of_week is required for weekly schedules")
            if not isinstance(value, int) or value < 0 or value > 6:
                raise ValueError("day_of_week must be between 0 and 6")
        elif value is not None and self._frequency != 'weekly':
            raise ValueError("day_of_week should only be set for weekly schedules")
        self._day_of_week = value

    @property
    def day_of_month(self):
        return self._day_of_month

    @day_of_month.setter
    def day_of_month(self, value):
        if self._frequency == 'monthly':
            if value is None:
                raise ValueError("day_of_month is required for monthly schedules")
            if not isinstance(value, int) or value < 1 or value > 31:
                raise ValueError("day_of_month must be between 1 and 31")
        elif value is not None and self._frequency != 'monthly':
            raise ValueError("day_of_month should only be set for monthly schedules")
        self._day_of_month = value

    def get_cron_expression(self):
        try:
            # Convert time from AM/PM to 24-hour format
            time_obj = datetime.strptime(self.time, "%I:%M %p")
        except ValueError:
            scheduler_logger.error(f"Invalid time format for schedule {self.id}: {self.time}")
            raise ValueError(f"Invalid time format: {self.time}")
        hour = time_obj.hour
        minute = time_obj.minute
        
        if self.frequency == 'daily':
            return f'{minute} {hour} * * *'
        elif self.frequency == 'weekly' and self.day_of_week is not None:
            return f'{minute} {hour} * * {self.day_of_week}'
        elif self.frequency == 'monthly' and self.day_of_month is not None:
            return f'{minute} {hour} {self.day_of_month} * *'
        else:
            raise ValueError("Invalid schedule configuration")

class EventViewConfig(db.Model):
    """
    Stores Dynamics CRM view configurations for Badge Generator V2.
    Groups all 4 view IDs under a single event name for easy management.
    """
    __tablename__ = 'event_view_config'
    
    id = db.Column(db.Integer, primary_key=True)
    event_name = db.Column(db.String(200), unique=True, nullable=False)
    event_guests_view_id = db.Column(db.String(100), nullable=False)
    qr_codes_view_id = db.Column(db.String(100), nullable=False)
    table_reservations_view_id = db.Column(db.String(100), nullable=False)
    form_responses_view_id = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_default = db.Column(db.Boolean, default=False)
    
    def to_dict(self):
        """Convert model to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'event_name': self.event_name,
            'event_guests_view_id': self.event_guests_view_id,
            'qr_codes_view_id': self.qr_codes_view_id,
            'table_reservations_view_id': self.table_reservations_view_id,
            'form_responses_view_id': self.form_responses_view_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'is_default': self.is_default
        }

class ScheduleManager:
    def __init__(self, app=None):
        self.app = None
        self.scheduler = BackgroundScheduler(timezone=pytz.timezone('America/Los_Angeles'))
        self.scheduler.start()
        if app:
            self.init_app(app)

    def init_app(self, app):
        self.app = app
        from utils.magazine.download_latest_magazine import main as magazine_main
        
        # Load existing schedules from database
        with app.app_context():
            schedules = Schedule.query.filter_by(active=True).all()
            for schedule in schedules:
                try:
                    # Validate schedule before adding
                    if not validate_time_format(schedule.time):
                        scheduler_logger.error(f"Invalid time format for schedule {schedule.id}: {schedule.time}")
                        # Deactivate invalid schedule
                        schedule.active = False
                        db.session.commit()
                        continue

                    # Validate frequency-specific fields
                    if schedule.frequency == 'weekly' and (schedule.day_of_week is None or not 0 <= schedule.day_of_week <= 6):
                        scheduler_logger.error(f"Invalid day_of_week for weekly schedule {schedule.id}: {schedule.day_of_week}")
                        schedule.active = False
                        db.session.commit()
                        continue

                    if schedule.frequency == 'monthly' and (schedule.day_of_month is None or not 1 <= schedule.day_of_month <= 31):
                        scheduler_logger.error(f"Invalid day_of_month for monthly schedule {schedule.id}: {schedule.day_of_month}")
                        schedule.active = False
                        db.session.commit()
                        continue

                    self.add_job(schedule, magazine_main)
                    scheduler_logger.info(f"Successfully loaded schedule {schedule.id}")
                except Exception as e:
                    scheduler_logger.error(f"Error loading schedule {schedule.id}: {str(e)}")
                    # Deactivate schedule on error
                    schedule.active = False
                    db.session.commit()

    def job_exists(self, job_id):
        """Check if a job exists in the scheduler"""
        return any(job.id == job_id for job in self.scheduler.get_jobs())

    def add_job(self, schedule, func, replace_existing=True):
        """Add a new job to the scheduler"""
        job_id = f'magazine_download_{schedule.id}'
        
        try:
            cron_expression = schedule.get_cron_expression()
            trigger = CronTrigger.from_crontab(cron_expression)
        except ValueError as e:
            scheduler_logger.error(f"Failed to create cron expression for schedule {schedule.id}: {str(e)}")
            return False
        
        # Check if job already exists
        if self.job_exists(job_id):
            if not replace_existing:
                return False  # Don't replace existing job
            scheduler_logger.info(f"Replacing existing job {job_id}")
            self.scheduler.remove_job(job_id)
        
        def job_wrapper():
            # Create a new job run record
            job_run = JobRun(schedule_id=schedule.id)
            output = StringIO()
            
            try:
                job_logger.info(f"Starting job {job_id}")
                with redirect_stdout(output):
                    func()
                job_run.status = 'success'
                job_logger.info(f"Job {job_id} completed successfully")
            except Exception as e:
                job_run.status = 'error'
                error_msg = f"Error in job {job_id}: {str(e)}"
                print(error_msg, file=output)
                job_logger.error(error_msg)
            finally:
                job_run.end_time = datetime.utcnow()
                job_run.logs = output.getvalue()
                with self.app.app_context():
                    db.session.add(job_run)
                    # Keep only last 10 runs
                    old_runs = JobRun.query.filter_by(schedule_id=schedule.id).order_by(JobRun.start_time.desc()).offset(10).all()
                    for run in old_runs:
                        db.session.delete(run)
                    db.session.commit()
                    job_logger.info(f"Job {job_id} run record saved to database")
        
        # Add new job with wrapper
        self.scheduler.add_job(
            func=job_wrapper,
            trigger=trigger,
            id=job_id,
            name=f'Magazine Download - {schedule.frequency} at {schedule.time}'
        )

    def remove_job(self, schedule_id):
        """Remove a job from the scheduler"""
        job_id = f'magazine_download_{schedule_id}'
        if job_id in self.scheduler.get_jobs():
            self.scheduler.remove_job(job_id)

schedule_manager = ScheduleManager()
