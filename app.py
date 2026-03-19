from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import requests
from submit_report import get_coordinates
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from flask import session
from flask_migrate import Migrate
from functools import wraps  # Added for the require_authority decorator
import logging
from collections import defaultdict
from datetime import datetime,timedelta
import time
import atexit
from apscheduler.schedulers.background import BackgroundScheduler
import os
from dotenv import load_dotenv
from llm_vision import is_disaster_image
from usgs_noaa import fetch_usgs_earthquakes, fetch_noaa_alerts
load_dotenv()
import base64
import urllib.parse
# Import models and db instance
# from models import db, User, Report, DangerZone, BroadcastHistory
from models import db, User, Report, DangerZone, BroadcastHistory, ResourceCamp, Feedback
# Load environment variables at the top of app.py

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Supabase / any cloud postgres may provide postgres:// but SQLAlchemy needs postgresql://
_db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:admin@localhost/disaster_management')
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}

# Configure Flask-Mail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')

mail = Mail(app)

# Add Flask-Caching for weather API (optional, for performance)
from flask_caching import Cache
cache = Cache(config={'CACHE_TYPE': 'simple'})
cache.init_app(app)

# Initialize extensions
db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
migrate = Migrate(app, db)

@app.route('/api/maps/key')
def get_maps_api_key():
    return jsonify({'api_key': os.getenv('GOOGLE_MAPS_API_KEY')})

@login_manager.user_loader
def load_user(user_id):
    logger.debug(f"Loading user with ID: {user_id}")
    return User.query.get(int(user_id))

