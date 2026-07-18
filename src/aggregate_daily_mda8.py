'''
Aggregates raw hourly OpenAQ data (global_hourly_2019_window.csv) into
daily values structurally comparable to Xu et al.'s station data:
    - PM2.5: simple daily mean of that day's hourly readings
    - O3: MDA8 (maximum of all rolling 8-hour averages within that day),
      after converting to ug/m3 if the sensor reported in ppm/ppb
 
Also joins station coordinates back in (the raw hourly file doesn't have
them) using the original global_pm25_stations.json / global_o3_stations.json
files.
'''
 
import json
 
import numpy as np
import pandas as pd
 
HOURLY_FILE = "data/global_hourly_2019_window.csv"
PM25_STATIONS_FILE = "data/global_pm25_stations.json"
O3_STATIONS_FILE = "data/global_o3_stations.json"
OUTPUT_FILE = "data/openaq_daily_aggregated_2019_window.csv"
 
# O3 unit conversion to ug/m3, standard EPA convention at 25C / 1 atm.
# true conversion depends on each site's actual temperature/pressure,
# this is an approximation
O3_MOLAR_MASS = 48.00       # g/mol
MOLAR_VOLUME_25C = 24.45    # L/mol at 25C, 1 atm
PPB_TO_UGM3 = O3_MOLAR_MASS / MOLAR_VOLUME_25C   # ~1.963
PPM_TO_UGM3 = PPB_TO_UGM3 * 1000
 
# Require at least this many of the 8 hours present to count a rolling window,
# to avoid a "window" built from 1-2 sparse readings producing a misleading value.
MIN_HOURS_PER_8HR_WINDOW = 6
 
 
def load_coordinates(*station_files):
    coords = {}
    for path in station_files:
        with open(path, "r", encoding = "utf-8") as f:
            data = json.load(f)
        for loc in data.get("results", []):
            loc_id = loc.get("id")
            c = loc.get("coordinates") or {}
            if loc_id is not None and loc_id not in coords:
                coords[loc_id] = (c.get("latitude"), c.get("longitude"))
    return coords
 
 
def convert_o3_to_ugm3(value, unit):
    if pd.isna(value):
        return np.nan
    unit = (unit or "").strip().lower()
    if unit in ("µg/m³", "ug/m3", "ug/m³", "µg/m3"):
        return value
    if unit == "ppb":
        return value * PPB_TO_UGM3
    if unit == "ppm":
        return value * PPM_TO_UGM3
    # Unknown/unexpected unit
    return np.nan
 
 
def compute_mda8_for_day(hours_df):
    '''hours_df has columns 'hour' (0-23) and 'value_ugm3' for one station/day.
    Returns (mda8_value, hours_used) or (nan, 0) if not enough data.'''
    hour_values = hours_df.groupby("hour")["value_ugm3"].mean().to_dict()
 
    window_avgs = []
    for start in range(0, 17):  # windows: hours 0-7 through 16-23
        window_hours = range(start, start + 8)
        vals = [hour_values[h] for h in window_hours if h in hour_values]
        if len(vals) >= MIN_HOURS_PER_8HR_WINDOW:
            window_avgs.append(sum(vals) / len(vals))
 
    if not window_avgs:
        return np.nan, len(hour_values)
    return max(window_avgs), len(hour_values)
 
 
def main():
    print("Loading raw hourly data...")
    df = pd.read_csv(HOURLY_FILE, encoding = "utf-8")
    df["date"] = df["datetime_local"].astype(str).str[:10]
    df["hour"] = pd.to_numeric(df["datetime_local"].astype(str).str[11:13], errors = "coerce")
 
    print("Loading station coordinates...")
    coords = load_coordinates(PM25_STATIONS_FILE, O3_STATIONS_FILE)
 
    all_results = []
 
    # PM2.5 daily mean
    print("Aggregating PM2.5 (daily mean)...")
    pm25 = df[df["parameter"] == "pm25"].copy()
    group_cols = ["location_id", "location_name", "country", "sensor_id", "date"]
    pm25_daily = pm25.groupby(group_cols)["value"].agg(daily_value = "mean", hours_used = "count").reset_index()
    
    pm25_daily["parameter"] = "pm25"
    pm25_daily["unit"] = "µg/m³"
    all_results.append(pm25_daily)
    print(f"{len(pm25_daily)} PM2.5 station-days computed")
 
    # O3 MDA8
    print("Aggregating O3 (MDA8)...")
    o3 = df[df["parameter"] == "o3"].copy()
    o3["value_ugm3"] = [convert_o3_to_ugm3(v, u) for v, u in zip(o3["value"], o3["unit"])]
    o3 = o3.dropna(subset = ["hour", "value_ugm3"])
 
    o3_rows = []
    for keys, group in o3.groupby(group_cols):
        mda8, hours_used = compute_mda8_for_day(group[["hour", "value_ugm3"]])
        if pd.isna(mda8):
            continue
        row = dict(zip(group_cols, keys))
        row["daily_value"] = mda8
        row["hours_used"] = hours_used
        o3_rows.append(row)
 
    o3_daily = pd.DataFrame(o3_rows)
    if not o3_daily.empty:
        o3_daily["parameter"] = "o3"
        o3_daily["unit"] = "µg/m³"
    all_results.append(o3_daily)
    print(f"{len(o3_daily)} O3 station-days computed (MDA8)")
 
    # Combine coordinates and save
    final = pd.concat(all_results, ignore_index = True)
    final["latitude"] = final["location_id"].map(lambda x: coords.get(x, (None, None))[0])
    final["longitude"] = final["location_id"].map(lambda x: coords.get(x, (None, None))[1])
 
    final = final[[
        "parameter", "location_id", "location_name", "country", "latitude", "longitude",
        "sensor_id", "date", "daily_value", "unit", "hours_used",
    ]]
 
    final.to_csv(OUTPUT_FILE, index = False, encoding = "utf-8")
    print(f"\nDone. Wrote {len(final)} daily rows to {OUTPUT_FILE}")
    print(final["parameter"].value_counts())
 
 
if __name__ == "__main__":
    main()