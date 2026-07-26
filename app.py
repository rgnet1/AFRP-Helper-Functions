from flask import Flask, render_template, request, send_file, send_from_directory, jsonify, Response, flash, redirect, url_for
from werkzeug.utils import secure_filename
from flask_login import LoginManager, login_required, current_user, login_user, logout_user
from flask_bcrypt import Bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import qrcode
from io import BytesIO, StringIO
from PIL import Image
import numpy as np
import sys
import threading
import queue
from datetime import datetime, time, timedelta
import time as pytime
import uuid
import re
from contextlib import redirect_stdout
import logging
import atexit
import shutil
import tempfile
import traceback
from utils.url_generator import extract_event_id, generate_event_registration_url, generate_event_summary_url
from utils.auth import (
    validate_password,
    validate_username,
    validate_email,
    FEATURES,
    user_can_access_path,
    permissions_from_form,
    path_is_public,
    path_requires_admin,
    feature_for_path,
)
from utils.auth.campaign_access import (
    CampaignAccessDenied,
    assert_campaign_access,
    assert_sub_event_access,
    annotate_campaigns_for_user,
    campaign_access_metadata,
)
from utils.magazine.download_latest_magazine import main as magazine_main
from utils.magazine.scheduler import db, Schedule, JobRun, schedule_manager, EventViewConfig, BadgeTemplate, User, PreprocessingTemplate
from utils.badges.pre_processing_module import PreprocessingBase
from utils.badges.event_preprocessing import preprocessing_implementations
from utils.badges.event_preprocessing.default import DefaultPreprocessing
from utils.badges.file_validator import FileValidator, FileTypes
from utils.badges.convert_to_mail_merge_v3 import EventRegistrationProcessorV3
from utils.badges.data_store import (
    BadgeDataStore,
    InsufficientMemoryError,
    PipelineBusyError,
    badge_pipeline_job,
    pull_campaign_to_store,
)
from utils.badges.badge_generator import (
    BadgeGenerator,
    probe_image_dimensions,
    validate_template_club_logo,
)
from utils.badges.badge_assets import load_badge_scale_js
from utils.badges.background_templates import (
    list_backgrounds,
    validate_background_image,
    register_upload,
    delete_background,
)
from utils.dynamics_crm import DynamicsCRMClient
from utils.badges.meal_options import aggregate_meal_options
import os
import json
import gc
import pandas as pd
from utils.badges.pre_processing_module import PreprocessingConfig
from typing import Dict, Type

# ============================================================================
# In-memory badge generation job tracking (for UI progress updates)
# ============================================================================

_BADGE_JOB_LOCK = threading.Lock()
_BADGE_JOBS: Dict[str, dict] = {}


def _cleanup_badge_jobs():
    """Remove old job records (and any leftover output PDFs)."""
    cutoff = datetime.utcnow() - timedelta(hours=2)
    with _BADGE_JOB_LOCK:
        stale_ids = [
            job_id
            for job_id, job in _BADGE_JOBS.items()
            if job.get("created_at") and job["created_at"] < cutoff
        ]
        for job_id in stale_ids:
            job = _BADGE_JOBS.pop(job_id, None)
            if not job:
                continue
            output_path = job.get("output_pdf_path")
            try:
                if output_path and os.path.exists(output_path):
                    os.remove(output_path)
            except Exception:
                pass


def _init_badge_job(phase: str, download_name: str = "badges.pdf") -> str:
    _cleanup_badge_jobs()
    job_id = str(uuid.uuid4())
    with _BADGE_JOB_LOCK:
        _BADGE_JOBS[job_id] = {
            "id": job_id,
            "status": "running",  # running|completed|failed
            "phase": phase,
            "message": "Starting...",
            "current": 0,
            "total": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "error": None,
            "output_pdf_path": None,
            "download_name": download_name,
        }
    return job_id


def _update_badge_job(job_id: str, **updates) -> None:
    with _BADGE_JOB_LOCK:
        job = _BADGE_JOBS.get(job_id)
        if not job:
            return
        job.update(updates)
        job["updated_at"] = datetime.utcnow()


def _get_badge_job(job_id: str) -> dict:
    with _BADGE_JOB_LOCK:
        job = _BADGE_JOBS.get(job_id)
        return dict(job) if job else {}


def _resolve_badge_club_logo(template, svg_path=None):
    """Resolve club logo path and validate template logo requirements."""
    if svg_path is None:
        svg_path = resolve_badge_svg_path(template)
    club_logo_path = None
    if template.club_logo_filename:
        candidate = os.path.join(app.config['BADGE_LOGOS_FOLDER'], template.club_logo_filename)
        if os.path.exists(candidate):
            club_logo_path = candidate
    error = validate_template_club_logo(svg_path, club_logo_path)
    return club_logo_path, error


def _template_element_layout(template):
    raw = getattr(template, 'element_layout', None) or '{}'
    if isinstance(raw, str):
        return json.loads(raw) if raw else {}
    return raw or {}


def _template_display_name_config(template):
    raw = getattr(template, 'display_name_config', None) or '{}'
    if isinstance(raw, str):
        return json.loads(raw) if raw else {}
    return raw or {}


def _template_meal_preference_mappings(template):
    raw = getattr(template, 'meal_preference_mappings', None) or '{}'
    if isinstance(raw, str):
        return json.loads(raw) if raw else {}
    return raw or {}


def _template_meal_preference_sources(template):
    raw = getattr(template, 'meal_preference_sources', None) or '{}'
    if isinstance(raw, str):
        return json.loads(raw) if raw else {}
    return raw or {}


def _preprocessing_template_by_id(preprocessing_template_id):
    if not preprocessing_template_id:
        return None
    try:
        from utils.magazine.scheduler import PreprocessingTemplate
        return PreprocessingTemplate.query.get(int(preprocessing_template_id))
    except (TypeError, ValueError):
        return None


def _meal_config_from_preprocessing_template_id(preprocessing_template_id):
    template = _preprocessing_template_by_id(preprocessing_template_id)
    if not template:
        return {}, {}
    return (
        _template_meal_preference_mappings(template),
        _template_meal_preference_sources(template),
    )


def _badge_generator_meal_kwargs(preprocessing_template_id):
    mappings, sources = _meal_config_from_preprocessing_template_id(
        preprocessing_template_id
    )
    return {
        'meal_preference_mappings': mappings,
        'meal_preference_sources': sources,
    }


def _campaign_access_denied_response(exc: CampaignAccessDenied):
    logger.warning(
        "Campaign access denied for user %s: %s",
        getattr(current_user, 'username', '?'),
        exc.message,
    )
    return jsonify({'error': exc.message}), 403


def _require_campaign_access(user, campaign_id, sub_event=None, crm_client=None):
    """Return a Flask error response if access is denied, else None."""
    try:
        assert_campaign_access(user, campaign_id)
        if sub_event:
            client = crm_client or DynamicsCRMClient()
            assert_sub_event_access(user, campaign_id, sub_event, client)
    except CampaignAccessDenied as exc:
        if user is current_user:
            return _campaign_access_denied_response(exc)
        logger.warning(
            "Campaign access denied for user %s: %s",
            getattr(user, 'username', '?'),
            exc.message,
        )
        return jsonify({'error': exc.message}), 403
    return None


def _resolve_campaign_id(campaign_id, campaign_name, crm_client):
    """Resolve campaign id from id or name. Returns (campaign_id, error_response)."""
    if campaign_name and not campaign_id:
        campaign_info = crm_client.get_campaign_by_name(campaign_name)
        if not campaign_info:
            return None, (jsonify({'error': f'Campaign {campaign_name} not found'}), 404)
        campaign_id = campaign_info['id']
    return campaign_id, None


def _copy_badge_sources_to_dir(source_dir: str, dest_dir: str) -> None:
    """Copy Parquet/Excel CRM sources into a processing temp directory."""
    paths = BadgeDataStore.find_source_paths(source_dir)
    for file_type in FileValidator.get_required_file_types():
        src = paths[file_type]
        dest = os.path.join(dest_dir, os.path.basename(src))
        shutil.copy2(src, dest)
        logger.debug("Copied %s source to %s", file_type, dest)


def _resolve_preprocessor_class(preprocessing_template_id):
    preprocessor_class = None
    if preprocessing_template_id:
        try:
            template = PreprocessingTemplate.query.get(int(preprocessing_template_id))
            if template:
                logger.info("Using database preprocessing template: %s", template.name)
                preprocessor_class = create_preprocessor_from_template(template)
            else:
                logger.warning(
                    "Preprocessing template %s not found, using default",
                    preprocessing_template_id,
                )
        except Exception as exc:
            logger.error("Error loading preprocessing template: %s", exc)
    if not preprocessor_class:
        logger.info("No preprocessing template selected, using default")
        preprocessor_class = DefaultPreprocessing
    return preprocessor_class


def _user_role_from_form(form):
    role = (form.get('role') or User.ROLE_USER).strip()
    if role not in User.VALID_ROLES:
        role = User.ROLE_USER
    return role


def _apply_user_access_from_form(user, form):
    """Apply role, campaign assignment, and feature permissions from admin form."""
    role = _user_role_from_form(form)
    assigned_id = (form.get('assigned_campaign_id') or '').strip()
    assigned_name = (form.get('assigned_campaign_name') or '').strip()

    if role == User.ROLE_EVENT_COORDINATOR and not assigned_id:
        raise ValueError('Assigned campaign is required for Event Coordinator role')

    user.apply_role(role, assigned_id, assigned_name)
    if role == User.ROLE_USER:
        user.set_feature_permissions(permissions_from_form(form))


