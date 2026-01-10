# ---------------- USGS ----------------

import requests
from datetime import datetime
import re

def classify_alert(title, details, source):
    """Classify an alert into a disaster category using keyword matching.
    
    Categories: earthquake, flood, tornado, wildfire, severe_storm, other
    """
    text = (title + " " + (details or "")).lower()
    
    # USGS source is always earthquakes
    if source == "USGS":
        return "earthquake"
    
    # Priority-based classification for NOAA alerts
    if "tornado" in text:
        return "tornado"
    if "flood" in text:
        return "flood"
    if "fire" in text or "wildfire" in text or "red flag" in text:
        return "wildfire"
    if "thunderstorm" in text or "storm" in text:
        return "severe_storm"
    
    return "other"

USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson"

def fetch_usgs_earthquakes(min_mag=0, timeout=10):
    events = []
    try:
        resp = requests.get(USGS_URL, timeout=timeout, headers={"User-Agent": "ResQ/1.0"})
        resp.raise_for_status()  # raises HTTPError for non-2xx

        ctype = resp.headers.get("Content-Type", "")
        if "application/json" not in ctype:
            # debug info
            print("Unexpected content-type:", ctype)
            print("Response text (truncated):", resp.text[:500])
            return events

        data = resp.json()
        features = data.get("features", [])
        print(f"DEBUG: fetched {len(features)} features")  # helpful while testing

        for feature in features:
            props = feature.get("properties", {})
            mag = props.get("mag")
            if mag is None or mag < min_mag:
                continue

            geom = feature.get("geometry") or {}
            coords = geom.get("coordinates") or [None, None, None]
            lon, lat, depth = coords

            time_ms = props.get("time")
            if time_ms is None:
                continue

            title = props.get("title", "")
            details = f"Magnitude {mag}"
            
            events.append({
                "id": feature.get("id"),
                "source": "USGS",
                "type": "earthquake",
                "category": classify_alert(title, details, "USGS"),
                "title": title,
                "severity": min(int(mag), 5),
                "latitude": lat,
                "longitude": lon,
                "depth_km": depth,
                "time": datetime.utcfromtimestamp(time_ms / 1000).isoformat() + "Z",
                "updated": datetime.utcfromtimestamp(props.get("updated", time_ms) / 1000).isoformat() + "Z",
                "details": details
            })

    except requests.exceptions.RequestException as req_e:
        print("Network/HTTP error fetching USGS feed:", req_e)
    except ValueError as json_e:
        print("JSON decode error:", json_e)
    except Exception as e:
        # When debugging, print full exception
        import traceback
        traceback.print_exc()
        print("Unexpected error:", e)

    return events


# ---------------- NOAA ----------------

NOAA_URL = "https://api.weather.gov/alerts/active"

def fetch_noaa_alerts():
    events = []

    try:
        data = requests.get(NOAA_URL, timeout=10).json()

        for alert in data.get("features", []):
            props = alert["properties"]
            severity_map = {
                "Extreme": 5,
                "Severe": 4,
                "Moderate": 3,
                "Minor": 2,
                "Unknown": 1
            }

            coords = alert["geometry"]
            if not coords:
                continue

            # Use first coordinate as reference
            lon, lat = coords["coordinates"][0][0]

            title = props.get("headline", "Weather Alert")
            details = props.get("description", "")
            
            events.append({
                "source": "NOAA",
                "type": "weather",
                "category": classify_alert(title, details, "NOAA"),
                "title": title,
                "severity": severity_map.get(props.get("severity", "Unknown"), 1),
                "latitude": lat,
                "longitude": lon,
                "time": props.get("sent"),
                "details": details
            })

    except Exception as e:
        print("NOAA error:", e)

    return events