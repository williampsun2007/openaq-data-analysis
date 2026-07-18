'''
Samples sensors from the global PM2.5 and O3 station lists and checks each
sampled sensor's /v3/sensors/{id} metadata to determine:
    - whether it reports hourly, daily, or some other interval
      (coverage.expectedInterval)
    - whether its data reaches back to around January 2000 (datetimeFirst)
 
This answers the "how many global sensors offer hourly vs daily data, and
how many go back to Jan 2000" question using a random sample instead of
checking all ~19,440 PM2.5 / ~3,679 O3 locations (which would take far too
long under the rate limit).
'''
 
import csv
import json
import random
import time
import urllib.error
import urllib.request
from dotenv import load_dotenv
import os
from collections import Counter
 
API_BASE = "https://api.openaq.org/v3"
 
SAMPLE_SIZE = 500
RANDOM_SEED = 42  # fixed seed so the sample is reproducible if re-run
 
SOURCES = [
    {"parameter_name": "pm25", "stations_file": "data/global_pm25_stations.json"},
    {"parameter_name": "o3", "stations_file": "data/global_o3_stations.json"},
]
 
SECONDS_BETWEEN_REQUESTS = 1.1
OUTPUT_DETAIL_FILE = "data/sensor_coverage_sample.csv"
 
# A sensor counts as reaching back to Jan 2000 if its first measurement is
# on or before this date.
JAN_2000_CUTOFF = "2000-02-01"
 
 
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
 
 
def fetch_sensor_detail(sensor_id, api_key):
    url = f"{API_BASE}/sensors/{sensor_id}"
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
 
 
def classify_interval(interval_str):
    '''Roughly bucket an expectedInterval string like '01:00:00' into a label.'''
    if not interval_str:
        return "unknown"
    try:
        hours = int(interval_str.split(":")[0])
    except (ValueError, IndexError):
        return "unknown"
 
    if hours <= 1:
        return "hourly"
    elif hours >= 24:
        return "daily"
    else:
        return f"other ({interval_str})"
 
 
def main():
    load_dotenv()
    
    api_key = os.getenv("OPENAQ_API_KEY")
 
    random.seed(RANDOM_SEED)
 
    all_samples = []
    for source in SOURCES:
        sensors = load_sensors_for_parameter(source["stations_file"], source["parameter_name"])
        sample_n = min(SAMPLE_SIZE, len(sensors))
        sample = random.sample(sensors, sample_n)
        print(f"{source['parameter_name']}: {len(sensors)} total sensors found, "
              f"sampling {sample_n}")
        all_samples.extend(sample)
 
    total = len(all_samples)
    print(f"\nChecking {total} sampled sensors via /v3/sensors/{{id}} ...\n")
 
    interval_counts = Counter()      # (parameter_name, interval_label) -> count
    jan2000_counts = Counter()       # parameter_name -> count with data back to Jan 2000
    checked_counts = Counter()       # parameter_name -> total successfully checked
 
    rows = []
 
    for i, s in enumerate(all_samples, start = 1):
        try:
            data = fetch_sensor_detail(s["sensor_id"], api_key)
        except Exception as e:
            print(f"[{i}/{total}] sensor {s['sensor_id']} ({s['parameter_name']}) failed: {e}")
            continue
 
        results = data.get("results", [])
        if not results:
            print(f"[{i}/{total}] sensor {s['sensor_id']} ({s['parameter_name']}) -> no data")
            continue
 
        detail = results[0]
        coverage = detail.get("coverage") or {}
        expected_interval = coverage.get("expectedInterval", "")
        interval_label = classify_interval(expected_interval)
 
        datetime_first = detail.get("datetimeFirst") or {}
        first_local = datetime_first.get("local", "")
        reaches_jan2000 = bool(first_local) and first_local[:10] <= JAN_2000_CUTOFF
 
        param_name = s["parameter_name"]
        checked_counts[param_name] += 1
        interval_counts[(param_name, interval_label)] += 1
        if reaches_jan2000:
            jan2000_counts[param_name] += 1
 
        rows.append({
            "parameter": param_name,
            "location_id": s["location_id"],
            "location_name": s["location_name"],
            "country": s["country"],
            "sensor_id": s["sensor_id"],
            "expected_interval": expected_interval,
            "interval_label": interval_label,
            "datetime_first_local": first_local,
            "reaches_jan_2000": reaches_jan2000,
        })
 
        print(f"[{i}/{total}] {param_name} sensor {s['sensor_id']} "
              f"({s['location_name']}) -> {interval_label}, "
              f"first data: {first_local[:10] if first_local else 'unknown'}")
 
        time.sleep(SECONDS_BETWEEN_REQUESTS)
 
    # Write per-sensor detail CSV
    fieldnames = [
        "parameter", "location_id", "location_name", "country", "sensor_id",
        "expected_interval", "interval_label", "datetime_first_local", "reaches_jan_2000",
    ]
    with open(OUTPUT_DETAIL_FILE, "w", newline = "", encoding = "utf-8") as f:
        writer = csv.DictWriter(f, fieldnames = fieldnames)
        writer.writeheader()
        writer.writerows(rows)
 
    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for param_name in ["pm25", "o3"]:
        checked = checked_counts[param_name]
        if checked == 0:
            print(f"\n{param_name}: no sensors successfully checked")
            continue
 
        print(f"\n{param_name}: {checked} sensors successfully checked")
        for (p, label), count in sorted(interval_counts.items()):
            if p == param_name:
                pct = 100 * count / checked
                print(f"{label}: {count} ({pct:.1f}%)")
 
        jan2000 = jan2000_counts[param_name]
        pct_jan2000 = 100 * jan2000 / checked
        print(f"reaches back to Jan 2000: {jan2000} ({pct_jan2000:.1f}%)")
 
if __name__ == "__main__":
    main()