# Custom decorator for authority role check
def require_authority(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'authority':
            flash('Access denied. Authority role required.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Ensure tables exist
with app.app_context():
    db.create_all()

# Disaster Classification Function (unchanged)
def classify_report(text):
    text_lower = text.lower()
    if any(keyword in text_lower for keyword in ["fire", "burning", "flames"]):
        return "Fire"
    elif any(keyword in text_lower for keyword in ["flood", "waterlogging", "heavy rain"]):
        return "Flood"
    elif any(keyword in text_lower for keyword in ["earthquake", "tremor", "seismic"]):
        return "Earthquake"
    return "Unknown"

# ---------------------------------------------------------------------------
# Location geocoding helpers
# ---------------------------------------------------------------------------

def _build_geocoding_queries(location_field):
    """Build geocoding queries from explicit user-provided location text only."""
    if location_field and location_field.strip():
        return [location_field.strip()]
    return []


# Proximity threshold for deduplicating danger zones (~200 m in degrees)
_DEDUP_RADIUS = 0.002


def _find_zone_by_proximity(lat, lng):
    """Return an existing DangerZone within _DEDUP_RADIUS of (lat, lng), or None."""
    return DangerZone.query.filter(
        DangerZone.latitude.between(lat - _DEDUP_RADIUS, lat + _DEDUP_RADIUS),
        DangerZone.longitude.between(lng - _DEDUP_RADIUS, lng + _DEDUP_RADIUS)
    ).first()


# ---------------------------------------------------------------------------
# Danger zone decay scheduler job
# ---------------------------------------------------------------------------

import math as _math

_DECAY_LAMBDA = 0.05   # e^(-λ·h);  half-life ≈ 14 hours
_MIN_SEVERITY = 0.05   # zones below this are auto-deleted (~3 days silence)


def decay_danger_zones():
    """Exponentially decay severity of all danger zones and delete stale ones.
    Called every 6 hours by APScheduler.
    """
    with app.app_context():
        now = datetime.utcnow()
        zones = DangerZone.query.all()
        deleted = 0
        updated = 0
        for zone in zones:
            if zone.last_reported_at is None:
                zone.last_reported_at = now
            hours_elapsed = (now - zone.last_reported_at).total_seconds() / 3600.0
            # Decay the severity using exponential decay
            zone.severity = (zone.severity or 1.0) * _math.exp(-_DECAY_LAMBDA * hours_elapsed)
            if zone.severity < _MIN_SEVERITY:
                db.session.delete(zone)
                deleted += 1
            else:
                updated += 1
        db.session.commit()
        logger.info(f"[decay_danger_zones] updated={updated}, deleted={deleted}")

# Weather API helper function
@cache.cached(timeout=1800)  # Cache for 30 minutes
def get_weather(location):
    api_key = os.getenv('WEATHERSTACK_API_KEY')
    url = f"http://api.weatherstack.com/current?access_key={api_key}&query={location}"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        weather_data = response.json()  # Extract JSON from Response object
        logger.debug(f"Weather data for {location}: {weather_data}")
        return weather_data
    except requests.RequestException as e:
        logger.error(f"Weather API error for {location}: {str(e)}")
        return {"error": f"Failed to fetch weather: {str(e)}"}

# Function to send automated broadcast
def send_automated_broadcast(zone, weather):
    if not weather.get('error'):
        message = "Emergency Alert: "
        risk_score = 0
        conditions = []

        if weather['current'].get('precip', 0) > 5:  # Heavy rain threshold
            risk_score += 2
            conditions.append(f"heavy rain ({weather['current'].get('precip', 0)}mm)")
        if weather['current'].get('wind_speed', 0) > 20:  # High wind threshold
            risk_score += 1
            conditions.append(f"strong winds ({weather['current'].get('wind_speed', 0)} km/h)")
        if weather['current'].get('temperature', 0) > 35:  # Extreme heat threshold
            risk_score += 1
            conditions.append(f"extreme heat ({weather['current'].get('temperature', 0)}°C)")

        if risk_score > 0:
            message += f"High risk detected in {zone.location} due to {', '.join(conditions)}. Take immediate action."
            logger.info(f"Automated broadcast sent for {zone.location}: {message}")

            # Store broadcast in history
            broadcast = BroadcastHistory(message=message, location=zone.location)
            db.session.add(broadcast)
            db.session.commit()

            recipients = [r.strip() for r in os.getenv('BROADCAST_RECIPIENT_EMAILS', '').split(',') if r.strip()]
            if not recipients:
                logger.warning("No BROADCAST_RECIPIENT_EMAILS set — skipping email for automated broadcast")
                return
            msg = Message('Automated Emergency Alert', sender=os.getenv('MAIL_USERNAME'), recipients=recipients)
            msg.body = message
            try:
                mail.send(msg)
                logger.debug(f"Email sent for automated broadcast to {recipients}")
            except Exception as e:
                logger.error(f"Failed to send email for automated broadcast: {str(e)}")
        else:
            logger.debug(f"No severe weather detected for {zone.location}")

# Scheduler for automated broadcasts
scheduler = BackgroundScheduler()
@scheduler.scheduled_job('interval', minutes=15)  # Check every 15 minutes (adjust as needed)
def check_weather_and_broadcast():
    with app.app_context():
        zones = DangerZone.query.all()
        if not zones:
            logger.warning("No danger zones found for automated broadcast check.")
            return

        for zone in zones:
            weather = get_weather(zone.location)
            send_automated_broadcast(zone, weather)

# Start the scheduler when the app starts.
# Guard against double-start: gunicorn --preload or Flask reloader can call this twice.
def start_scheduler():
    if scheduler.running:
        logger.info("Scheduler already running — skipping start.")
        return
    scheduler.add_job(decay_danger_zones, 'interval', hours=6, id='danger_zone_decay')
    scheduler.start()
    logger.info("Started automated broadcast scheduler.")

# Shut down the scheduler when the app exits
def shutdown_scheduler():
    scheduler.shutdown()
    logger.info("Shut down automated broadcast scheduler.")

# Register the scheduler startup and shutdown
with app.app_context():
    start_scheduler()
atexit.register(shutdown_scheduler)


live_cache = {
    "events": [],
    "last_updated": None
}

def refresh_live_updates():
    usgs = fetch_usgs_earthquakes()
    noaa = fetch_noaa_alerts()

    live_cache["events"] = usgs + noaa
    live_cache["last_updated"] = datetime.utcnow()

with app.app_context():
    refresh_live_updates()


@scheduler.scheduled_job("interval", minutes=10)
def scheduled_live_updates():
    refresh_live_updates()


# Routes (unchanged except for /broadcast)
@app.route('/')
def home():
    return redirect(url_for('index'))

@app.route('/index')
def index():
    return render_template('index.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        logger.debug(f"Login attempt for username: {username}")
        password = request.form.get('password')
        logger.debug(f"Attempting login for username: {username}")
        
        user = User.query.filter_by(username=username).first()
        
        if user:
            logger.debug(f"User found: {user.username}, Role: {user.role}")
            if user.check_password(password):
                logger.debug(f"Password verified for user: {user.username}")
                login_user(user, remember=True)
                logger.debug(f"User logged in: {user.username}, Role: {user.role}, Redirecting to {'authority_dashboard' if user.role == 'authority' else 'index'}")
                # Redirect based on role
                if user.role == 'authority':
                    return redirect(url_for('authority_dashboard'))
                else:
                    return redirect(url_for('index'))
            else:
                logger.debug(f"Invalid password for user: {username}")
                flash('Invalid username or password', 'danger')
                return redirect(url_for('login'))  # Redirect back to login page with flash message
        else:
            logger.debug(f"User not found: {username}")
            flash('Invalid username or password', 'danger')
            return redirect(url_for('login'))  # Redirect back to login page with flash message

    return render_template('login.html')

@app.route("/api/live_updates")
def live_updates():
    return jsonify(live_cache)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            role = request.form.get('role', 'user')

            # Create new user
            new_user = User(
                username=username,
                email=email,
                role=role
            )
            new_user.set_password(password)
            
            try:
                db.session.add(new_user)
                db.session.commit()
                flash('Registration successful! Please login.', 'success')
                return redirect(url_for('login'))
            except Exception as e:
                db.session.rollback()
                logger.error(f"Database error during registration: {str(e)}")
                flash('An error occurred during registration. Please try again.', 'danger')
                return redirect(url_for('register'))

        except Exception as e:
            logger.error(f"Registration error: {str(e)}")
            flash('An error occurred. Please try again.', 'danger')
            return redirect(url_for('register'))

    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))



@app.route('/report', methods=['GET', 'POST'])
@login_required
def report():
    if request.method == 'POST':
        description = request.form.get('description')
        location_field = request.form.get('location')
        extracted_locations = location_field.strip() if location_field and location_field.strip() else ""
        disaster_type = classify_report(description)
        image_file = request.files['image']
        
        image = None
        if image_file and image_file.filename:
            image_data = image_file.read()
            
            if os.getenv('ENABLE_IMAGE_VALIDATION', 'false').lower() in ('1', 'true', 'yes'):
                if not is_disaster_image(image_data):
                    error_message = 'The uploaded image does not appear to be a valid disaster-related photo.'
                    return render_template('report.html', image_error=error_message)
            
            image = image_data

        # Store report in database
        new_report = Report(
            description=description,
            location=location_field,
            disaster_type=disaster_type,
            extracted_locations=extracted_locations,
            image=image
        )
        db.session.add(new_report)
        db.session.commit()

        # Process danger zones using the exact coordinates captured from Places Autocomplete
        place_lat_str = request.form.get('place_lat')
        place_lng_str = request.form.get('place_lng')

        if place_lat_str and place_lng_str:
            try:
                lat = float(place_lat_str)
                lng = float(place_lng_str)
                
                existing_zone = _find_zone_by_proximity(lat, lng)
                if existing_zone:
                    existing_zone.report_count += 1
                    existing_zone.severity = 1.0                   # Refresh: active zone
                    existing_zone.last_reported_at = datetime.utcnow()
                    logger.debug(f"Refreshed existing zone '{existing_zone.location}' at ({lat},{lng})")
                else:
                    # Use the user's location_field as the label
                    label = location_field.strip() if location_field and location_field.strip() else "Reported Location"
                    new_zone = DangerZone(
                        location=label,
                        latitude=lat,
                        longitude=lng,
                        report_count=1,
                        severity=1.0,
                        last_reported_at=datetime.utcnow()
                    )
                    db.session.add(new_zone)
                    logger.debug(f"Created new zone '{label}' at ({lat},{lng})")
                
                db.session.commit()
            except ValueError:
                logger.error("Invalid coordinates received from form.")
        else:
            # Fallback: if user didn't use the autocomplete dropdown, process using fallback logic
            logger.debug("No pre-geocoded coordinates found. Falling back to server-side geocoding.")
            geocoding_queries = _build_geocoding_queries(location_field)

            for full_query in geocoding_queries:
                if not full_query.strip():
                    continue
                lat, lng = get_coordinates(full_query.strip())
                if lat and lng:
                    existing_zone = _find_zone_by_proximity(lat, lng)
                    if existing_zone:
                        existing_zone.report_count += 1
                        existing_zone.severity = 1.0
                        existing_zone.last_reported_at = datetime.utcnow()
                        logger.debug(f"Refreshed existing zone '{existing_zone.location}' at ({lat},{lng})")
                    else:
                        label = location_field.strip() if location_field and location_field.strip() else full_query.strip()
                        new_zone = DangerZone(
                            location=label,
                            latitude=lat,
                            longitude=lng,
                            report_count=1,
                            severity=1.0,
                            last_reported_at=datetime.utcnow()
                        )
                        db.session.add(new_zone)
                        logger.debug(f"Created new zone '{label}' at ({lat},{lng})")
                else:
                    logger.warning(f"Could not get coordinates for query: {full_query.strip()}")
            
            db.session.commit()


        return redirect(url_for('index'))

    return render_template('report.html')

@app.route('/danger_zones')
def danger_zones():
    zones = DangerZone.query.all()
    danger_data = [
        {
            "location": zone.location,
            "latitude": zone.latitude,
            "longitude": zone.longitude,
            "report_count": zone.report_count,
            "severity": round(zone.severity, 3) if zone.severity is not None else 1.0
        } for zone in zones
    ]
    return jsonify(danger_data)

@app.route('/map')
def map_view():
    return render_template('map.html')

# ... inside app.py ...

@app.route('/api/send_sos', methods=['POST'])
def sos():
    try:
        data = request.get_json()
        
        # 1. Extract Data
        lat = data.get('latitude')
        lng = data.get('longitude')
        timestamp = data.get('timestamp')
        
        # 2. Create Google Maps Link
        maps_link = f"https://www.google.com/maps?q={lat},{lng}"
        
        # 3. Construct Email
        user_email = current_user.email
        subject = f"🚨 SOS ALERT: {current_user.username}"
        
        body_content = (
            f"SOS SIGNAL RECEIVED!\n\n"
            f"User: {current_user.username}\n"
            f"Email: {user_email}\n"
            f"Time: {timestamp}\n\n"
            f"📍 LOCATION COORDINATES:\n"
            f"Latitude: {lat}\n"
            f"Longitude: {lng}\n\n"
            f"🔗 CLICK TO TRACK:\n{maps_link}"
        )

        # 4. Send Email
        sos_recipients = [r.strip() for r in os.getenv('SOS_RECIPIENT_EMAILS', '').split(',') if r.strip()]
        if not sos_recipients:
            logger.warning("SOS_RECIPIENT_EMAILS not configured — SOS email not sent")
            return jsonify({"status": "success", "message": "SOS recorded (email not configured)"}), 200
        msg = Message(subject, sender=os.getenv('MAIL_USERNAME'), recipients=sos_recipients)
        msg.body = body_content
        mail.send(msg)

        return jsonify({"status": "success", "message": "SOS sent successfully"}), 200

    except Exception as e:
        print(f"SOS Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
@app.route('/broadcast', methods=['GET', 'POST'])
@login_required
@require_authority  # Use custom decorator
def broadcast():
    if request.method == 'GET':
        return render_template('broadcast.html')
    elif request.method == 'POST':
        message = request.form.get('message')
        zones = DangerZone.query.all()
        for zone in zones:
            weather = get_weather(zone.location)
            if not weather.get('error'):  # Check if there's no error in the weather data
                if weather['current'].get('precip', 0) > 5:  # Example: Heavy rain threshold
                    logger.debug(f"High weather risk for {zone.location}: {weather}")
                    message += f" | High risk due to {weather['current'].get('weather_descriptions', ['unknown'])[0]}"
        flash('Broadcast message sent to danger zones')
        return redirect(url_for('authority_dashboard'))

@app.route('/safe_route')
def safe_route():
    return render_template('safe_route.html')

@app.route('/alerts')
def alerts():
    return render_template('alerts.html')

import base64

# Change <location> to <path:location> to handle addresses with slashes (e.g. "10/77")
@app.route('/images/<path:location>') 
def get_images(location):
    """Get images for a specific location"""
    # ... rest of your code is fine ...
    """Get images for a specific location"""
    logger.debug(f"Fetching images for location: {location}")
    
    # Try multiple ways to match locations
    reports = []
    
    # Method 1: Exact match in extracted_locations
    reports.extend(Report.query.filter(Report.extracted_locations.contains(location)).all())
    
    # Method 2: Location field match
    reports.extend(Report.query.filter(Report.location.contains(location)).all())
    
    # Method 3: Case-insensitive search
    reports.extend(Report.query.filter(Report.extracted_locations.ilike(f'%{location}%')).all())
    
    # Remove duplicates based on report ID
    unique_reports = {report.id: report for report in reports}.values()
    
    logger.debug(f"Found {len(unique_reports)} reports for location: {location}")
    
    images = []
    for report in unique_reports:
        if report.image:
            logger.debug(f"Processing image for report {report.id}")
            # Convert binary data to base64 for display
            image_b64 = base64.b64encode(report.image).decode('utf-8')
            images.append(image_b64)
    
    logger.debug(f"Returning {len(images)} images for location: {location}")
    return jsonify(images)

@app.route('/image/<int:report_id>')
def get_image(report_id):
    """Serve individual images with proper headers"""
    report = Report.query.get_or_404(report_id)
    if report.image:
        # Determine image type (you might want to store this in the database)
        # For now, we'll assume JPEG
        response = app.response_class(report.image, mimetype='image/jpeg')
        return response
    else:
        return "Image not found", 404

@app.route('/images_data/<location>')
def get_images_data(location):
    """Get images with metadata for the map"""
    reports = Report.query.filter(Report.extracted_locations.contains(location)).all()
    images_data = []
    for report in reports:
        if report.image:
            image_b64 = base64.b64encode(report.image).decode('utf-8')
            images_data.append({
                'id': report.id,
                'image': image_b64,
                'description': report.description,
                'disaster_type': report.disaster_type,
                'created_at': report.created_at.isoformat() if report.created_at else None
            })
    return jsonify(images_data)

@app.route('/authority_dashboard')
@login_required
@require_authority
def authority_dashboard():
    try:
        reports = Report.query.order_by(Report.created_at.desc()).all()
        zones = DangerZone.query.all()

        report_stats = {
            'Fire': Report.query.filter_by(disaster_type='Fire').count(),
            'Flood': Report.query.filter_by(disaster_type='Flood').count(),
            'Earthquake': Report.query.filter_by(disaster_type='Earthquake').count(),
            'Unknown': Report.query.filter_by(disaster_type='Unknown').count()
        }
        
        # Prepare default or computed trend data
        trend_labels = []  # Replace with actual labels if available
        trend_data = {
            'Fire': [],
            'Flood': [],
            'Earthquake': [],
            'Unknown': []
        }
        
        return render_template('authority_dashboard.html', 
                               zones=zones,
                               reports=reports,
                               stats=report_stats,
                               trend_labels=trend_labels,
                               trend_data=trend_data)
    except Exception as e:
        logger.error(f"Error in authority dashboard: {str(e)}")
        flash('Error loading dashboard data', 'danger')
        # Pass default empty values to avoid undefined variables in the template
        return render_template('authority_dashboard.html', 
                               stats={'Fire': 0, 'Flood': 0, 'Earthquake': 0, 'Unknown': 0},
                               trend_labels=[],
                               trend_data={'Fire': [], 'Flood': [], 'Earthquake': [], 'Unknown': []})


@app.route('/user_guide')
def user_guide():
    return render_template('user_guide.html')

@app.route('/debug/reports')
def debug_reports():
    """Debug route to see what reports are in the database"""
    reports = Report.query.all()
    debug_data = []
    for report in reports:
        debug_data.append({
            'id': report.id,
            'description': report.description[:100] + '...' if len(report.description) > 100 else report.description,
            'location': report.location,
            'extracted_locations': report.extracted_locations,
            'disaster_type': report.disaster_type,
            'has_image': report.image is not None,
            'image_size': len(report.image) if report.image else 0,
            'created_at': report.created_at.isoformat() if report.created_at else None
        })
    return jsonify(debug_data)

@app.route('/debug/danger_zones')
def debug_danger_zones():
    """Debug route to see what danger zones are in the database"""
    zones = DangerZone.query.all()
    debug_data = []
    for zone in zones:
        debug_data.append({
            'id': zone.id,
            'location': zone.location,
            'latitude': zone.latitude,
            'longitude': zone.longitude,
            'report_count': zone.report_count
        })
    return jsonify(debug_data)
@app.route('/resource_map')
def resource_map():
    """Page for users to view the resource map"""
    return render_template('resource_map.html')

@app.route('/manage_resource_camps')
@login_required
@require_authority
def manage_resource_camps():
    """Authority page to manage resource camps"""
    return render_template('manage_resource_camps.html')

@app.route('/api/resource_camps')
def get_resource_camps():
    """API to fetch all camps for the Google Map"""
    camps = ResourceCamp.query.all()
    return jsonify([camp.to_dict() for camp in camps])

@app.route('/add_resource_camp', methods=['POST'])
@login_required
@require_authority
def add_resource_camp():
    """Authority route to add a new camp"""
    name = request.form.get('name')
    camp_type = request.form.get('camp_type')
    location = request.form.get('location')
    contact = request.form.get('contact')

    # Geocode the address
    lat, lng = get_coordinates(location)

    if lat and lng:
        new_camp = ResourceCamp(
            name=name,
            camp_type=camp_type,
            location=location,
            latitude=lat,
            longitude=lng,
            contact_info=contact
        )
        db.session.add(new_camp)
        db.session.commit()
        
        # Return JSON for AJAX requests, or redirect for form submissions
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.accept_json:
            return jsonify({'success': True, 'message': f'{camp_type} Camp added successfully!'})
        
        flash(f'{camp_type} Camp added successfully!', 'success')
        return redirect(url_for('authority_dashboard'))
    else:
        # Return JSON error for AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.accept_json:
            return jsonify({'success': False, 'message': 'Could not find location coordinates. Please be more specific.'}), 400
        
        flash('Could not find location coordinates. Please be more specific.', 'danger')
        return redirect(url_for('authority_dashboard'))




@app.route('/delete_resource_camp/<int:camp_id>', methods=['DELETE'])
@login_required
@require_authority
def delete_resource_camp(camp_id):
    """Authority route to delete a resource camp"""
    camp = ResourceCamp.query.get_or_404(camp_id)
    try:
        db.session.delete(camp)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Camp deleted successfully!'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting camp: {str(e)}")
        return jsonify({'success': False, 'message': 'Error deleting camp.'}), 500

@app.route('/feedback', methods=['POST'])
def feedback():
    """Receive feedback and persist to the database."""
    try:
        data = request.get_json()
        category = data.get('category', 'General')
        subject  = data.get('subject', '')
        message  = data.get('message', '')
        rating_raw = data.get('rating', None)
        rating = int(rating_raw) if rating_raw not in (None, '') else None

        username = current_user.username if current_user.is_authenticated else 'Anonymous'
        email    = current_user.email    if current_user.is_authenticated else ''

        entry = Feedback(
            username=username,
            email=email,
            category=category,
            subject=subject,
            message=message,
            rating=rating,
        )
        db.session.add(entry)
        db.session.commit()

        return jsonify({'status': 'success', 'message': 'Thank you for your feedback!'}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Feedback error: {e}")
        return jsonify({'status': 'error', 'message': 'Failed to save feedback.'}), 500

if __name__ == '__main__':
    app.run(debug=True)