def _preprocessing_config_with_meal(
    preprocessing_template_id,
    *,
    main_event,
    sub_event=None,
    inclusion_list=None,
    created_on_filter=None,
    group_by_household=False,
    household_cache_path=None,
):
    mappings, sources = _meal_config_from_preprocessing_template_id(
        preprocessing_template_id
    )
    return PreprocessingConfig(
        main_event=main_event,
        sub_event=sub_event,
        inclusion_list=inclusion_list,
        created_on_filter=created_on_filter,
        group_by_household=group_by_household,
        household_cache_path=household_cache_path,
        meal_preference_mappings=mappings or None,
        meal_preference_sources=sources or None,
    )

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Redact secrets from every log record so credentials are never written to logs.
from utils.log_redaction import install_secret_redaction
install_secret_redaction()

# Log that the script is starting
logger.info("Starting app.py...")

# Check if running in Docker
IN_DOCKER = os.environ.get('DOCKER_CONTAINER', False)
# Resolve BASE_PATH to an absolute path so resource lookups (logos, templates,
# uploads) keep working even when other code temporarily changes the process
# working directory via os.chdir() (e.g. preprocessing in /api/badges/pull-process-generate).
BASE_PATH = '/app' if IN_DOCKER else os.path.abspath(os.path.dirname(__file__))

# Ensure required directories exist with proper permissions
for dir_path in ['data', 'temp', 'downloads', 'badge_templates', 'badge_logos', 'badge_background_templates']:
    full_path = os.path.join(BASE_PATH, dir_path)
    os.makedirs(full_path, exist_ok=True)
    os.chmod(full_path, 0o777)

# Helper function to create a preprocessor class from a database template
def create_preprocessor_from_template(template):
    """Create a dynamic preprocessor class from a database template."""
    from utils.badges.pre_processing_module import PreprocessingBase, PreprocessingConfig
    import pandas as pd
    
    class DynamicPreprocessor(PreprocessingBase):
        """Dynamically created preprocessor from database template."""
        
        def __init__(self, config=None):
            self.config = config
            self._value_mappings = template.value_mappings if isinstance(template.value_mappings, dict) else json.loads(template.value_mappings or '{}')
            self._contains_mappings = template.contains_mappings if isinstance(template.contains_mappings, dict) else json.loads(template.contains_mappings or '{}')
        
        def get_value_mappings(self):
            return self._value_mappings
        
        def get_contains_mappings(self):
            return self._contains_mappings
        
        def preprocess_dataframe(self, df):
            return super().preprocess_dataframe(df)
    
    return DynamicPreprocessor

# Initialize Flask app
app = Flask(__name__)

# Set port based on environment
PORT = 5066 if IN_DOCKER else 5000

# Set database URI based on environment
if IN_DOCKER:
    db_uri = 'sqlite:////app/data/magazine_schedules.db'
else:
    # For local development, use absolute path
    db_path = os.path.join(os.getcwd(), 'data', 'magazine_schedules.db')
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    db_uri = f'sqlite:///{db_path}'

app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Load SECRET_KEY from environment
# Note: Environment variables are loaded from config/.env via docker-compose
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', '')

# Validate SECRET_KEY is configured
if not app.config.get('SECRET_KEY') or app.config['SECRET_KEY'] == '':
    raise RuntimeError(
        "SECRET_KEY is not set! "
        "Please set SECRET_KEY in config/.env file. "
        "Generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
    )

# Session configuration for security
app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS only
app.config['SESSION_COOKIE_HTTPONLY'] = True  # No JavaScript access
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)  # Session timeout
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)  # Remember me duration
app.config['REMEMBER_COOKIE_SECURE'] = True  # HTTPS only
app.config['REMEMBER_COOKIE_HTTPONLY'] = True  # No JavaScript access

logger.info(f"Database URI configured: {db_uri}")

# Initialize extensions
db.init_app(app)

# Initialize authentication extensions
bcrypt = Bcrypt(app)
# Store bcrypt in app.extensions so User model can access it
app.extensions['bcrypt'] = bcrypt
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.session_protection = 'strong'

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

@login_manager.user_loader
def load_user(user_id):
    """Load user for Flask-Login."""
    from utils.magazine.scheduler import User
    return User.query.get(int(user_id))

# Create database tables
with app.app_context():
    db.create_all()

# Initialize scheduler after database setup
schedule_manager.init_app(app)  # This will use replace_existing=True by default

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

def create_persistent_temp_dir():
    """Create a persistent temporary directory that won't be automatically cleaned up."""
    # Create a base temporary directory that persists
    base_dir = os.path.join(tempfile.gettempdir(), 'convention_badges_uploads')
    os.makedirs(base_dir, mode=0o777, exist_ok=True)
    
    # Create a unique subdirectory for this session
    session_dir = tempfile.mkdtemp(dir=base_dir)
    os.chmod(session_dir, 0o777)
    
    logger.info(f"Created persistent upload directory: {session_dir}")
    return session_dir

def cleanup_upload_folder(folder_path):
    """Clean up the upload folder."""
    try:
        if os.path.exists(folder_path):
            logger.debug(f"Cleaning up upload folder: {folder_path}")
            shutil.rmtree(folder_path, ignore_errors=True)
    except Exception as e:
        logger.error(f"Error cleaning up upload folder: {str(e)}")

# Create upload folder with proper permissions
app.config['UPLOAD_FOLDER'] = create_persistent_temp_dir()

# Register cleanup function to run when the server shuts down
atexit.register(cleanup_upload_folder, app.config['UPLOAD_FOLDER'])

# Configure badge generation directories
app.config['BADGE_TEMPLATES_FOLDER'] = os.path.join(BASE_PATH, 'badge_templates')
app.config['BADGE_LOGOS_FOLDER'] = os.path.join(BASE_PATH, 'badge_logos')
app.config['BADGE_BACKGROUNDS_FOLDER'] = os.path.join(BASE_PATH, 'badge_background_templates')
app.config['HOUSEHOLD_CACHE_PATH'] = os.path.join(BASE_PATH, 'data', 'household_cache.json')
# AFRP logo path from environment variable (defaults to PNG in static folder)
afrp_logo_relative = os.environ.get('AFRP_LOGO_PATH', 'static/afrp_logo.png')
# Always store an absolute path so logo lookups survive os.chdir() and so that
# missing-file warnings include a useful path in the logs.
afrp_logo_resolved = afrp_logo_relative if os.path.isabs(afrp_logo_relative) else os.path.join(BASE_PATH, afrp_logo_relative)
app.config['AFRP_LOGO_PATH'] = os.path.abspath(afrp_logo_resolved)
if not os.path.exists(app.config['AFRP_LOGO_PATH']):
    logger.warning(f"AFRP logo not found at startup: {app.config['AFRP_LOGO_PATH']}")

# Ensure badge folders exist
os.makedirs(app.config['BADGE_TEMPLATES_FOLDER'], mode=0o777, exist_ok=True)
os.makedirs(app.config['BADGE_LOGOS_FOLDER'], mode=0o777, exist_ok=True)
os.makedirs(app.config['BADGE_BACKGROUNDS_FOLDER'], mode=0o777, exist_ok=True)

DEFAULT_BADGE_SVG_FILENAME = "minimal_badge_landscape.svg"
DEFAULT_BADGE_SVG_PATH = os.path.join(BASE_PATH, "static", "svg", DEFAULT_BADGE_SVG_FILENAME)


def resolve_badge_svg_path(template=None) -> str:
    """Return path to the built-in Avery 5392 landscape badge SVG."""
    return DEFAULT_BADGE_SVG_PATH

# Log registered preprocessors at startup
logger.info(f"Registered {len(preprocessing_implementations)} preprocessor(s): {list(preprocessing_implementations.keys())}")


@app.before_request
def enforce_feature_permissions():
    """Gate routes by per-user feature permissions (admins bypass)."""
    path = request.path
    if path_is_public(path):
        return None
    if not current_user.is_authenticated:
        return None
    if current_user.is_admin:
        return None
    if path_requires_admin(path):
        if path.startswith("/api"):
            return jsonify({"error": "Admin access required"}), 403
        flash("Access denied — Admin only", "error")
        return redirect(url_for("home"))
    if path == "/":
        return None
    feature_id = feature_for_path(path)
    if feature_id is None:
        if path.startswith("/api"):
            return jsonify({"error": "Forbidden"}), 403
        flash("Access denied", "error")
        return redirect(url_for("home"))
    if not current_user.has_feature(feature_id):
        label = FEATURES[feature_id]["label"]
        if path.startswith("/api"):
            return jsonify({"error": f"Access denied: {label}"}), 403
        flash(f"Access denied — you do not have access to {label}", "error")
        return redirect(url_for("home"))
    return None


# ========================================
# Authentication Routes
# ========================================

