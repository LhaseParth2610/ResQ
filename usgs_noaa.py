# ---------------- USGS ----------------

USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson"

def fetch_usgs_earthquakes():
    events = []

    try:
        data = requests.get(USGS_URL, timeout=10).json()

        for feature in data.get("features", []):
            mag = feature["properties"]["mag"]
            if mag is None or mag < 2.5:
                continue

            lon, lat, depth = feature["geometry"]["coordinates"]
            time_ms = feature["properties"]["time"]

            events.append({
                "source": "USGS",
                "type": "earthquake",
                "title": feature["properties"]["title"],
                "severity": min(int(mag), 5),
                "latitude": lat,
                "longitude": lon,
                "time": datetime.utcfromtimestamp(time_ms / 1000).isoformat(),
                "details": f"Magnitude {mag}"
            })

    except Exception as e:
        print("USGS error:", e)

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

            events.append({
                "source": "NOAA",
                "type": "weather",
                "title": props.get("headline", "Weather Alert"),
                "severity": severity_map.get(props.get("severity", "Unknown"), 1),
                "latitude": lat,
                "longitude": lon,
                "time": props.get("sent"),
                "details": props.get("description", "")
            })

    except Exception as e:
        print("NOAA error:", e)

    return events