from flask import Flask, render_template, request, send_file, jsonify, Response
from werkzeug.utils import secure_filename
import qrcode
from io import BytesIO, StringIO
from PIL import Image
import numpy as np
import sys
import threading
import queue
from datetime import datetime, time
import re
from contextlib import redirect_stdout
import logging
import atexit
import shutil
import tempfile
import traceback
from utils.url_generator import extract_event_id, generate_event_registration_url, generate_event_summary_url
from utils.magazine.download_latest_magazine import main as magazine_main
from utils.magazine.scheduler import db, Schedule, JobRun, schedule_manager, EventViewConfig
from utils.badges.pre_processing_module import PreprocessingBase
from utils.badges.event_preprocessing import preprocessing_implementations
from utils.badges.event_preprocessing.default import DefaultPreprocessing
from utils.badges.file_validator import FileValidator, FileTypes
from utils.badges.convert_to_mail_merge_v3 import EventRegistrationProcessorV3
from utils.dynamics_crm import DynamicsCRMClient
import os
import pandas as pd
from utils.badges.pre_processing_module import PreprocessingConfig
from typing import Dict, Type

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Log that the script is starting
logger.info("Starting app.py...")

# Check if running in Docker
IN_DOCKER = os.environ.get('DOCKER_CONTAINER', False)
BASE_PATH = '/app' if IN_DOCKER else '.'

# Ensure required directories exist with proper permissions
for dir_path in ['data', 'temp', 'downloads']:
    full_path = os.path.join(BASE_PATH, dir_path)
    os.makedirs(full_path, exist_ok=True)
    os.chmod(full_path, 0o777)

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

logger.info(f"Database URI configured: {db_uri}")

# Initialize extensions
db.init_app(app)

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

# Log registered preprocessors at startup
logger.info(f"Registered {len(preprocessing_implementations)} preprocessor(s): {list(preprocessing_implementations.keys())}")

@app.route('/', methods=['GET'])
def home():
    # This route displays the home page with tiles
    return render_template('home.html')

@app.route('/qr', methods=['GET', 'POST'])
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
def magazine():
    schedules = Schedule.query.all()
    return render_template('magazine.html', schedules=schedules)

@app.route('/event', methods=['GET', 'POST'])
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

@app.route('/api/available-events', methods=['GET'])
def get_available_events():
    """Endpoint to fetch dynamically discovered event preprocessors."""
    logger.debug("Fetching available events")
    try:
        events = list(preprocessing_implementations.keys())
        return jsonify({'events': events})
    except Exception as e:
        logger.exception("Failed to fetch available events")
        return jsonify({'error': f'Failed to fetch events: {str(e)}'}), 500

@app.route('/run-magazine-download')
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
def badges():
    # Pass empty events list initially - will be populated via AJAX after file upload
    return render_template('badges.html', events=[])