def is_safe_url(target):
    """Validate redirect URL to prevent open redirects."""
    from urllib.parse import urlparse, urljoin
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    """First-time setup wizard - only accessible if no users exist."""
    # Check if users already exist
    if User.query.first() is not None:
        flash('Setup already completed', 'info')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        email = request.form.get('email', '').strip()
        
        # Validate username
        valid, error = validate_username(username)
        if not valid:
            flash(error, 'error')
            return render_template('setup.html')
        
        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return render_template('setup.html')
        
        # Validate email if provided
        if email:
            valid, error = validate_email(email)
            if not valid:
                flash(error, 'error')
                return render_template('setup.html')
            
            # Check if email already exists
            if User.query.filter_by(email=email).first():
                flash('Email already exists', 'error')
                return render_template('setup.html')
        
        # Validate password
        valid, error = validate_password(password)
        if not valid:
            flash(error, 'error')
            return render_template('setup.html')
        
        # Check password confirmation
        if password != password_confirm:
            flash('Passwords do not match', 'error')
            return render_template('setup.html')
        
        # Create admin user
        try:
            user = User(
                username=username,
                email=email if email else None,
                is_admin=True,
                is_active=True
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            
            logger.info(f"Admin user created: {username}")
            flash('Admin account created successfully! Please log in.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            db.session.rollback()
            logger.exception("Error creating admin user")
            flash(f'Error creating account: {str(e)}', 'error')
    
    return render_template('setup.html')

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per 15 minutes")
def login():
    """User login."""
    # Check if setup is needed
    if User.query.first() is None:
        return redirect(url_for('setup'))
    
    # Already logged in
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False) == 'on'
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash('Account is disabled', 'error')
                return render_template('login.html')
            
            # Log in user
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            logger.info(f"User logged in: {username}")
            
            # Redirect to next page or home (must be allowed for this user)
            next_page = request.args.get('next')
            if next_page and is_safe_url(next_page):
                from urllib.parse import urlparse, urljoin
                next_path = urlparse(urljoin(request.host_url, next_page)).path
                if user_can_access_path(user, next_path):
                    return redirect(next_page)
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password', 'error')
            logger.warning(f"Failed login attempt for username: {username}")
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """User logout."""
    username = current_user.username
    logout_user()
    logger.info(f"User logged out: {username}")
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

# ========================================
# User Management Routes (Admin Only)
# ========================================

@app.route('/users')
@login_required
def list_users():
    """List all users (admin only)."""
    if not current_user.is_admin:
        flash('Access denied - Admin only', 'error')
        return redirect(url_for('home'))
    
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('users.html', users=users, features=FEATURES)

@app.route('/users/create', methods=['GET', 'POST'])
@login_required
def create_user():
    """Create new user (admin only)."""
    if not current_user.is_admin:
        flash('Access denied - Admin only', 'error')
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        email = request.form.get('email', '').strip()
        role = _user_role_from_form(request.form)
        
        # Validate username
        valid, error = validate_username(username)
        if not valid:
            flash(error, 'error')
            return render_template('create_user.html')
        
        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return render_template('create_user.html')
        
        # Validate email if provided
        if email:
            valid, error = validate_email(email)
            if not valid:
                flash(error, 'error')
                return render_template('create_user.html')
            
            # Check if email already exists
            if User.query.filter_by(email=email).first():
                flash('Email already exists', 'error')
                return render_template('create_user.html')
        
        # Validate password
        valid, error = validate_password(password)
        if not valid:
            flash(error, 'error')
            return render_template('create_user.html')
        
        # Check password confirmation
        if password != password_confirm:
            flash('Passwords do not match', 'error')
            return render_template('create_user.html')
        
        # Create user
        try:
            user = User(
                username=username,
                email=email if email else None,
                is_active=True
            )
            user.set_password(password)
            _apply_user_access_from_form(user, request.form)
            db.session.add(user)
            db.session.commit()
            
            logger.info(f"User created: {username} by {current_user.username}")
            flash(f'User {username} created successfully', 'success')
            return redirect(url_for('list_users'))

        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'error')
            return render_template('create_user.html', features=FEATURES)
        except Exception as e:
            db.session.rollback()
            logger.exception("Error creating user")
            flash(f'Error creating user: {str(e)}', 'error')
    
    return render_template('create_user.html', features=FEATURES)

@app.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    """Edit user permissions (admin only)."""
    if not current_user.is_admin:
        flash('Access denied - Admin only', 'error')
        return redirect(url_for('home'))

    user = User.query.get(user_id)
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('list_users'))

    if request.method == 'POST':
        try:
            _apply_user_access_from_form(user, request.form)
            db.session.commit()
            logger.info(f"User updated: {user.username} by {current_user.username}")
            flash(f'User {user.username} updated successfully', 'success')
            return redirect(url_for('list_users'))
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'error')
        except Exception as e:
            db.session.rollback()
            logger.exception("Error updating user")
            flash(f'Error updating user: {str(e)}', 'error')

    return render_template('edit_user.html', user=user, features=FEATURES)

@app.route('/users/<int:user_id>/toggle-active', methods=['POST'])
@login_required
def toggle_user_active(user_id):
    """Toggle user active status (admin only)."""
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Prevent deactivating yourself
    if user.id == current_user.id:
        return jsonify({'error': 'Cannot deactivate your own account'}), 400
    
    try:
        user.is_active = not user.is_active
        db.session.commit()
        status = 'activated' if user.is_active else 'deactivated'
        logger.info(f"User {user.username} {status} by {current_user.username}")
        return jsonify({'success': True, 'is_active': user.is_active})
    except Exception as e:
        db.session.rollback()
        logger.exception("Error toggling user status")
        return jsonify({'error': str(e)}), 500

@app.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    """Delete user (admin only)."""
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Prevent deleting yourself
    if user.id == current_user.id:
        return jsonify({'error': 'Cannot delete your own account'}), 400
    
    try:
        username = user.username
        db.session.delete(user)
        db.session.commit()
        logger.info(f"User deleted: {username} by {current_user.username}")
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        logger.exception("Error deleting user")
        return jsonify({'error': str(e)}), 500

# ========================================
# Main Application Routes
# ========================================

@app.route('/', methods=['GET'])
@login_required
def home():
    # This route displays the home page with tiles
    return render_template(
        'home.html',
        allowed_features=current_user.allowed_features(),
        features=FEATURES,
    )

@app.route('/qr', methods=['GET', 'POST'])
@login_required
def qr():
    if request.method == 'POST':
        data = request.form.get('data')
        image_file = request.files.get('image')
        shape = request.form.get('shape', 'circle')  # Get the shape selection
        solid_radius_percent = request.form.get('solid_radius', '60')  # Get the radius percentage

        if data:
            # Generate QR code
            qr_code = qrcode.QRCode(
                version=None,  # Adjusts size automatically based on data
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=10,
                border=4,
            )
            qr_code.add_data(data)
            qr_code.make(fit=True)
            img_qr = qr_code.make_image(
                fill_color="black", back_color="white"
            ).convert('RGBA')  # Use 'RGBA' mode for transparency

            # Add center image if provided
            if image_file and image_file.filename != '':
                try:
                    # Convert solid_radius_percent to a float between 0 and 1
                    solid_radius = float(solid_radius_percent) / 100.0
                    # Ensure solid_radius is within valid range
                    solid_radius = min(max(solid_radius, 0.01), 1.0)

                    # Open and convert the icon image to RGBA
                    icon = Image.open(image_file).convert("RGBA")

                    # Calculate dimensions for the icon
                    img_w, img_h = img_qr.size
                    factor = 2.5  # Adjust factor to change icon size
                    size_w = int(img_w / factor)
                    size_h = int(img_h / factor)

                    # Resize the icon
                    icon = icon.resize((size_w, size_h), Image.LANCZOS)

                    # Create mask depending on the shape
                    if shape == 'circle':
                        # Circular fade mask with solid center
                        x = np.linspace(-1, 1, size_w)
                        y = np.linspace(-1, 1, size_h)
                        xv, yv = np.meshgrid(x, y)
                        d = np.sqrt(xv**2 + yv**2)
                        mask_array = np.ones_like(d)
                        fade_zone = d >= solid_radius
                        mask_array[fade_zone] = 1 - (d[fade_zone] - solid_radius) / (1 - solid_radius)
                        mask_array = np.clip(mask_array, 0, 1)
                        mask_array = (mask_array * 255).astype('uint8')
                        mask = Image.fromarray(mask_array, mode='L')
                    else:
                        # Rectangle fade mask with solid center
                        x = np.linspace(-1, 1, size_w)
                        y = np.linspace(-1, 1, size_h)
                        xv, yv = np.meshgrid(x, y)
                        dx = np.abs(xv)
                        dy = np.abs(yv)
                        mask_array = np.ones_like(dx)
                        fade_zone_x = dx >= solid_radius
                        mask_array[fade_zone_x] *= 1 - (dx[fade_zone_x] - solid_radius) / (1 - solid_radius)
                        fade_zone_y = dy >= solid_radius
                        mask_array[fade_zone_y] *= 1 - (dy[fade_zone_y] - solid_radius) / (1 - solid_radius)
                        mask_array = np.clip(mask_array, 0, 1)
                        mask_array = (mask_array * 255).astype('uint8')
                        mask = Image.fromarray(mask_array, mode='L')

                    # Apply the mask to the icon
                    icon.putalpha(mask)

                    # Paste the icon onto the QR code
                    pos_w = (img_w - size_w) // 2
                    pos_h = (img_h - size_h) // 2
                    img_qr.paste(icon, (pos_w, pos_h), icon)
                except Exception as e:
                    print(f"Error processing the image: {e}")

            # Save the generated QR code to a bytes buffer
            buf = BytesIO()
            img_qr.save(buf, format='PNG')
            buf.seek(0)
            return send_file(
                buf,
                mimetype='image/png',
                as_attachment=True,
                download_name='qr.png'
            )
    return render_template('qr.html')

@app.route('/magazine')
@login_required
def magazine():
    schedules = Schedule.query.all()
    return render_template('magazine.html', schedules=schedules)

