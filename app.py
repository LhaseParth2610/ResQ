from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
import spacy
import requests
from submit_report import get_coordinates

app = Flask(__name__, template_folder="templates", static_folder="static")

# Configure PostgreSQL Database
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:admin@localhost/disaster_reports'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Load NLP model
nlp = spacy.load("en_core_web_sm")

# Database Models
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
def index():
    return render_template('index.html')

@app.route('/report', methods=['GET', 'POST'])
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

if __name__ == '__main__':
    app.run(debug=True)