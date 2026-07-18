'''
For the ~1000 hour time period from January 1 to February 10 of 2019, get all hourly data across global PM2.5 and O3 sensors
'''
 
import csv
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dotenv import load_dotenv
 
API_BASE = "https://api.openaq.org/v3"
 
DATETIME_FROM = "2019-01-01T00:00:00"
DATETIME_TO = "2019-02-11T00:00:00"
 
SOURCES = [
    {"parameter_name": "pm25", "stations_file": "data/global_pm25_stations.json"},
    {"parameter_name": "o3", "stations_file": "data/global_o3_stations.json"},
]
 
PAGE_LIMIT = 1000
SECONDS_BETWEEN_REQUESTS = 1.85
PROGRESS_EVERY = 50
 
OUTPUT_FILE = "data/global_hourly_2019_window.csv"
FIELDNAMES = [
    "parameter", "location_id", "location_name", "country", "sensor_id",
    "datetime_utc", "datetime_local", "value", "unit",
]
 
 
def load_sensors_for_parameter(stations_file, parameter_name):
    with open(stations_file, "r", encoding = "utf-8") as f:
        data = json.load(f)
 
    sensors = []
    for loc in data.get("results", []):
        loc_id = loc.get("id")
        loc_name = loc.get("name") or ""
        country = (loc.get("country") or {}).get("code", "")
        for sensor in loc.get("sensors", []):
            parameter = sensor.get("parameter") or {}
            if parameter.get("name") == parameter_name:
                sensors.append({
                    "location_id": loc_id,
                    "location_name": loc_name,
                    "country": country,
                    "sensor_id": sensor.get("id"),
                    "parameter_name": parameter_name,
                })
    return sensors
 
 
def get_already_done_sensor_ids(output_file):
    '''Read the existing partial CSV (if any) and return the set of sensor_ids
    that already have at least one row written for them.'''
    done = set()
    if not os.path.exists(output_file):
        return done
 
    with open(output_file, "r", encoding = "utf-8", newline = "") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = row.get("sensor_id")
            if sid:
                done.add(sid)
    return done
 
 
def fetch_hourly_window(sensor_id, api_key):
    params = urllib.parse.urlencode({
        "datetime_from": DATETIME_FROM,
        "datetime_to": DATETIME_TO,
        "limit": PAGE_LIMIT,
        "page": 1,
    })
    url = f"{API_BASE}/sensors/{sensor_id}/hours?{params}"
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
 
    all_sensors = []
    for source in SOURCES:
        sensors = load_sensors_for_parameter(source["stations_file"], source["parameter_name"])
        print(f"{source['parameter_name']}: {len(sensors)} sensors loaded")
        all_sensors.extend(sensors)
 
    already_done = get_already_done_sensor_ids(OUTPUT_FILE)
    print(f"\nFound {len(already_done)} sensors already completed in {OUTPUT_FILE}")
 
    remaining = [s for s in all_sensors if str(s["sensor_id"]) not in already_done]
    total = len(remaining)
    est_hours = total * SECONDS_BETWEEN_REQUESTS / 3600
    print(f"Remaining sensors to fetch: {total}")
    print(f"Estimated remaining runtime: ~{est_hours:.1f} hours\n")
    
    if total == 0:
        print("All sensors already recorded")
        return
 
    file_exists = os.path.exists(OUTPUT_FILE)
    total_rows = 0
    failures = 0
 
    # Append mode: keeps existing data, only write header if file is brand new.
    with open(OUTPUT_FILE, "a", newline = "", encoding = "utf-8") as f:
        writer = csv.DictWriter(f, fieldnames = FIELDNAMES)
        if not file_exists or os.path.getsize(OUTPUT_FILE) == 0:
            writer.writeheader()
 
        for i, s in enumerate(remaining, start = 1):
            try:
                data = fetch_hourly_window(s["sensor_id"], api_key)
            except Exception as e:
                failures += 1
                print(f"[{i}/{total}] sensor {s['sensor_id']} ({s['parameter_name']}) failed: {e}")
                time.sleep(SECONDS_BETWEEN_REQUESTS)
                continue
 
            rows = []
            for r in data.get("results", []):
                period = r.get("period") or {}
                dt_from = period.get("datetimeFrom") or {}
                parameter = r.get("parameter") or {}
 
                rows.append({
                    "parameter": s["parameter_name"],
                    "location_id": s["location_id"],
                    "location_name": s["location_name"],
                    "country": s["country"],
                    "sensor_id": s["sensor_id"],
                    "datetime_utc": dt_from.get("utc", ""),
                    "datetime_local": dt_from.get("local", ""),
                    "value": r.get("value"),
                    "unit": parameter.get("units", ""),
                })
 
            writer.writerows(rows)
            total_rows += len(rows)
 
            if i % PROGRESS_EVERY == 0 or i == total:
                print(f"[{i}/{total}] sensors processed this run, {total_rows} rows written, "
                      f"{failures} failures")
                f.flush()
 
            time.sleep(SECONDS_BETWEEN_REQUESTS)
 
if __name__ == "__main__":
    main()