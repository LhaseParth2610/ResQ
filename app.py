from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import spacy
import requests
from submit_report import get_coordinates
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from flask import session
from flask_login import current_user

 



app = Flask(__name__, template_folder="templates", static_folder="static")
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:iSzwMxdBLUsLVeckIUiAQRFRUOeFnfpD@viaduct.proxy.rlwy.net:25941/railway?sslmode=disable'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configure Flask-Mail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'parthlhase49@gmail.com'
app.config['MAIL_PASSWORD'] = "ecfs othd ulqa vkxp"
mail = Mail(app)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Load NLP model
nlp = spacy.load("en_core_web_sm")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255))  # Increased length to 255


    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(255))
    disaster_type = db.Column(db.String(50))
    extracted_locations = db.Column(db.Text)

class DangerZone(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    location = db.Column(db.String(255), nullable=False)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    report_count = db.Column(db.Integer, default=1)

# Ensure tables exist
with app.app_context():
    db.create_all()

# Disaster Classification Function
def classify_report(text):
    text_lower = text.lower()
    if any(keyword in text_lower for keyword in ["fire", "burning", "flames"]):
        return "Fire"
    elif any(keyword in text_lower for keyword in ["flood", "waterlogging", "heavy rain"]):
        return "Flood"
    elif any(keyword in text_lower for keyword in ["earthquake", "tremor", "seismic"]):
        return "Earthquake"
    return "Unknown"

# Extract location entities using spaCy
def extract_entities(text):
    doc = nlp(text)
    locations = {ent.text for ent in doc.ents if ent.label_ in ("GPE", "LOC", "FAC")}
    return ", ".join(locations)


@app.route('/')
def home():
    return redirect(url_for('login'))  # ✅ Shows main page after login

@app.route('/index')
def index():
    return render_template('index.html')  # ✅ Shows main page after login

@app.route('/debug')
def debug():
    return jsonify({
        "session": dict(session),  # ✅ Convert session to dictionary for viewing
        "is_authenticated": current_user.is_authenticated  # ✅ Check if user is logged in
    })

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user, remember=True)  # ✅ Fix: Keeps user logged in
            return redirect(url_for('index'))
        
        flash('Invalid username or password', 'danger')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        if User.query.filter_by(username=username).first():
            flash('Username already taken')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('register'))
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful. Please login.')
        return redirect(url_for('login'))
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

        # Store report in database
        new_report = Report(
            description=description,
            location=location_field,
            disaster_type=disaster_type,
            extracted_locations=extracted_locations
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
    # Assuming you're receiving the location as part of the JSON body
    data = request.get_json()
    user_location = data.get('location')

    # Predefined message
    predefined_message = "SOS! Send help immediately. I am in danger at this location."

    # Retrieve the user's email and send the message
    user_email = current_user.email
    msg = Message('SOS Alert', sender="parthlhase49@gmail.com", recipients=['sohamwalimbe20@gmail.com'])
    msg.body = f'{predefined_message} \n\nUser: {current_user.username} ({user_email}) \nLocation: {user_location}'

    try:
        mail.send(msg)
        flash('SOS alert sent to authorities', 'success')  # Flash success message
        return redirect(url_for('index'))  # Redirect to homepage or wherever you want
    except Exception as e:
        flash(f"An error occurred: {str(e)}", 'danger')  # Flash error message
        return redirect(url_for('index'))  # Redirect to homepage



@app.route('/broadcast', methods=['POST'])
@login_required
def broadcast():
    message = request.form.get('message')
    zones = DangerZone.query.all()
    for zone in zones:
        # Send message to all users in danger zones (pseudo-code)
        # This would require a UserLocation model to track user locations
        pass
    flash('Broadcast message sent to danger zones')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
