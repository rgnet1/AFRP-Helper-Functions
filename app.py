from flask import Flask, render_template, request, send_file, jsonify, Response
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
from utils.url_generator import extract_event_id, generate_event_registration_url, generate_event_summary_url
from utils.magazine.download_latest_magazine import main as magazine_main
from utils.magazine.scheduler import db, Schedule, JobRun, schedule_manager
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Log that the script is starting
logger.info("Starting app.py...")

# Check if running in Docker
IN_DOCKER = os.environ.get('DOCKER_CONTAINER', False)
BASE_PATH = '/app' if IN_DOCKER else '.'

# Ensure data directory exists with proper permissions
data_dir = os.path.join(BASE_PATH, 'data')
os.makedirs(data_dir, exist_ok=True)
os.chmod(data_dir, 0o777)

# Initialize Flask app
app = Flask(__name__)

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

@app.route('/event')
def event_page():
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
