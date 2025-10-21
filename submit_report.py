import requests
from flask_mail import Message
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Store API key (Replace with your actual API key)
apikey = "AIzaSyC46htxTZ4Tvpkv2Xob8oCKqZubIvsORkM"  # Using the same key from your map template

def get_coordinates(location_name):
    """Get coordinates for a location name using Google Geocoding API"""
    if not location_name or not location_name.strip():
        logger.warning("Empty location name provided")
        return None, None
    
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": location_name, "key": apikey}
    
    try:
        logger.debug(f"Fetching coordinates for: {location_name}")
        response = requests.get(url, params=params)
        response.raise_for_status()  # Raise HTTP errors
        data = response.json()
        
        if data["status"] == "OK":
            lat = data["results"][0]["geometry"]["location"]["lat"]
            lng = data["results"][0]["geometry"]["location"]["lng"]
            logger.debug(f"Found coordinates for {location_name}: ({lat}, {lng})")
            return lat, lng
        else:
            logger.warning(f"Error fetching coordinates for {location_name}: {data['status']}")
            return None, None
    except Exception as e:
        logger.error(f"API request failed for {location_name}: {e}")
        return None, None

def send_email(subject, recipient, body):
    msg = Message(subject, sender='your_email@gmail.com', recipients=[recipient])
    msg.body = body
    mail.send(msg)
