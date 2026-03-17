import requests
from flask_mail import Message
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Store API key (Replace with your actual API key)
apikey = "INSERT YOUR API KEY HERE"  # Using the same key from your map template

def get_coordinates(location_name, city_hint=None):
    """Get coordinates for a location name using Google Geocoding API.

    Args:
        location_name: Full address/place string to geocode (already enriched).
        city_hint: Optional city name (e.g. "Pune") used as a locality filter
                   to disambiguate common names like "Anandnagar".
    """
    if not location_name or not location_name.strip():
        logger.warning("Empty location name provided")
        return None, None

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": location_name,
        "key": apikey,
        "region": "in",            # Bias results toward India
        "language": "en",
        "components": "country:IN" # Hard-filter to India only
    }

    # If we know the city, add a locality filter for precise disambiguation
    # e.g. "Anandnagar" + city_hint="Pune" → resolves to the Pune Anandnagar
    if city_hint and city_hint.strip():
        params["components"] += f"|locality:{city_hint.strip()}"

    try:
        logger.debug(f"Fetching coordinates for: {location_name} (city_hint={city_hint})")
        response = requests.get(url, params=params)
        response.raise_for_status()
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
