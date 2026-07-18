'''
Downloads HOURLY PM2.5 measurements for all India monitoring stations from
the OpenAQ v3 API, for Jan-Jun 2026, and saves them to a CSV file.
 
This pulls ~24x more data than the daily version (fetch_openaq_pm25.py) and
takes roughly 1.5-2 hours to run, since each sensor's ~4,344 possible hourly
rows has to be paginated (1000 rows max per request), and requests are paced
to stay safely under OpenAQ's 2,000 requests/hour limit.
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
OUTPUT_FILE = "data/india_pm25_jan_jun_2026_hourly.csv"
 
DATETIME_FROM = "2026-01-01T00:00:00"
DATETIME_TO = "2026-07-01T00:00:00"
 
PAGE_LIMIT = 1000
 
# 2,000 requests/hour = 1 request per 1.8s. Add a small margin.
SECONDS_BETWEEN_REQUESTS = 1.85
 
FIELDNAMES = [
    "location_id", "location_name", "locality", "latitude", "longitude",
    "sensor_id", "datetime_utc", "datetime_local", "pm25_value", "pm25_avg",
    "pm25_min", "pm25_max", "pm25_median", "unit", "percent_coverage",
]
 
 
def load_pm25_sensors(path):
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
 
 
def fetch_hourly_page(sensor_id, api_key, page):
    params = urllib.parse.urlencode({
        "datetime_from": DATETIME_FROM,
        "datetime_to": DATETIME_TO,
        "limit": PAGE_LIMIT,
        "page": page,
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
 
 
def rows_from_response(data, sensor_info):
    rows = []
    for r in data.get("results", []):
        period = r.get("period") or {}
        dt_from = period.get("datetimeFrom") or {}
        summary = r.get("summary") or {}
        coverage = r.get("coverage") or {}
        parameter = r.get("parameter") or {}
 
        rows.append({
            "location_id": sensor_info["location_id"],
            "location_name": sensor_info["location_name"],
            "locality": sensor_info["locality"],
            "latitude": sensor_info["latitude"],
            "longitude": sensor_info["longitude"],
            "sensor_id": sensor_info["sensor_id"],
            "datetime_utc": dt_from.get("utc", ""),
            "datetime_local": dt_from.get("local", ""),
            "pm25_value": r.get("value"),
            "pm25_avg": summary.get("avg"),
            "pm25_min": summary.get("min"),
            "pm25_max": summary.get("max"),
            "pm25_median": summary.get("median"),
            "unit": parameter.get("units", "µg/m³"),
            "percent_coverage": coverage.get("percentCoverage"),
        })
    return rows
 
 
def main():
    load_dotenv()
    
    api_key = os.getenv("OPENAQ_API_KEY")
 
    print("Loading station list from", STATIONS_FILE)
    sensors = load_pm25_sensors(STATIONS_FILE)
    total_sensors = len(sensors)
    print(f"Found {total_sensors} PM2.5 sensors across India stations.")
 
    request_count = 0
    total_rows = 0
 
    with open(OUTPUT_FILE, "w", newline = "", encoding = "utf-8") as f:
        writer = csv.DictWriter(f, fieldnames = FIELDNAMES)
        writer.writeheader()
 
        for i, sensor_info in enumerate(sensors, start = 1):
            sensor_id = sensor_info["sensor_id"]
            page = 1
            sensor_rows = 0
 
            while True:
                try:
                    data = fetch_hourly_page(sensor_id, api_key, page)
                except Exception as e:
                    print(f"[{i}/{total_sensors}] sensor {sensor_id} "
                          f"({sensor_info['location_name']}) page {page} failed: {e}")
                    break
 
                request_count += 1
                results = data.get("results", [])
                page_rows = rows_from_response(data, sensor_info)
                writer.writerows(page_rows)
                sensor_rows += len(page_rows)
 
                time.sleep(SECONDS_BETWEEN_REQUESTS)
 
                if len(results) < PAGE_LIMIT:
                    # Last page for this sensor.
                    break
                page += 1
 
            total_rows += sensor_rows
            print(f"[{i}/{total_sensors}] {sensor_info['location_name'] or sensor_info['location_id']} "
                  f"-> {sensor_rows} hourly rows (requests so far: {request_count})")
 
            f.flush()

if __name__ == "__main__":
    main()