@app.route('/event', methods=['GET', 'POST'])
@login_required
def event_page():
    if request.method == 'POST':
        crm_url = request.form.get('crmUrl')
        try:
            event_id = extract_event_id(crm_url)
            event_url = generate_event_registration_url(event_id)
            summary_url = generate_event_summary_url(event_id)
            return jsonify({
                'event_url': event_url,
                'summary_url': summary_url
            })
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
    return render_template('event.html')

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

@app.route('/api/schedules', methods=['GET', 'POST', 'DELETE'])
@login_required
def manage_schedules():
    if request.method == 'GET':
        schedules = Schedule.query.all()
        return jsonify([{
            'id': s.id,
            'frequency': s.frequency,
            'time': s.time,
            'day_of_week': s.day_of_week,
            'day_of_month': s.day_of_month,
            'active': s.active,
            'runs': [{
                'id': r.id,
                'start_time': r.start_time.strftime('%Y-%m-%d %I:%M %p'),
                'end_time': r.end_time.strftime('%Y-%m-%d %I:%M %p') if r.end_time else None,
                'status': r.status,
                'logs': r.logs
            } for r in s.runs[:10]]  # Get last 10 runs
        } for s in schedules])
    
    elif request.method == 'POST':
        data = request.json
        
        # Check if a schedule with the same configuration already exists
        existing_schedule = Schedule.query.filter_by(
            frequency=data['frequency'],
            time=data['time'],
            day_of_week=data.get('day_of_week'),
            day_of_month=data.get('day_of_month'),
            active=True
        ).first()
        
        if existing_schedule:
            return jsonify({'error': 'Schedule with these parameters already exists'}), 409
            
        # Validate time format
        if not validate_time_format(data.get('time', '')):
            return jsonify({'error': 'Invalid time format. Use HH:MM AM/PM format (e.g., 09:30 AM)'}), 400

        # Create new schedule if none exists
        try:
            schedule = Schedule(
                frequency=data['frequency'],
                time=data['time'],
                day_of_week=data.get('day_of_week'),
                day_of_month=data.get('day_of_month'),
                active=True
            )
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        
        try:
            db.session.add(schedule)
            db.session.commit()
            
            # Add job to scheduler
            schedule_manager.add_job(schedule, magazine_main, replace_existing=True)
            
            return jsonify({
                'id': schedule.id,
                'message': 'Schedule created successfully'
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': f'Failed to create schedule: {str(e)}'}), 500
    
    elif request.method == 'DELETE':
        schedule_id = request.args.get('id')
        if not schedule_id:
            return jsonify({'error': 'Schedule ID is required'}), 400
        
        try:
            schedule = Schedule.query.get(schedule_id)
            if not schedule:
                return jsonify({'error': 'Schedule not found'}), 404

            # Remove from scheduler first
            schedule_manager.remove_job(schedule.id)
            
            # Delete associated runs
            for run in schedule.runs:
                db.session.delete(run)
            
            # Delete schedule
            db.session.delete(schedule)
            db.session.commit()
            
            return jsonify({'message': 'Schedule deleted successfully'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': f'Failed to delete schedule: {str(e)}'}), 500

@app.route('/run-magazine-download')
@login_required
def run_magazine_download():
    def generate():
        logging.info("Starting magazine download process")
        output_queue = queue.Queue()
        log_queue = queue.Queue()
        
        class QueueHandler(logging.Handler):
            def emit(self, record):
                log_entry = self.format(record)
                log_queue.put(log_entry)
                # Also print to stdout for terminal visibility with a single newline
                print(log_entry, flush=True)
        
        def run_download():
            try:
                # Create and configure queue handler
                queue_handler = QueueHandler()
                queue_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
                queue_handler.setLevel(logging.INFO)
                
                # Add handler to root logger
                root_logger = logging.getLogger()
                root_logger.addHandler(queue_handler)
                
                try:
                    magazine_main()
                except Exception as e:
                    logging.error(f"Error in magazine download: {str(e)}")
                finally:
                    # Remove queue handler
                    root_logger.removeHandler(queue_handler)
                    logging.shutdown() # Ensure all logs are processed
                    output_queue.put(None)  # Signal completion
            except Exception as e:
                logging.error(f"Error in download thread: {str(e)}")
                output_queue.put(None)

        logging.info("Starting download thread")
        thread = threading.Thread(target=run_download)
        thread.start()

        logging.info("Collecting log messages")
        all_logs = []

        logging.info("Streaming output")
        while True:
            # Check for new log messages
            try:
                while True:
                    log_entry = log_queue.get_nowait()
                    all_logs.append(log_entry)
                    # Ensure log entry doesn't have trailing newlines that would create empty lines
                    log_entry = log_entry.rstrip('\n')
                    yield f"data: {log_entry}\n\n"
            except queue.Empty:
                pass

            # Check if process is complete
            try:
                done = output_queue.get_nowait()
                if done is None:
                    break
            except queue.Empty:
                pass

        logging.info("Creating job run record")
        with app.app_context():
            job_run = JobRun(
                schedule_id=None,  # Manual run has no schedule
                end_time=datetime.utcnow(),
                logs='\n'.join(all_logs),
                status='success' if 'ERROR' not in '\n'.join(all_logs) else 'error'
            )
            db.session.add(job_run)
            db.session.commit()

        logging.info("Download process completed")
        yield "data: DONE\n\n"

    return Response(generate(), mimetype='text/event-stream')

# Badge Generator Routes
@app.route('/badges')
@login_required
def badges():
    """Badge Generator page with automated CRM integration."""
    return render_template('badges.html')

# Badge Mapping & Preprocessing Designer Routes


@app.route('/badge-mapping')
@login_required
def badge_mapping():
    """Badge template mapping configuration page."""
    badge_scale_js = None
    try:
        badge_scale_js = load_badge_scale_js()
    except OSError as exc:
        logger.warning("Could not load bundled badge_scale.js: %s", exc)
    return render_template(
        'badge_mapping.html',
        badge_scale_js=badge_scale_js,
        is_admin=current_user.is_admin,
        current_user_id=current_user.id,
    )

@app.route('/preprocessing-designer')
@login_required
def preprocessing_designer():
    """Preprocessing template designer page."""
    return render_template('preprocessing_designer.html', is_admin=current_user.is_admin)

@app.route('/badge_templates/<path:filename>')
@login_required
def serve_badge_template(filename):
    """Serve badge template SVG files."""
    return send_from_directory(app.config['BADGE_TEMPLATES_FOLDER'], filename)


@app.route('/badge_logos/<path:filename>')
@login_required
def serve_badge_logo(filename):
    """Serve uploaded club logo files for badge preview."""
    return send_from_directory(app.config['BADGE_LOGOS_FOLDER'], filename)


@app.route('/badge_background_templates/<path:filename>')
@login_required
def serve_badge_background(filename):
    """Serve badge background images and thumbnails."""
    return send_from_directory(app.config['BADGE_BACKGROUNDS_FOLDER'], filename)


@app.route('/api/badge-backgrounds', methods=['GET'])
@login_required
def get_badge_backgrounds():
    """List available badge background templates for an Avery size."""
    avery = request.args.get('avery', '5392')
    backgrounds = list_backgrounds(app.config['BADGE_BACKGROUNDS_FOLDER'], avery)
    return jsonify({'backgrounds': backgrounds, 'avery': avery})


@app.route('/api/badge-backgrounds/upload', methods=['POST'])
@login_required
def upload_badge_background():
    """Upload a custom badge background sized for the selected Avery canvas."""
    avery = request.form.get('avery', '5392')
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    file_storage = request.files['file']
    if not file_storage.filename:
        return jsonify({'error': 'No file selected'}), 400

    img, error = validate_background_image(file_storage, avery)
    if error:
        return jsonify({'error': error}), 400

    try:
        entry = register_upload(
            app.config['BADGE_BACKGROUNDS_FOLDER'],
            img,
            file_storage.filename,
            avery,
            uploaded_by_user_id=current_user.id,
        )
        return jsonify(entry), 201
    except Exception as e:
        logger.exception("Error uploading badge background")
        return jsonify({'error': str(e)}), 500


@app.route('/api/badge-backgrounds/<background_id>', methods=['DELETE'])
@login_required
def delete_badge_background(background_id):
    """Remove a background. Admins may remove any; users only their own uploads."""
    avery = request.args.get('avery', '5392')

    entry, error = delete_background(
        app.config['BADGE_BACKGROUNDS_FOLDER'],
        background_id,
        avery,
        user_id=current_user.id,
        is_admin=current_user.is_admin,
    )
    if error:
        lowered = error.lower()
        if (
            "administrator" in lowered
            or "only remove backgrounds you uploaded" in lowered
            or "without an owner" in lowered
        ):
            status = 403
        elif "not found" in lowered:
            status = 404
        else:
            status = 400
        return jsonify({'error': error}), status

    templates_reset = BadgeTemplate.query.filter_by(
        background_id=background_id
    ).update({'background_id': 'white'}, synchronize_session=False)
    db.session.commit()

    logger.info(
        "Removed badge background %s (%s); reset %d template(s) to white",
        background_id,
        entry.get('name'),
        templates_reset,
    )
    return jsonify({
        'message': 'Background removed successfully',
        'templates_reset': templates_reset,
    })


@app.route('/api/badges/meal-options', methods=['GET'])
@login_required
def get_badge_meal_options():
    """Detect meal-preference questions and choice labels for a main event."""
    campaign_id = (request.args.get('campaign_id') or '').strip()
    if not campaign_id:
        return jsonify({'error': 'campaign_id is required'}), 400
    denied = _require_campaign_access(current_user, campaign_id)
    if denied:
        return denied
    try:
        crm_client = DynamicsCRMClient()
        questions = crm_client.get_form_questions(campaign_id)
        payload = aggregate_meal_options(questions)
        payload['campaign_id'] = campaign_id
        return jsonify(payload)
    except Exception as e:
        logger.exception("Error fetching meal options for campaign %s", campaign_id)
        return jsonify({'error': str(e)}), 500


@app.route('/api/campaigns/open', methods=['GET'])
@login_required
def get_open_campaigns():
    """Get list of open campaigns from Dynamics CRM."""
    try:
        crm_client = DynamicsCRMClient()
        campaigns = crm_client.get_open_campaigns()
        annotated = annotate_campaigns_for_user(current_user, campaigns)
        access = campaign_access_metadata(current_user)

        logger.info(f"Retrieved {len(campaigns)} open campaigns")
        return jsonify({'campaigns': annotated, 'access': access})
        
    except Exception as e:
        logger.error(f"Error fetching open campaigns: {str(e)}")
        return jsonify({'error': f'Failed to fetch open campaigns: {str(e)}'}), 500

@app.route('/api/campaigns/<campaign_id>/sub-events', methods=['GET'])
@login_required
def get_campaign_sub_events(campaign_id):
    """Get list of sub-events for a specific campaign from Dynamics CRM."""
    denied = _require_campaign_access(current_user, campaign_id)
    if denied:
        return denied
    try:
        crm_client = DynamicsCRMClient()
        sub_events = crm_client.get_sub_events(campaign_id)
        
        logger.info(f"Retrieved {len(sub_events)} sub-events for campaign {campaign_id}")
        return jsonify({'sub_events': sub_events})
        
    except Exception as e:
        logger.error(f"Error fetching sub-events for campaign {campaign_id}: {str(e)}")
        return jsonify({'error': f'Failed to fetch sub-events: {str(e)}'}), 500
@app.route('/api/badges/pull-and-process', methods=['POST'])
@login_required
def badges_pull_and_process():
    """One-click endpoint to pull all data from CRM and process it."""
    logger.debug("Starting Badge Generator V2 pull and process")
    try:
        data = request.get_json()
        if not data:
            logger.error("No JSON data received")
            return jsonify({'error': 'No data received'}), 400
        
        # Get parameters
        campaign_id = data.get('campaign_id')
        campaign_name = data.get('campaign_name')
        event_name = data.get('event')
        sub_event = data.get('subEvent')
        inclusion_list = data.get('inclusionList')
        created_on_filter = data.get('createdOnFilter')
        group_by_household = bool(data.get('groupByHousehold', False))
        preprocessing_template_id = data.get('preprocessingTemplateId')
        
        if not campaign_id and not campaign_name:
            logger.error("No campaign ID or name provided")
            return jsonify({'error': 'Campaign ID or name is required'}), 400
        
        logger.debug(f"Processing request: campaign_id={campaign_id}, campaign_name={campaign_name}, event={event_name}")
        
        # Initialize CRM client
        try:
            crm_client = DynamicsCRMClient()
        except Exception as e:
            logger.error(f"Failed to initialize CRM client: {str(e)}")
            return jsonify({'error': f'Failed to connect to Dynamics CRM: {str(e)}'}), 500
        
        # Campaign-based approach
        logger.info("Using campaign-based filtering")
        
        # Get campaign ID if only name was provided
        if campaign_name and not campaign_id:
            campaign_info = crm_client.get_campaign_by_name(campaign_name)
            if not campaign_info:
                return jsonify({'error': f'Campaign "{campaign_name}" not found'}), 404
            campaign_id = campaign_info['id']
            logger.info(f"Found campaign: {campaign_info['name']} (ID: {campaign_id})")
        
        # Verify campaign exists
        campaign_info = crm_client.get_campaign_by_id(campaign_id)
        if not campaign_info:
            return jsonify({'error': 'Campaign not found'}), 404
        
        logger.info(f"Using campaign: {campaign_info['name']} (ID: {campaign_id})")

        denied = _require_campaign_access(
            current_user, campaign_id, sub_event, crm_client
        )
        if denied:
            return denied
        
        upload_folder = app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, mode=0o777, exist_ok=True)

        try:
            with badge_pipeline_job():
                store = BadgeDataStore(upload_folder)
                pull_campaign_to_store(crm_client, campaign_id, store)
        except PipelineBusyError as exc:
            return jsonify({'error': str(exc)}), 409
        except InsufficientMemoryError as exc:
            return jsonify({'error': str(exc)}), 503
        
        logger.info("All data pulled successfully, starting processing...")
        
        if not event_name:
            logger.error("No event name provided for processing")
            return jsonify({'error': 'Event name is required'}), 400
        
        preprocessor_class = _resolve_preprocessor_class(preprocessing_template_id)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            logger.debug(f"Created temporary directory: {temp_dir}")
            os.makedirs(temp_dir, mode=0o777, exist_ok=True)
            
            _copy_badge_sources_to_dir(upload_folder, temp_dir)
            original_dir = os.getcwd()
            os.chdir(temp_dir)
            logger.debug(f"Changed working directory to: {temp_dir}")
            
            try:
                # Create preprocessing config
                config_obj = _preprocessing_config_with_meal(
                    preprocessing_template_id,
                    main_event=event_name,
                    sub_event=sub_event if sub_event else None,
                    inclusion_list=inclusion_list if inclusion_list else None,
                    created_on_filter=created_on_filter if created_on_filter else None,
                    group_by_household=group_by_household,
                    household_cache_path=app.config['HOUSEHOLD_CACHE_PATH'],
                )
                logger.debug(f"Created preprocessing config: {config_obj.__dict__}")
                
                # Initialize processor
                processor = EventRegistrationProcessorV3(
                    config=config_obj,
                    preprocessor_class=preprocessor_class
                )
                
                # Process files
                logger.info("Starting file processing...")
                result_df = processor.transform_and_merge()
                logger.debug(f"Processing complete. Result shape: {result_df.shape}")
                
                # Save output
                output_file = os.path.join(temp_dir, "MAIL_MERGE_output.xlsx")
                result_df.to_excel(output_file, index=False)
                logger.debug(f"Saved output to: {output_file}")
                
                # Send file to user
                return send_file(
                    output_file,
                    as_attachment=True,
                    download_name=f"MAIL_MERGE_{event_name.replace(' ', '_')}_{sub_event or 'all'}.xlsx",
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
            
            except Exception as e:
                logger.exception("Error during processing")
                return jsonify({'error': f'Processing error: {str(e)}\n{traceback.format_exc()}'}), 500
            
            finally:
                os.chdir(original_dir)
                logger.debug(f"Changed working directory back to: {original_dir}")
    except Exception as e:
        logger.exception("Error in badges_v2_pull_and_process handler")
        return jsonify({'error': f'Server error: {str(e)}'}), 500
# ============================================================================
# Badge Generation API Endpoints
# ============================================================================

@app.route('/api/badge-templates', methods=['GET'])
@login_required
def get_badge_templates():
    """Get list of saved badge templates."""
    try:
        templates = BadgeTemplate.query.all()
        return jsonify({
            'templates': [t.to_dict() for t in templates]
        })
    except Exception as e:
        logger.exception("Error fetching badge templates")
        return jsonify({'error': str(e)}), 500

@app.route('/api/badge-templates', methods=['POST'])
@login_required
def create_badge_template():
    """Save a new badge template configuration."""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('name'):
            return jsonify({'error': 'Template name is required'}), 400
        if not data.get('column_mappings'):
            return jsonify({'error': 'Column mappings are required'}), 400
        
        # Check if template with this name already exists
        existing = BadgeTemplate.query.filter_by(name=data['name']).first()
        if existing:
            return jsonify({'error': 'Template with this name already exists'}), 400
        
        # Create new template
        template = BadgeTemplate(
            name=data['name'],
            svg_filename=DEFAULT_BADGE_SVG_FILENAME,
            club_logo_filename=data.get('club_logo_filename'),
            club_logo_width=data.get('club_logo_width'),
            club_logo_height=data.get('club_logo_height'),
            column_mappings=json.dumps(data['column_mappings']),
            avery_template=data.get('avery_template', '5392'),
            background_id=data.get('background_id', 'white'),
            show_outlines=bool(data.get('show_outlines', False)),
            element_layout=json.dumps(data.get('element_layout') or {}),
            display_name_config=json.dumps(data.get('display_name_config') or {}),
        )
        
        db.session.add(template)
        db.session.commit()
        
        logger.info(f"Created badge template: {template.name}")
        return jsonify(template.to_dict()), 201
        
    except Exception as e:
        logger.exception("Error creating badge template")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/badge-templates/<int:template_id>', methods=['GET'])
@login_required
def get_badge_template(template_id):
    """Get a specific badge template."""
    try:
        template = BadgeTemplate.query.get(template_id)
        if not template:
            return jsonify({'error': 'Template not found'}), 404
        return jsonify(template.to_dict())
    except Exception as e:
        logger.exception(f"Error fetching badge template {template_id}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/badge-templates/<int:template_id>', methods=['PUT'])
@login_required
def update_badge_template(template_id):
    """Update an existing badge template."""
    try:
        template = BadgeTemplate.query.get(template_id)
        if not template:
            return jsonify({'error': 'Template not found'}), 404
        
        data = request.get_json()
        
        # Update fields if provided
        if 'name' in data:
            # Check if new name conflicts with another template
            existing = BadgeTemplate.query.filter(
                BadgeTemplate.name == data['name'],
                BadgeTemplate.id != template_id
            ).first()
            if existing:
                return jsonify({'error': 'Template with this name already exists'}), 400
            template.name = data['name']
        
        if 'club_logo_filename' in data:
            template.club_logo_filename = data['club_logo_filename']
        if 'club_logo_width' in data:
            template.club_logo_width = data['club_logo_width']
        if 'club_logo_height' in data:
            template.club_logo_height = data['club_logo_height']
        if 'column_mappings' in data:
            template.column_mappings = json.dumps(data['column_mappings'])
        if 'avery_template' in data:
            template.avery_template = data['avery_template']
        if 'background_id' in data:
            template.background_id = data['background_id'] or 'white'
        if 'show_outlines' in data:
            template.show_outlines = bool(data['show_outlines'])
        if 'element_layout' in data:
            template.element_layout = json.dumps(data['element_layout'] or {})
        if 'display_name_config' in data:
            template.display_name_config = json.dumps(data['display_name_config'] or {})
        
        template.updated_at = datetime.utcnow()
        db.session.commit()
        
        logger.info(f"Updated badge template: {template.name}")
        return jsonify(template.to_dict())
        
    except Exception as e:
        logger.exception(f"Error updating badge template {template_id}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/badge-templates/<int:template_id>', methods=['DELETE'])
@login_required
def delete_badge_template(template_id):
    """Delete a badge template (admin only)."""
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied - Admin only'}), 403
    try:
        template = BadgeTemplate.query.get(template_id)
        if not template:
            return jsonify({'error': 'Template not found'}), 404
        
        template_name = template.name
        db.session.delete(template)
        db.session.commit()
        
        logger.info(f"Deleted badge template: {template_name}")
        return jsonify({'message': 'Template deleted successfully'})
        
    except Exception as e:
        logger.exception(f"Error deleting badge template {template_id}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/badge-templates/<int:template_id>/duplicate', methods=['POST'])
@login_required
def duplicate_badge_template(template_id):
    """Duplicate a badge template with auto-incremented name."""
    try:
        template = BadgeTemplate.query.get(template_id)
        if not template:
            return jsonify({'error': 'Template not found'}), 404
        
        # Generate new name with auto-increment
        base_name = template.name
        new_name = base_name
        counter = 1
        
        while BadgeTemplate.query.filter_by(name=new_name).first():
            new_name = f"{base_name} ({counter})"
            counter += 1
        
        # Create duplicate
        new_template = BadgeTemplate(
            name=new_name,
            svg_filename=DEFAULT_BADGE_SVG_FILENAME,
            club_logo_filename=template.club_logo_filename,
            club_logo_width=template.club_logo_width,
            club_logo_height=template.club_logo_height,
            column_mappings=template.column_mappings,
            avery_template=template.avery_template,
            background_id=template.background_id or 'white',
            show_outlines=template.show_outlines,
            element_layout=template.element_layout or '{}',
            display_name_config=template.display_name_config or '{}',
        )
        
        db.session.add(new_template)
        db.session.commit()
        
        logger.info(f"Duplicated badge template '{template.name}' as '{new_name}'")
        return jsonify({
            'success': True,
            'message': 'Template duplicated successfully',
            'template': new_template.to_dict()
        }), 201
        
    except Exception as e:
        logger.exception(f"Error duplicating badge template {template_id}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/badge-logos/upload', methods=['POST'])
@login_required
def upload_club_logo():
    """Upload club logo for badge generation."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Validate file type
        allowed_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.svg'}
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            return jsonify({'error': 'Invalid file type. Allowed: PNG, JPG, GIF, SVG'}), 400
        
        # Save file
        filename = secure_filename(file.filename)
        # Add timestamp to avoid conflicts
        timestamp = int(datetime.utcnow().timestamp())
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['BADGE_LOGOS_FOLDER'], filename)
        file.save(filepath)
        
        width, height = probe_image_dimensions(filepath)
        if width and height:
            logger.info(f"Club logo dimensions: {width}x{height}")
        else:
            logger.warning(f"Could not determine logo dimensions for {filename}")
        
        logger.info(f"Uploaded club logo: {filename}")
        return jsonify({
            'filename': filename,
            'path': filepath,
            'width': width,
            'height': height
        })
        
    except Exception as e:
        logger.exception("Error uploading club logo")
        return jsonify({'error': str(e)}), 500

@app.route('/api/avery-templates', methods=['GET'])
@login_required
def get_avery_templates():
    """Get list of available Avery templates."""
    try:
        templates = BadgeGenerator.get_available_templates()
        return jsonify({'templates': templates})
    except Exception as e:
        logger.exception("Error fetching Avery templates")
        return jsonify({'error': str(e)}), 500

# ============================================
# Preprocessing Template Endpoints
# ============================================

@app.route('/api/preprocessing-templates', methods=['GET'])
@login_required
def get_preprocessing_templates():
    """Get list of saved preprocessing templates."""
    try:
        from utils.magazine.scheduler import PreprocessingTemplate
        templates = PreprocessingTemplate.query.all()
        return jsonify({
            'success': True,
            'templates': [t.to_dict() for t in templates]
        })
    except Exception as e:
        logger.exception("Error fetching preprocessing templates")
        return jsonify({'error': str(e)}), 500

@app.route('/api/preprocessing-templates', methods=['POST'])
@login_required
def create_preprocessing_template():
    """Create a new preprocessing template."""
    try:
        from utils.magazine.scheduler import PreprocessingTemplate
        data = request.get_json()
        
        # Validate required fields
        if not data.get('name'):
            return jsonify({'error': 'Template name is required'}), 400
        
        # Check if template with same name exists
        existing = PreprocessingTemplate.query.filter_by(name=data['name']).first()
        if existing:
            return jsonify({'error': 'Template with this name already exists'}), 400
        
        # Create new template
        template = PreprocessingTemplate(
            name=data['name'],
            description=data.get('description', ''),
            value_mappings=json.dumps(data.get('value_mappings', {})),
            contains_mappings=json.dumps(data.get('contains_mappings', {})),
            meal_preference_mappings=json.dumps(data.get('meal_preference_mappings') or {}),
            meal_preference_sources=json.dumps(data.get('meal_preference_sources') or {}),
        )
        
        db.session.add(template)
        db.session.commit()
        
        logger.info(f"Created preprocessing template: {template.name}")
        return jsonify({
            'success': True,
            'message': 'Template created successfully',
            'template': template.to_dict()
        }), 201
        
    except Exception as e:
        logger.exception("Error creating preprocessing template")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/preprocessing-templates/<int:template_id>', methods=['GET'])
@login_required
def get_preprocessing_template(template_id):
    """Get a specific preprocessing template."""
    try:
        from utils.magazine.scheduler import PreprocessingTemplate
        template = PreprocessingTemplate.query.get(template_id)
        if not template:
            return jsonify({'error': 'Template not found'}), 404
        return jsonify({
            'success': True,
            'template': template.to_dict()
        })
    except Exception as e:
        logger.exception(f"Error fetching preprocessing template {template_id}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/preprocessing-templates/<int:template_id>', methods=['PUT'])
@login_required
def update_preprocessing_template(template_id):
    """Update an existing preprocessing template."""
    try:
        from utils.magazine.scheduler import PreprocessingTemplate
        template = PreprocessingTemplate.query.get(template_id)
        if not template:
            return jsonify({'error': 'Template not found'}), 404
        
        data = request.get_json()
        
        # Update fields if provided
        if 'name' in data:
            # Check if new name conflicts with another template
            existing = PreprocessingTemplate.query.filter(
                PreprocessingTemplate.name == data['name'],
                PreprocessingTemplate.id != template_id
            ).first()
            if existing:
                return jsonify({'error': 'Template with this name already exists'}), 400
            template.name = data['name']
        
        if 'description' in data:
            template.description = data['description']
        if 'value_mappings' in data:
            template.value_mappings = json.dumps(data['value_mappings'])
        if 'contains_mappings' in data:
            template.contains_mappings = json.dumps(data['contains_mappings'])
        if 'meal_preference_mappings' in data:
            template.meal_preference_mappings = json.dumps(
                data['meal_preference_mappings'] or {}
            )
        if 'meal_preference_sources' in data:
            template.meal_preference_sources = json.dumps(
                data['meal_preference_sources'] or {}
            )
        
        template.updated_at = datetime.utcnow()
        db.session.commit()
        
        logger.info(f"Updated preprocessing template: {template.name}")
        return jsonify({
            'success': True,
            'message': 'Template updated successfully',
            'template': template.to_dict()
        })
        
    except Exception as e:
        logger.exception(f"Error updating preprocessing template {template_id}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/preprocessing-templates/<int:template_id>', methods=['DELETE'])
@login_required
def delete_preprocessing_template(template_id):
    """Delete a preprocessing template (admin only)."""
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied - Admin only'}), 403
    try:
        from utils.magazine.scheduler import PreprocessingTemplate
        template = PreprocessingTemplate.query.get(template_id)
        if not template:
            return jsonify({'error': 'Template not found'}), 404
        
        template_name = template.name
        db.session.delete(template)
        db.session.commit()
        
        logger.info(f"Deleted preprocessing template: {template_name}")
        return jsonify({
            'success': True,
            'message': 'Template deleted successfully'
        })
        
    except Exception as e:
        logger.exception(f"Error deleting preprocessing template {template_id}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/preprocessing-templates/<int:template_id>/duplicate', methods=['POST'])
@login_required
def duplicate_preprocessing_template(template_id):
    """Duplicate a preprocessing template with auto-incremented name."""
    try:
        from utils.magazine.scheduler import PreprocessingTemplate
        template = PreprocessingTemplate.query.get(template_id)
        if not template:
            return jsonify({'error': 'Template not found'}), 404
        
        # Generate new name with auto-increment
        base_name = template.name
        new_name = base_name
        counter = 1
        
        while PreprocessingTemplate.query.filter_by(name=new_name).first():
            new_name = f"{base_name} ({counter})"
            counter += 1
        
        # Create duplicate
        new_template = PreprocessingTemplate(
            name=new_name,
            description=template.description,
            value_mappings=template.value_mappings,
            contains_mappings=template.contains_mappings,
            meal_preference_mappings=template.meal_preference_mappings or '{}',
            meal_preference_sources=template.meal_preference_sources or '{}',
        )
        
        db.session.add(new_template)
        db.session.commit()
        
        logger.info(f"Duplicated preprocessing template '{template.name}' as '{new_name}'")
        return jsonify({
            'success': True,
            'message': 'Template duplicated successfully',
            'template': new_template.to_dict()
        }), 201
        
    except Exception as e:
        logger.exception(f"Error duplicating preprocessing template {template_id}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/badges/generate', methods=['POST'])
@login_required
def generate_badges():
    """Generate PDF badges from processed Excel file."""
    try:
        data = request.get_json()
        
        # Validate required fields
        excel_file = data.get('excel_file')
        template_id = data.get('template_id')
        preprocessing_template_id = data.get('preprocessingTemplateId')
        
        if not excel_file:
            return jsonify({'error': 'Excel file path is required'}), 400
        if not template_id:
            return jsonify({'error': 'Template ID is required'}), 400
        
        # Check if Excel file exists
        if not os.path.exists(excel_file):
            return jsonify({'error': 'Excel file not found'}), 404
        
        # Load template configuration
        template = BadgeTemplate.query.get(template_id)
        if not template:
            return jsonify({'error': 'Template not found'}), 404
        
        # Get SVG template path (built-in Avery 5392 landscape)
        svg_path = resolve_badge_svg_path(template)
        if not os.path.exists(svg_path):
            return jsonify({'error': 'Built-in badge SVG template not found'}), 500
        
        club_logo_path, club_logo_error = _resolve_badge_club_logo(template, svg_path)
        if club_logo_error:
            return jsonify({'error': club_logo_error}), 400
        if club_logo_path:
            logger.info(f"Using club logo: {club_logo_path}")
        
        # Get Avery template from badge template
        avery_template = template.avery_template
        
        # Parse column mappings
        column_mappings = json.loads(template.column_mappings)
        
        # Create badge generator
        generator = BadgeGenerator(
            excel_file=excel_file,
            svg_template_path=svg_path,
            column_mappings=column_mappings,
            afrp_logo_path=app.config['AFRP_LOGO_PATH'],
            club_logo_path=club_logo_path,
            club_logo_width=template.club_logo_width,
            club_logo_height=template.club_logo_height,
            avery_template=avery_template,
            show_outlines=template.show_outlines,
            background_id=template.background_id or 'white',
            backgrounds_folder=app.config['BADGE_BACKGROUNDS_FOLDER'],
            element_layout=_template_element_layout(template),
            display_name_config=_template_display_name_config(template),
            **_badge_generator_meal_kwargs(preprocessing_template_id),
        )
        
        # Generate PDF
        output_pdf = os.path.join(tempfile.gettempdir(), f'badges_{int(datetime.utcnow().timestamp())}.pdf')
        generator.generate_pdf(output_pdf)
        
        logger.info(f"Generated badges PDF: {output_pdf}")
        
        # Send file
        return send_file(
            output_pdf,
            as_attachment=True,
            download_name='badges.pdf',
            mimetype='application/pdf'
        )
        
    except Exception as e:
        logger.exception("Error generating badges")
        return jsonify({'error': str(e)}), 500


@app.route('/api/badges/generate-async', methods=['POST'])
@login_required
def generate_badges_async():
    """Start badge generation in background and return a job id for progress polling."""
    data = request.get_json() or {}
    excel_file = data.get('excel_file')
    template_id = data.get('template_id')
    preprocessing_template_id = data.get('preprocessingTemplateId')

    if not excel_file:
        return jsonify({'error': 'Excel file path is required'}), 400
    if not template_id:
        return jsonify({'error': 'Template ID is required'}), 400
    if not os.path.exists(excel_file):
        return jsonify({'error': 'Excel file not found'}), 404

    template = BadgeTemplate.query.get(template_id)
    if not template:
        return jsonify({'error': 'Template not found'}), 404

    svg_path = resolve_badge_svg_path(template)
    if not os.path.exists(svg_path):
        return jsonify({'error': 'Built-in badge SVG template not found'}), 500
    club_logo_path, club_logo_error = _resolve_badge_club_logo(template, svg_path)
    if club_logo_error:
        return jsonify({'error': club_logo_error}), 400

    download_name = 'badges.pdf'
    job_id = _init_badge_job(phase="generate_badges", download_name=download_name)

    def run_job():
        try:
            with app.app_context():
                svg_path = resolve_badge_svg_path(template)
                if not os.path.exists(svg_path):
                    raise FileNotFoundError("Built-in badge SVG template not found")

                column_mappings = json.loads(template.column_mappings)

                generator = BadgeGenerator(
                    excel_file=excel_file,
                    svg_template_path=svg_path,
                    column_mappings=column_mappings,
                    afrp_logo_path=app.config['AFRP_LOGO_PATH'],
                    club_logo_path=club_logo_path,
                    club_logo_width=template.club_logo_width,
                    club_logo_height=template.club_logo_height,
                    avery_template=template.avery_template,
                    show_outlines=template.show_outlines,
                    background_id=template.background_id or 'white',
                    backgrounds_folder=app.config['BADGE_BACKGROUNDS_FOLDER'],
                    element_layout=_template_element_layout(template),
                    display_name_config=_template_display_name_config(template),
                    **_badge_generator_meal_kwargs(preprocessing_template_id),
                )

                total = len(generator.df) if hasattr(generator, "df") else 0
                _update_badge_job(job_id, total=total, message="Generating badges...")

                def progress_callback(current, total_count, message):
                    _update_badge_job(
                        job_id,
                        current=int(current),
                        total=int(total_count),
                        message=message or "Generating badges..."
                    )

                output_pdf = os.path.join(
                    tempfile.gettempdir(),
                    f'badges_{job_id}_{int(datetime.utcnow().timestamp())}.pdf'
                )

                generator.generate_pdf(output_pdf, progress_callback=progress_callback)
                _update_badge_job(job_id, status="completed", output_pdf_path=output_pdf, message="Complete")
        except Exception as e:
            logger.exception("Async badge generation failed")
            _update_badge_job(job_id, status="failed", error=str(e), message="Failed")

    threading.Thread(target=run_job, daemon=True).start()
    return jsonify({'job_id': job_id})


@app.route('/api/badges/pull-process-generate-async', methods=['POST'])
@login_required
def badges_pull_process_generate_async():
    """Start pull+process+generate in background and return a job id for progress polling."""
    data = request.get_json() or {}
    template_id = data.get('template_id')
    if not template_id:
        return jsonify({'error': 'template_id is required'}), 400

    badge_template = BadgeTemplate.query.get(int(template_id))
    if not badge_template:
        return jsonify({'error': 'Badge template not found'}), 404

    svg_path = resolve_badge_svg_path(badge_template)
    if not os.path.exists(svg_path):
        return jsonify({'error': 'Built-in badge SVG template not found'}), 500

    club_logo_path, club_logo_error = _resolve_badge_club_logo(badge_template, svg_path)
    if club_logo_error:
        return jsonify({'error': club_logo_error}), 400

    campaign_name = (data.get('campaign_name') or 'campaign').replace(" ", "_")
    download_name = f'badges_{campaign_name}.pdf'
    job_id = _init_badge_job(phase="pull_process_generate", download_name=download_name)
    requesting_user_id = current_user.id

    def run_job():
        try:
            with app.app_context():
                user = User.query.get(requesting_user_id)
                if not user:
                    raise ValueError('User not found')

                _update_badge_job(job_id, message="Pulling and processing data...")

                with badge_pipeline_job():
                    campaign_id = data.get('campaign_id')
                    campaign_name_local = data.get('campaign_name')
                    event_name = data.get('event', 'Default')
                    sub_event = data.get('subEvent')
                    inclusion_list = data.get('inclusionList')
                    created_on_filter = data.get('createdOnFilter')
                    group_by_household = bool(data.get('groupByHousehold', False))
                    preprocessing_template_id = data.get('preprocessingTemplateId')

                    if not campaign_id and not campaign_name_local:
                        raise ValueError('Campaign ID or name is required')

                    crm_client = DynamicsCRMClient()
                    if campaign_name_local and not campaign_id:
                        campaign_info = crm_client.get_campaign_by_name(campaign_name_local)
                        if not campaign_info:
                            raise ValueError(f'Campaign {campaign_name_local} not found')
                        campaign_id = campaign_info['id']

                    denied = _require_campaign_access(user, campaign_id, sub_event, crm_client)
                    if denied:
                        raise ValueError(denied[0].get_json().get('error', 'Access denied'))

                    upload_folder = app.config['UPLOAD_FOLDER']
                    os.makedirs(upload_folder, mode=0o777, exist_ok=True)
                    store = BadgeDataStore(upload_folder)
                    pull_campaign_to_store(crm_client, campaign_id, store)

                    preprocessor_class = _resolve_preprocessor_class(preprocessing_template_id)

                    config_obj = _preprocessing_config_with_meal(
                        preprocessing_template_id,
                        main_event=event_name,
                        sub_event=sub_event,
                        inclusion_list=inclusion_list,
                        created_on_filter=created_on_filter,
                        group_by_household=group_by_household,
                        household_cache_path=app.config['HOUSEHOLD_CACHE_PATH'],
                    )

                    with tempfile.TemporaryDirectory() as temp_dir:
                        _copy_badge_sources_to_dir(upload_folder, temp_dir)

                        original_dir = os.getcwd()
                        os.chdir(temp_dir)
                        try:
                            _update_badge_job(job_id, message="Processing and merging data...")
                            processor = EventRegistrationProcessorV3(
                                config=config_obj, preprocessor_class=preprocessor_class
                            )
                            result_df = processor.transform_and_merge()

                            processed_excel = os.path.join(temp_dir, 'processed_data.xlsx')
                            result_df.to_excel(processed_excel, index=False)
                            del result_df
                            gc.collect()

                            svg_path = resolve_badge_svg_path(badge_template)
                            column_mappings = json.loads(badge_template.column_mappings)

                            generator = BadgeGenerator(
                                excel_file=processed_excel,
                                svg_template_path=svg_path,
                                column_mappings=column_mappings,
                                afrp_logo_path=app.config['AFRP_LOGO_PATH'],
                                club_logo_path=club_logo_path,
                                club_logo_width=badge_template.club_logo_width,
                                club_logo_height=badge_template.club_logo_height,
                                avery_template=badge_template.avery_template,
                                show_outlines=badge_template.show_outlines,
                                background_id=badge_template.background_id or 'white',
                                backgrounds_folder=app.config['BADGE_BACKGROUNDS_FOLDER'],
                                element_layout=_template_element_layout(badge_template),
                                display_name_config=_template_display_name_config(badge_template),
                                **_badge_generator_meal_kwargs(preprocessing_template_id),
                            )

                            total = len(generator.df) if hasattr(generator, "df") else 0
                            _update_badge_job(job_id, total=total, message="Generating badges...")

                            def progress_callback(current, total_count, message):
                                _update_badge_job(
                                    job_id,
                                    current=int(current),
                                    total=int(total_count),
                                    message=message or "Generating badges..."
                                )

                            output_pdf = os.path.join(
                                tempfile.gettempdir(),
                                f'badges_{job_id}_{int(datetime.utcnow().timestamp())}.pdf'
                            )
                            generator.generate_pdf(output_pdf, progress_callback=progress_callback)
                            _update_badge_job(
                                job_id,
                                status="completed",
                                output_pdf_path=output_pdf,
                                message="Complete",
                            )
                        finally:
                            os.chdir(original_dir)

        except PipelineBusyError as e:
            logger.warning("Async pull-process-generate busy: %s", e)
            _update_badge_job(job_id, status="failed", error=str(e), message="Failed")
        except InsufficientMemoryError as e:
            logger.warning("Async pull-process-generate memory: %s", e)
            _update_badge_job(job_id, status="failed", error=str(e), message="Failed")
        except Exception as e:
            logger.exception("Async pull-process-generate failed")
            _update_badge_job(job_id, status="failed", error=str(e), message="Failed")

    threading.Thread(target=run_job, daemon=True).start()
    return jsonify({'job_id': job_id})


@app.route('/api/badges/jobs/<job_id>', methods=['GET'])
@login_required
@limiter.exempt
def get_badge_job(job_id):
    """Get progress for an async badge generation job."""
    job = _get_badge_job(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404

    total = int(job.get("total") or 0)
    current = int(job.get("current") or 0)
    percent = 0
    if total > 0:
        percent = min(100, int((current / total) * 100))
    elif job.get("status") == "completed":
        percent = 100

    return jsonify({
        'job_id': job_id,
        'status': job.get('status'),
        'phase': job.get('phase'),
        'message': job.get('message'),
        'current': current,
        'total': total,
        'percent': percent,
        'error': job.get('error')
    })


@app.route('/api/badges/jobs/<job_id>/download', methods=['GET'])
@login_required
@limiter.exempt
def download_badge_job(job_id):
    """Download the PDF for a completed async badge generation job."""
    job = _get_badge_job(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    if job.get("status") != "completed":
        return jsonify({'error': 'Job not completed'}), 409
    output_path = job.get("output_pdf_path")
    if not output_path or not os.path.exists(output_path):
        return jsonify({'error': 'Output file missing'}), 404
    return send_file(
        output_path,
        as_attachment=True,
        download_name=job.get("download_name") or "badges.pdf",
        mimetype='application/pdf'
    )


@app.route('/api/badges/pull-process-generate', methods=['POST'])
@login_required
def badges_pull_process_generate():
    """Combined endpoint: pull data, process, and generate badges."""
    try:
        data = request.get_json()
        
        # First, pull and process data (reuse existing logic)
        # This will save the processed Excel file
        campaign_id = data.get('campaign_id')
        campaign_name = data.get('campaign_name')
        event_name = data.get('event', 'Default')
        sub_event = data.get('subEvent')
        inclusion_list = data.get('inclusionList')
        created_on_filter = data.get('createdOnFilter')
        group_by_household = bool(data.get('groupByHousehold', False))
        preprocessing_template_id = data.get('preprocessingTemplateId')
        
        if not campaign_id and not campaign_name:
            return jsonify({'error': 'Campaign ID or name is required'}), 400
        
        # Initialize CRM client
        crm_client = DynamicsCRMClient()
        
        # Get campaign ID if only name provided
        if campaign_name and not campaign_id:
            campaign_info = crm_client.get_campaign_by_name(campaign_name)
            if not campaign_info:
                return jsonify({'error': f'Campaign {campaign_name} not found'}), 404
            campaign_id = campaign_info['id']

        denied = _require_campaign_access(
            current_user, campaign_id, sub_event, crm_client
        )
        if denied:
            return denied
        
        # Pull CRM data into memory-efficient Parquet store
        upload_folder = app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, mode=0o777, exist_ok=True)

        try:
            with badge_pipeline_job():
                store = BadgeDataStore(upload_folder)
                pull_campaign_to_store(crm_client, campaign_id, store)
        except PipelineBusyError as exc:
            return jsonify({'error': str(exc)}), 409
        except InsufficientMemoryError as exc:
            return jsonify({'error': str(exc)}), 503
        
        preprocessor_class = _resolve_preprocessor_class(preprocessing_template_id)
        
        config_obj = _preprocessing_config_with_meal(
            preprocessing_template_id,
            main_event=event_name,
            sub_event=sub_event,
            inclusion_list=inclusion_list,
            created_on_filter=created_on_filter,
            group_by_household=group_by_household,
            household_cache_path=app.config['HOUSEHOLD_CACHE_PATH'],
        )
        
        with tempfile.TemporaryDirectory() as temp_dir:
            _copy_badge_sources_to_dir(upload_folder, temp_dir)
            original_dir = os.getcwd()
            os.chdir(temp_dir)
            
            try:
                processor = EventRegistrationProcessorV3(config=config_obj, preprocessor_class=preprocessor_class)
                result_df = processor.transform_and_merge()
                
                # Save processed Excel file
                processed_excel = os.path.join(temp_dir, 'processed_data.xlsx')
                result_df.to_excel(processed_excel, index=False)
                
                # Now generate badges if template specified
                template_id = data.get('template_id')
                if template_id:
                    template = BadgeTemplate.query.get(template_id)
                    if not template:
                        return jsonify({'error': 'Badge template not found'}), 404
                    
                    svg_path = resolve_badge_svg_path(template)
                    club_logo_path, club_logo_error = _resolve_badge_club_logo(template, svg_path)
                    if club_logo_error:
                        return jsonify({'error': club_logo_error}), 400
                    if club_logo_path:
                        logger.info(f"Using club logo: {club_logo_path}")
                    
                    avery_template = template.avery_template
                    column_mappings = json.loads(template.column_mappings)
                    
                    generator = BadgeGenerator(
                        excel_file=processed_excel,
                        svg_template_path=svg_path,
                        column_mappings=column_mappings,
                        afrp_logo_path=app.config['AFRP_LOGO_PATH'],
                        club_logo_path=club_logo_path,
                        club_logo_width=template.club_logo_width,
                        club_logo_height=template.club_logo_height,
                        avery_template=avery_template,
                        show_outlines=template.show_outlines,
                        background_id=template.background_id or 'white',
                        backgrounds_folder=app.config['BADGE_BACKGROUNDS_FOLDER'],
                        element_layout=_template_element_layout(template),
                        display_name_config=_template_display_name_config(template),
                        **_badge_generator_meal_kwargs(preprocessing_template_id),
                    )
                    
                    output_pdf = os.path.join(tempfile.gettempdir(), f'badges_{int(datetime.utcnow().timestamp())}.pdf')
                    generator.generate_pdf(output_pdf)
                    
                    return send_file(
                        output_pdf,
                        as_attachment=True,
                        download_name=f'badges_{campaign_name.replace(" ", "_")}.pdf',
                        mimetype='application/pdf'
                    )
                else:
                    # If no template specified, just return the processed Excel
                    return send_file(
                        processed_excel,
                        as_attachment=True,
                        download_name=f'MAIL_MERGE_{campaign_name.replace(" ", "_")}.xlsx',
                        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    )
                    
            finally:
                os.chdir(original_dir)
                
    except Exception as e:
        logger.exception("Error in combined pull-process-generate")
        return jsonify({'error': str(e)}), 500
