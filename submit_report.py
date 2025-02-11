import requests
from flask_mail import Message

# Store API key (Replace with your actual API key)
apikey = "AIzaSyC46htxTZ4Tvpkv2Xob8oCKqZubIvsORkM"

def get_coordinates(location_name):
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": location_name, "key": apikey}
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()  # Raise HTTP errors
        data = response.json()
        
        if data["status"] == "OK":
            lat = data["results"][0]["geometry"]["location"]["lat"]
            lng = data["results"][0]["geometry"]["location"]["lng"]
            return lat, lng
        else:
            print(f"Error fetching coordinates for {location_name}: {data['status']}")
            return None, None
    except Exception as e:
        print(f"API request failed: {e}")
        return None, None

def send_email(subject, recipient, body):
    msg = Message(subject, sender='your_email@gmail.com', recipients=[recipient])
    msg.body = body
    mail.send(msg)