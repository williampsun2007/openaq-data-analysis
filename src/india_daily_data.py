'''
Downloads daily PM2.5 measurements for all India monitoring stations from
the OpenAQ v3 API, for a given date range, and saves them to a CSV file.
'''
 
import csv
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import os
from dotenv import load_dotenv
 
API_BASE = "https://api.openaq.org/v3"
STATIONS_FILE = "data/india_stations.json"
OUTPUT_FILE = "data/india_pm25_jun_2026.csv"
 
# Date range: Jan 1, 2026 through end of June 2026.
# date_to is exclusive-ish in practice, so we use July 1 to make sure June 30 is included.
DATE_FROM = "2026-07-01"
DATE_TO = "2026-07-08"
 
# Stay comfortably under the free-tier limit of 60 requests/minute.
SECONDS_BETWEEN_REQUESTS = 1.1
 
 
def load_pm25_sensors(path):
    '''Read india_stations.json and pull out one entry per PM2.5 sensor.'''
    with open(path, "r", encoding = "utf-8") as f:
        data = json.load(f)
 
    sensors = []
    for loc in data.get("results", []):
        loc_id = loc.get("id")
        loc_name = loc.get("name") or ""
        locality = loc.get("locality") or ""
        coords = loc.get("coordinates") or {}
        for sensor in loc.get("sensors", []):
            parameter = sensor.get("parameter") or {}
            if parameter.get("name") == "pm25":
                sensors.append({
                    "location_id": loc_id,
                    "location_name": loc_name,
                    "locality": locality,
                    "latitude": coords.get("latitude"),
                    "longitude": coords.get("longitude"),
                    "sensor_id": sensor.get("id"),
                })
    return sensors
 
 
def fetch_daily_measurements(sensor_id, api_key):
    """Call /v3/sensors/{sensor_id}/days for the configured date range."""
    params = urllib.parse.urlencode({
        "date_from": DATE_FROM,
        "date_to": DATE_TO,
        "limit": 1000,
        "page": 1,
    })
    url = f"{API_BASE}/sensors/{sensor_id}/days?{params}"
    req = urllib.request.Request(url, headers = {"X-API-Key": api_key})
 
    try:
        with urllib.request.urlopen(req, timeout = 30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("Rate limited - waiting 60s before retrying...")
            time.sleep(60)
            with urllib.request.urlopen(req, timeout = 30) as resp:
                return json.load(resp)
        raise
 
 
def main():
    load_dotenv()
    
    api_key = os.getenv("OPENAQ_API_KEY")
 
    print("Loading station list from", STATIONS_FILE, "...")
    sensors = load_pm25_sensors(STATIONS_FILE)
    print(f"Found {len(sensors)} PM2.5 sensors across India stations.\n")
 
    rows = []
    total = len(sensors)
 
    for i, s in enumerate(sensors, start=1):
        try:
            data = fetch_daily_measurements(s["sensor_id"], api_key)
        except urllib.error.HTTPError as e:
            print(f"[{i}/{total}] sensor {s['sensor_id']} ({s['location_name']}) "
                  f"failed: HTTP {e.code}")
            time.sleep(SECONDS_BETWEEN_REQUESTS)
            continue
        except Exception as e:
            print(f"[{i}/{total}] sensor {s['sensor_id']} ({s['location_name']}) "
                  f"failed: {e}")
            time.sleep(SECONDS_BETWEEN_REQUESTS)
            continue
 
        results = data.get("results", [])
        for r in results:
            period = r.get("period") or {}
            dt_from = (period.get("datetimeFrom") or {}).get("local", "")
            date_str = dt_from[:10] if dt_from else ""
            summary = r.get("summary") or {}
            coverage = r.get("coverage") or {}
            parameter = r.get("parameter") or {}
 
            rows.append({
                "location_id": s["location_id"],
                "location_name": s["location_name"],
                "locality": s["locality"],
                "latitude": s["latitude"],
                "longitude": s["longitude"],
                "sensor_id": s["sensor_id"],
                "date": date_str,
                "pm25_value": r.get("value"),
                "pm25_avg": summary.get("avg"),
                "pm25_min": summary.get("min"),
                "pm25_max": summary.get("max"),
                "pm25_median": summary.get("median"),
                "unit": parameter.get("units", ""),
                "percent_coverage": coverage.get("percentCoverage"),
            })
 
        print(f"[{i}/{total}] {s['location_name'] or s['location_id']} -> {len(results)} days")
        time.sleep(SECONDS_BETWEEN_REQUESTS)
 
    fieldnames = [
        "location_id", "location_name", "locality", "latitude", "longitude",
        "sensor_id", "date", "pm25_value", "pm25_avg", "pm25_min", "pm25_max",
        "pm25_median", "unit", "percent_coverage",
    ]
    
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows) 
 
if __name__ == "__main__":
    main()