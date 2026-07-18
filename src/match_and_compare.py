'''
Matches OpenAQ stations to Xu et al.'s compiled station data by coordinates
(nearest neighbor within a distance threshold), then compares the two for
site coverage and daily-value consistency.
'''
 
import numpy as np
import pandas as pd
import pyreadr
 
OPENAQ_FILE = "data/openaq_daily_aggregated_2019_window.csv"
XU_PM25_FILE = "data/PM25_data_5661_stations_cleaned_2000_2019.rds"
XU_O3_FILE = "data/O3_data_6851_stations_cleaned_2000_2019.rds"
 
# Matches the actual date range covered by the 984-hour OpenAQ download
# (2019-01-01T00:00 through 2019-02-11T00:00, so the last full day is Feb 10).
DATE_START = "2019-01-01"
DATE_END = "2019-02-10"
 
MATCH_THRESHOLD_KM = 1.0
 
OUTPUT_MATCHES_FILE = "data/station_matches.csv"
OUTPUT_COMPARISON_FILE = "data/daily_value_comparison.csv"
 
 
def load_rds(path):
    result = pyreadr.read_r(path)
    df = result[None] if None in result else list(result.values())[0]
    # Normalize date to plain "YYYY-MM-DD" text so it merges cleanly against
    # OpenAQ's string-based date column, regardless of how pyreadr typed it.
    df["date"] = df["date"].astype(str).str[:10]
    return df
 
 
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arcsin(np.sqrt(a))
 
 
def nearest_match(source, source_id_col, source_lat_col, source_lon_col,
                   targets, target_id_col, target_lat_col, target_lon_col,
                   threshold_km):
    """For each row in `source`, find the nearest row in `targets` and report
    whether it's within threshold_km. Returns one row per source station."""
    s_lat = source[source_lat_col].to_numpy()[:, None]
    s_lon = source[source_lon_col].to_numpy()[:, None]
    t_lat = targets[target_lat_col].to_numpy()[None, :]
    t_lon = targets[target_lon_col].to_numpy()[None, :]
 
    dist_matrix = haversine_km(s_lat, s_lon, t_lat, t_lon)  # shape (n_source, n_targets)
    nearest_idx = np.argmin(dist_matrix, axis = 1)
    nearest_dist = dist_matrix[np.arange(len(source)), nearest_idx]
 
    result = source[[source_id_col]].copy().reset_index(drop = True)
    result["nearest_target_id"] = targets[target_id_col].to_numpy()[nearest_idx]
    result["distance_km"] = nearest_dist
    result["matched"] = result["distance_km"] <= threshold_km
    return result
 
 
def main():
    print("Loading OpenAQ aggregated data...")
    openaq = pd.read_csv(OPENAQ_FILE, encoding = "utf-8")
    openaq = openaq.dropna(subset = ["latitude", "longitude"])
 
    print("Loading Xu et al. station data...")
    xu_pm25 = load_rds(XU_PM25_FILE)
    xu_o3 = load_rds(XU_O3_FILE)
 
    xu_pm25 = xu_pm25[(xu_pm25["date"] >= DATE_START) & (xu_pm25["date"] <= DATE_END)].copy()
    xu_o3 = xu_o3[(xu_o3["date"] >= DATE_START) & (xu_o3["date"] <= DATE_END)].copy()
 
    all_matches = []
    all_comparisons = []
 
    for param, xu_df, value_col in [("pm25", xu_pm25, "PM25_ug_m3"), ("o3", xu_o3, "O3_max8h_av_ug_m3")]:
        print(f"Param: {param}")
 
        oa_param = openaq[openaq["parameter"] == param]
        oa_stations = oa_param[
            ["location_id", "location_name", "country", "latitude", "longitude"]
        ].drop_duplicates(subset = ["location_id"]).reset_index(drop = True)
 
        xu_stations = xu_df[["station_id", "country", "lat", "lon"]].drop_duplicates(
            subset = ["station_id"]).reset_index(drop = True)
 
        print(f"OpenAQ stations (with data in window): {len(oa_stations)}")
        print(f"Xu stations (with data in window): {len(xu_stations)}")
 
        # Direction 1: For each OpenAQ station, find nearest Xu station
        oa_to_xu = nearest_match(
            oa_stations, "location_id", "latitude", "longitude",
            xu_stations, "station_id", "lat", "lon",
            MATCH_THRESHOLD_KM,
        )
        oa_matched = oa_to_xu["matched"].sum()
        print(f"OpenAQ stations with a Xu match within {MATCH_THRESHOLD_KM} km: "
              f"{oa_matched} / {len(oa_to_xu)} ({100 * oa_matched / len(oa_to_xu):.1f}%)")
 
        # Direction 2: For each Xu station, find nearest OpenAQ station
        xu_to_oa = nearest_match(
            xu_stations, "station_id", "lat", "lon",
            oa_stations, "location_id", "latitude", "longitude",
            MATCH_THRESHOLD_KM,
        )
        xu_matched = xu_to_oa["matched"].sum()
        print(f"Xu stations with an OpenAQ match within {MATCH_THRESHOLD_KM} km: "
              f"{xu_matched} / {len(xu_to_oa)} ({100 * xu_matched / len(xu_to_oa):.1f}%)")
 
        oa_to_xu["parameter"] = param
        oa_to_xu = oa_to_xu.rename(columns = {"location_id": "station_id", "nearest_target_id": "xu_station_id"})
        all_matches.append(oa_to_xu)
 
        # Join matched pairs daily values
        matched_pairs = oa_to_xu[oa_to_xu["matched"]][["station_id", "xu_station_id"]].rename(
            columns = {"station_id": "location_id"})
 
        oa_daily = oa_param[["location_id", "date", "daily_value"]].rename(
            columns = {"daily_value": "openaq_value"})
        xu_daily = xu_df[["station_id", "date", value_col]].rename(
            columns = {"station_id": "xu_station_id", value_col: "xu_value"})
 
        comparison = matched_pairs.merge(oa_daily, on = "location_id", how = "inner")
        comparison = comparison.merge(xu_daily, on = ["xu_station_id", "date"], how = "inner")
        comparison["parameter"] = param
        comparison["abs_diff"] = (comparison["openaq_value"] - comparison["xu_value"]).abs()
        all_comparisons.append(comparison)
 
        if len(comparison) > 0:
            corr = comparison["openaq_value"].corr(comparison["xu_value"])
            print(f"Matched station-days with values on both sides: {len(comparison)}")
            print(f"Correlation (OpenAQ vs Xu): {corr:.3f}")
            print(f"Mean absolute difference: {comparison['abs_diff'].mean():.2f}")
            print(f"Median absolute difference: {comparison['abs_diff'].median():.2f}")
        else:
            print("No overlapping station-days with values on both sides.")
 
    pd.concat(all_matches, ignore_index = True).to_csv(OUTPUT_MATCHES_FILE, index = False)
    pd.concat(all_comparisons, ignore_index = True).to_csv(OUTPUT_COMPARISON_FILE, index = False)
 
if __name__ == "__main__":
    main()