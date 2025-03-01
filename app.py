from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import spacy
import requests
from submit_report import get_coordinates
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from flask import session
from flask_migrate import Migrate
from functools import wraps  # Added for the require_authority decorator
import logging
from collections import defaultdict
from datetime import datetime
import time
import atexit
from apscheduler.schedulers.background import BackgroundScheduler
import os
from cnn_model.utils import classify_image
from dotenv import load_dotenv
import os

# Load environment variables at the top of app.py



# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = "Your_database_uri"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configure Flask-Mail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'parthlhase49@gmail.com'
app.config['MAIL_PASSWORD'] = "MAIL_PASS"

mail = Mail(app)

# Add Flask-Caching for weather API (optional, for performance)
from flask_caching import Cache
cache = Cache(config={'CACHE_TYPE': 'simple'})
cache.init_app(app)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
migrate = Migrate(app, db)

# Load NLP model
nlp = spacy.load("en_core_web_trf")

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

# Database Models (unchanged)
class User(UserMixin, db.Model):
    __tablename__ = 'user'  # Keep your existing table name
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, server_default='user')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(255))
    disaster_type = db.Column(db.String(50))
    extracted_locations = db.Column(db.Text)
    image = db.Column(db.LargeBinary, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)  # Timestamp added

class DangerZone(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    location = db.Column(db.String(255), nullable=False)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    report_count = db.Column(db.Integer, default=1)

class BroadcastHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)

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

# Extract location entities using spaCy (unchanged)
def extract_entities(text):
    doc = nlp(text)
    locations = {ent.text for ent in doc.ents if ent.label_ in ("GPE", "LOC", "FAC")}
    return ", ".join(locations)

# Weather API helper function
@cache.cached(timeout=1800)  # Cache for 30 minutes
def get_weather(location):
    api_key = 'yOUR_API'  # Replace with your Weatherstack API key (stored securely, e.g., in .env)
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

            # Simulate sending to communities (replace with actual implementation, e.g., email/SMS)
            recipients = ['prajwalkumbhar2909@gmail.com']  # Example recipient; adjust as needed
            msg = Message('Automated Emergency Alert', sender="parthlhase49@gmail.com", recipients=recipients)
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
    zones = DangerZone.query.all()
    if not zones:
        logger.warning("No danger zones found for automated broadcast check.")
        return

    for zone in zones:
        weather = get_weather(zone.location)
        send_automated_broadcast(zone, weather)

# Start the scheduler when the app starts
def start_scheduler():
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

def fetch_gdacs_events():
    """
    Fetch and parse the GDACS RSS feed.
    Returns a list of disaster events (filtered for India).
    """
    gdacs_url = "https://www.gdacs.org/xml/rss.xml"
    try:
        response = requests.get(gdacs_url)
        if response.status_code != 200:
            print("Error fetching GDACS feed:", response.status_code)
            return []
        xml_content = response.content
        root = ET.fromstring(xml_content)
        channel = root.find('channel')
        items = channel.findall('item')
        events = []
        # Define georss namespace
        namespace = {'georss': 'http://www.georss.org/georss'}
        for item in items:
            title = item.find('title').text if item.find('title') is not None else ""
            description = item.find('description').text if item.find('description') is not None else ""
            pubDate = item.find('pubDate').text if item.find('pubDate') is not None else ""
            geo_point = item.find('georss:point', namespace)
            if geo_point is not None:
                coords = geo_point.text.split()
                if len(coords) == 2:
                    try:
                        lat, lon = float(coords[0]), float(coords[1])
                    except Exception:
                        continue
                    # Filter for events in India (approx lat: 6-37, lon: 68-98)
                    if 6.0 <= lat <= 37.0 and 68.0 <= lon <= 98.0:
                        events.append({
                            'title': title,
                            'description': description,
                            'pubDate': pubDate,
                            'latitude': lat,
                            'longitude': lon
                        })
        return events
    except Exception as e:
        print("Error in fetch_gdacs_events:", e)
        return []
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
        extracted_locations = extract_entities(description)
        disaster_type = classify_report(description)
        image_file = request.files['image']
        
        if image_file:
            image_path = f'static/uploads/{image_file.filename}'
            image_file.save(image_path)
            classification = classify_image(image_path)
            
            if classification == 'not disaster':
                flash('The uploaded image is not related to a disaster.', 'danger')
                os.remove(image_path)
                return redirect(url_for('index'))
            
            with open(image_path, 'rb') as img_file:
                image = img_file.read()
        else:
            image = None

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

        # Process danger zones
        if extracted_locations:
            locations_list = extracted_locations.split(", ")
            for loc in locations_list:
                lat, lng = get_coordinates(loc)
                if lat and lng:
                    existing_zone = DangerZone.query.filter_by(location=loc).first()
                    if existing_zone:
                        existing_zone.report_count += 1  # Increase count
                    else:
                        new_zone = DangerZone(location=loc, latitude=lat, longitude=lng, report_count=1)
                        db.session.add(new_zone)
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
            "report_count": zone.report_count
        } for zone in zones
    ]
    return jsonify(danger_data)

@app.route('/map')
def map_view():
    return render_template('map.html')

@app.route('/sos', methods=['POST'])
@login_required
def sos():
    data = request.get_json()
    user_location = data.get('location')

    predefined_message = "SOS! Send help immediately. I am in danger at this location."

    user_email = current_user.email
    msg = Message('SOS Alert', sender="parthlhase49@gmail.com", recipients=['prajwalkumbhar2909@gmail.com'])
    msg.body = f'{predefined_message} \n\nUser: {current_user.username} ({user_email}) \nLocation: {user_location}'

    try:
        mail.send(msg)
        flash('SOS alert sent to authorities', 'success')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f"An error occurred: {str(e)}", 'danger')
        return redirect(url_for('index'))

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

import base64

@app.route('/images/<location>')
def get_images(location):
    reports = Report.query.filter(Report.extracted_locations.contains(location)).all()
    images = [base64.b64encode(report.image).decode('utf-8') for report in reports if report.image]
    return jsonify(images)

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

@app.route('/gdacs_events')
def gdacs_events():
    """
    Expose GDACS events as JSON.
    """
    events = fetch_gdacs_events()
    return jsonify(events)
@app.route('/user_guide')
def user_guide():
    return render_template('user_guide.html')

if __name__ == '__main__':
    app.run(debug=True)