@app.route('/api/pull-crm-data', methods=['POST'])
def pull_crm_data():
    """Pull data directly from Dynamics CRM."""
    try:
        data = request.get_json()
        view_id = data.get('view_id')
        data_type = data.get('data_type')
        
        if not view_id or not data_type:
            return jsonify({'error': 'View ID and data type are required'}), 400
            
        # Initialize the CRM client
        crm_client = DynamicsCRMClient()
        
        # Download the specific data type
        df = crm_client.download_data_by_type(data_type, view_id)
        
        # Map CRM data types to file types
        data_type_mapping = {
            'event_guests': FileTypes.REGISTRATION,
            'qr_codes': FileTypes.QR_CODES,
            'table_reservations': FileTypes.SEATING,
            'form_responses': FileTypes.FORM_RESPONSES
        }
        
        file_type = data_type_mapping.get(data_type, data_type)
        
        # Remove any existing file of the same type
        existing_files = [f for f in os.listdir(app.config['UPLOAD_FOLDER']) 
                         if f.startswith(f"{file_type}_")]
        for existing_file in existing_files:
            try:
                existing_path = os.path.join(app.config['UPLOAD_FOLDER'], existing_file)
                if os.path.exists(existing_path):
                    os.remove(existing_path)
                    logger.debug(f"Removed existing file: {existing_file}")
            except Exception as e:
                logger.warning(f"Could not remove existing file {existing_file}: {e}")
        
        # Save to a temporary Excel file with proper file type prefix
        temp_file = os.path.join(app.config['UPLOAD_FOLDER'], f"{file_type}_crm_data.xlsx")
        df.to_excel(temp_file, index=False)
        
        return jsonify({
            'message': f'Successfully pulled {data_type} data from CRM',
            'file': temp_file,
            'type': file_type
        })
        
    except Exception as e:
        logger.error(f"Error pulling CRM data: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Handle file upload."""
    logger.debug("Starting file upload handler")
    save_path = None
    
    try:
        # Verify upload folder exists and is writable
        upload_folder = app.config['UPLOAD_FOLDER']
        if not os.path.exists(upload_folder):
            logger.warning(f"Upload folder does not exist, recreating: {upload_folder}")
            os.makedirs(upload_folder, mode=0o777, exist_ok=True)
        
        if not os.access(upload_folder, os.W_OK):
            logger.warning(f"Upload folder not writable, fixing permissions: {upload_folder}")
            os.chmod(upload_folder, 0o777)
        
        logger.debug(f"Upload folder ready: {upload_folder}")
        
        if 'file' not in request.files:
            logger.error("No file part in request")
            return jsonify({'error': 'No file part'}), 400
        
        file = request.files['file']
        if file.filename == '':
            logger.error("No selected file")
            return jsonify({'error': 'No selected file'}), 400
        
        logger.debug(f"Processing file: {file.filename}")
        
        if not FileValidator.is_valid_excel(file.filename):
            logger.error(f"Invalid file type: {file.filename}")
            return jsonify({'error': 'Invalid file type - must be .xlsx'}), 400
        
        filename = secure_filename(file.filename)
        logger.debug(f"Secured filename: {filename}")
        
        file_type = FileValidator.get_file_type(filename)
        logger.debug(f"Detected file type: {file_type}")
        
        if file_type is None:
            logger.error(f"Unable to determine file type for: {filename}")
            logger.error("Expected file name patterns:")
            logger.error("  - Registration List: '*Registration List*.xlsx'")
            logger.error("  - Seating Chart: '*Seating Chart*.xlsx'")
            logger.error("  - QR Codes: '*QR Codes*.xlsx'")
            logger.error("  - Form Responses: '*(Form|From) Responses*.xlsx'")
            return jsonify({
                'error': 'Unable to determine file type. File name must contain one of: "Registration List", "Seating Chart", "QR Codes", or "Form Responses"'
            }), 400
        
        try:
            # Remove any existing file of the same type
            existing_files = [f for f in os.listdir(upload_folder) 
                            if f.startswith(f"{file_type}_")]
            for existing_file in existing_files:
                try:
                    existing_path = os.path.join(upload_folder, existing_file)
                    if os.path.exists(existing_path):
                        os.chmod(existing_path, 0o666)  # Make file writable
                        os.remove(existing_path)
                        logger.debug(f"Removed existing file: {existing_file}")
                except Exception as e:
                    logger.warning(f"Could not remove existing file {existing_file}: {e}")
            
            # Save new file with type prefix
            save_path = os.path.join(upload_folder, f"{file_type}_{filename}")
            logger.debug(f"Saving file to: {save_path}")
            
            # Create a temporary file first
            temp_fd, temp_path = tempfile.mkstemp(dir=upload_folder)
            os.close(temp_fd)
            
            logger.debug(f"Created temporary file: {temp_path}")
            
            # Save to temporary file first
            file.save(temp_path)
            os.chmod(temp_path, 0o666)
            
            # Move to final location
            shutil.move(temp_path, save_path)
            os.chmod(save_path, 0o666)
            
            logger.debug(f"File saved successfully: {save_path}")
            
            # Verify file was saved and is readable
            if not os.path.exists(save_path):
                raise FileNotFoundError(f"File was not saved: {save_path}")
            
            # Try to read the file to verify it's accessible
            with open(save_path, 'rb') as f:
                f.read(1)
            
            return jsonify({
                'message': 'File uploaded successfully',
                'type': file_type,
                'path': save_path
            })
            
        except Exception as e:
            logger.exception(f"Error saving file to {save_path if save_path else 'unknown path'}")
            return jsonify({'error': f'Error saving file: {str(e)}'}), 500
            
    except Exception as e:
        logger.exception("Error in upload handler")
        return jsonify({'error': f'Upload error: {str(e)}'}), 500

@app.route('/api/get_sub_events', methods=['POST'])
def get_sub_events():
    """Get available sub-events from registration file."""
    logger.debug("Starting sub-events retrieval")
    try:
        # Ensure upload folder exists
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        # Find registration file
        reg_files = [f for f in os.listdir(app.config['UPLOAD_FOLDER']) 
                    if f.startswith(f"{FileTypes.REGISTRATION}_")]
        
        if not reg_files:
            logger.error("Registration file not uploaded")
            return jsonify({'error': 'Registration file not uploaded'}), 400
            
        # Read registration data
        reg_file = os.path.join(app.config['UPLOAD_FOLDER'], reg_files[0])
        logger.debug(f"Reading registration file: {reg_file}")
        df = pd.read_excel(reg_file)
        
        # Clean column names
        df.columns = df.columns.str.strip()
        
        # Handle both 'Event' and 'Event ' column names
        event_col = 'Event' if 'Event' in df.columns else 'Event '
        status_col = 'Status Reason' if 'Status Reason' in df.columns else 'Status'
        
        logger.debug(f"Using event column: {event_col}")
        logger.debug(f"Using status column: {status_col}")
        logger.debug(f"Available columns: {df.columns.tolist()}")
        
        # Get unique events from paid registrations
        paid_df = df[df[status_col] == 'Paid']
        events = sorted(paid_df[event_col].unique().tolist())
        logger.debug(f"Found sub-events: {events}")
        
        return jsonify({'events': events})
        
    except Exception as e:
        logger.exception("Error retrieving sub-events")
        return jsonify({'error': str(e)}), 500


@app.route('/api/process', methods=['POST'])
def process_files():
    """Process uploaded files and generate mail merge."""
    logger.debug("Starting file processing")
    try:
        data = request.get_json()
        if not data:
            logger.error("No JSON data received")
            return jsonify({'error': 'No data received'}), 400
            
        event_name = data.get('event')
        sub_event = data.get('subEvent')
        inclusion_list = data.get('inclusionList')
        created_on_filter = data.get('createdOnFilter')
        
        logger.debug(f"Processing request for event: {event_name}, sub_event: {sub_event}, inclusion list: {inclusion_list}, date filter: {created_on_filter}")
        
        if not event_name:
            logger.error("No event name provided")
            return jsonify({'error': 'Event name is required'}), 400
        
        # Get the preprocessing implementation for the selected event
        preprocessor_class = preprocessing_implementations.get(event_name, DefaultPreprocessing)
        if preprocessor_class == DefaultPreprocessing:
            logger.warning(f"No specific preprocessor found for '{event_name}', using DefaultPreprocessing")
        
        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            logger.debug(f"Created temporary directory: {temp_dir}")
            os.makedirs(temp_dir, mode=0o777, exist_ok=True)
            
            # Copy uploaded files to temp directory with correct names
            files = {}
            for file_type in FileValidator.get_required_file_types():
                matching_files = [f for f in os.listdir(app.config['UPLOAD_FOLDER']) 
                                if f.startswith(f"{file_type}_")]
                if not matching_files:
                    logger.error(f"Missing required file: {file_type}")
                    return jsonify({'error': f'Missing required file: {file_type}'}), 400
                source = os.path.join(app.config['UPLOAD_FOLDER'], matching_files[0])
                dest = os.path.join(temp_dir, os.path.basename(matching_files[0]))
                logger.debug(f"Copying {file_type} file from {source} to {dest}")
                shutil.copy2(source, dest)
                files[file_type] = dest
            
            # Change to temp directory
            original_dir = os.getcwd()
            os.chdir(temp_dir)
            logger.debug(f"Changed working directory to: {temp_dir}")
            
            try:
                # Create preprocessing config
                config = PreprocessingConfig(
                    main_event=event_name,
                    sub_event=sub_event if sub_event else None,
                    inclusion_list=inclusion_list if inclusion_list else None,
                    created_on_filter=created_on_filter if created_on_filter else None
                )
                logger.debug(f"Created preprocessing config: {config.__dict__}")
                
                # Initialize processor with config and selected preprocessor class
                processor = EventRegistrationProcessorV3(
                    config=config,
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
        logger.exception("Error in process_files handler")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

# Badge Generator V2 Routes

@app.route('/badges-v2')
def badges_v2():
    """Badge Generator V2 page with automated CRM integration."""
    return render_template('badges_v2.html')


@app.route('/api/campaigns/open', methods=['GET'])
def get_open_campaigns():
    """Get list of open campaigns from Dynamics CRM."""
    try:
        crm_client = DynamicsCRMClient()
        campaigns = crm_client.get_open_campaigns()
        
        logger.info(f"Retrieved {len(campaigns)} open campaigns")
        return jsonify({'campaigns': campaigns})
        
    except Exception as e:
        logger.error(f"Error fetching open campaigns: {str(e)}")
        return jsonify({'error': f'Failed to fetch open campaigns: {str(e)}'}), 500

@app.route('/api/campaigns/<campaign_id>/sub-events', methods=['GET'])
def get_campaign_sub_events(campaign_id):
    """Get list of sub-events for a specific campaign from Dynamics CRM."""
    try:
        crm_client = DynamicsCRMClient()
        sub_events = crm_client.get_sub_events(campaign_id)
        
        logger.info(f"Retrieved {len(sub_events)} sub-events for campaign {campaign_id}")
        return jsonify({'sub_events': sub_events})
        
    except Exception as e:
        logger.error(f"Error fetching sub-events for campaign {campaign_id}: {str(e)}")
        return jsonify({'error': f'Failed to fetch sub-events: {str(e)}'}), 500

@app.route('/api/debug/contact-fields', methods=['GET'])
def debug_contact_fields():
    """Debug endpoint to discover contact fields in Dynamics."""
    try:
        crm_client = DynamicsCRMClient()
        
        # Get multiple contacts to check title and local club fields  
        endpoint = "contacts?$top=10"
        response = crm_client._make_request(endpoint)
        records = response.get('value', [])
        
        contacts_data = []
        for record in records:
            # Extract only the relevant fields we care about
            contact_info = {
                'name': f"{record.get('firstname', '')} {record.get('lastname', '')}",
                'salutation': record.get('salutation'),
                'salutation_formatted': record.get('salutation@OData.Community.Display.V1.FormattedValue'),
                'aha_title': record.get('aha_title'),
                'aha_title_formatted': record.get('aha_title@OData.Community.Display.V1.FormattedValue'),
                'jobtitle': record.get('jobtitle'),
                'aha_localclub': record.get('aha_localclub'),
                '_aha_localclub2_value': record.get('_aha_localclub2_value'),
                '_aha_localclub2_formatted': record.get('_aha_localclub2_value@OData.Community.Display.V1.FormattedValue'),
            }
            contacts_data.append(contact_info)
        
        return jsonify({
            'total_contacts': len(contacts_data),
            'contacts': contacts_data
        })
        
    except Exception as e:
        logger.error(f"Error fetching contact fields: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/badges-v2/pull-and-process', methods=['POST'])
def badges_v2_pull_and_process():
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
        
        # Create temporary directory for processing
        upload_folder = app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, mode=0o777, exist_ok=True)
        
        # Map data types to file types
        data_type_mapping = {
            'event_guests': {
                'file_type': FileTypes.REGISTRATION,
                'display_name': 'Event Guests'
            },
            'qr_codes': {
                'file_type': FileTypes.QR_CODES,
                'display_name': 'QR Codes'
            },
            'table_reservations': {
                'file_type': FileTypes.SEATING,
                'display_name': 'Table Reservations'
            },
            'form_responses': {
                'file_type': FileTypes.FORM_RESPONSES,
                'display_name': 'Form Responses'
            }
        }
        
        # Pull all 4 data types from CRM
        for data_type, info in data_type_mapping.items():
            try:
                logger.info(f"Pulling {info['display_name']} from CRM...")
                
                # Use campaign-based filtering (main + sub-events)
                df = crm_client.download_data_by_type_filtered(data_type, None, campaign_id)
                
                logger.info(f"Pulled {len(df)} records for {info['display_name']}")
                
                # Remove existing file of the same type
                existing_files = [f for f in os.listdir(upload_folder) 
                                if f.startswith(f"{info['file_type']}_")]
                for existing_file in existing_files:
                    try:
                        existing_path = os.path.join(upload_folder, existing_file)
                        if os.path.exists(existing_path):
                            os.remove(existing_path)
                            logger.debug(f"Removed existing file: {existing_file}")
                    except Exception as e:
                        logger.warning(f"Could not remove existing file {existing_file}: {e}")
                
                # Additional cleanup for seating data to prevent type issues
                if data_type == 'table_reservations' and 'Event' in df.columns:
                    import numpy as np
                    # Ensure Event column is fully string type before saving
                    df['Event'] = df['Event'].replace({np.nan: '', None: ''})
                    df['Event'] = df['Event'].astype(str).replace('nan', '').replace('None', '')
                    logger.debug(f"Cleaned Event column in seating data. Types: {df['Event'].apply(type).unique()}")
                
                # Save to Excel file with proper naming
                temp_file = os.path.join(upload_folder, f"{info['file_type']}_crm_data.xlsx")
                df.to_excel(temp_file, index=False)
                logger.debug(f"Saved {info['display_name']} data to: {temp_file}")
                
            except Exception as e:
                logger.error(f"Error pulling {info['display_name']}: {str(e)}")
                return jsonify({'error': f'Failed to pull {info["display_name"]}: {str(e)}'}), 500
        
        # Now process the files using existing logic
        logger.info("All data pulled successfully, starting processing...")
        
        if not event_name:
            logger.error("No event name provided for processing")
            return jsonify({'error': 'Event name is required'}), 400
        
        # Get the preprocessing implementation
        preprocessor_class = preprocessing_implementations.get(event_name, DefaultPreprocessing)
        if preprocessor_class == DefaultPreprocessing:
            logger.warning(f"No specific preprocessor found for '{event_name}', using DefaultPreprocessing")
        
        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            logger.debug(f"Created temporary directory: {temp_dir}")
            os.makedirs(temp_dir, mode=0o777, exist_ok=True)
            
            # Copy uploaded files to temp directory
            files = {}
            for file_type in FileValidator.get_required_file_types():
                matching_files = [f for f in os.listdir(upload_folder) 
                                if f.startswith(f"{file_type}_")]
                if not matching_files:
                    logger.error(f"Missing required file: {file_type}")
                    return jsonify({'error': f'Missing required file: {file_type}'}), 400
                source = os.path.join(upload_folder, matching_files[0])
                dest = os.path.join(temp_dir, os.path.basename(matching_files[0]))
                logger.debug(f"Copying {file_type} file from {source} to {dest}")
                shutil.copy2(source, dest)
                files[file_type] = dest
            
            # Change to temp directory
            original_dir = os.getcwd()
            os.chdir(temp_dir)
            logger.debug(f"Changed working directory to: {temp_dir}")
            
            try:
                # Create preprocessing config
                config_obj = PreprocessingConfig(
                    main_event=event_name,
                    sub_event=sub_event if sub_event else None,
                    inclusion_list=inclusion_list if inclusion_list else None,
                    created_on_filter=created_on_filter if created_on_filter else None
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