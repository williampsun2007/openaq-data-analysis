'''
Compares completeness of the India PM2.5 daily download vs the hourly
download for Jan-Jun 2026, to quantify how much lower hourly coverage is
compared to daily coverage.
'''
 
import pandas as pd
 
DAILY_FILE = "data/india_pm25_jan_jun_2026.csv"
HOURLY_FILE = "data/india_pm25_jan_jun_2026_hourly.csv"
 
EXPECTED_DAYS = 181       # Jan 1 - Jun 30, 2026
EXPECTED_HOURS = 181 * 24
OUTPUT_DETAIL_FILE = "data/india_coverage_comparison.csv"
 
 
def main():
    daily = pd.read_csv(DAILY_FILE, encoding = "utf-8")
    hourly = pd.read_csv(HOURLY_FILE, encoding = "utf-8")
 
    # Check # of distinct days in daily file per loc.
    daily_station_days = daily.groupby("location_id")["date"].nunique()
    daily_pct_days = (daily_station_days / EXPECTED_DAYS * 100)
 
    # Check # of distinct hours and days in hourly file (days with at least one hour recorded) per loc.
    hourly = hourly.copy()
    hourly["date_only"] = hourly["datetime_local"].astype(str).str[:10]
    hourly_station_hours = hourly.groupby("location_id")["datetime_local"].nunique()
    hourly_station_days = hourly.groupby("location_id")["date_only"].nunique()
    hourly_pct_hours = (hourly_station_hours / EXPECTED_HOURS * 100)
    hourly_pct_days_covered = (hourly_station_days / EXPECTED_DAYS * 100)
 
    print("=" * 60)
    print("SUMMARY: India PM2.5, Jan-Jun 2026")
    print("=" * 60)
 
    print(f"\nDaily file: {daily['location_id'].nunique()} stations")
    print(f"avg % of expected {EXPECTED_DAYS} days filled: {daily_pct_days.mean():.1f}%")
    print(f"median % of expected days filled: {daily_pct_days.median():.1f}%")
 
    print(f"\nHourly file: {hourly['location_id'].nunique()} stations")
    print(f"avg % of expected {EXPECTED_HOURS} hours filled: {hourly_pct_hours.mean():.1f}%")
    print(f"median % of expected hours filled: {hourly_pct_hours.median():.1f}%")
    print(f"avg % of days with >=1 hourly reading: {hourly_pct_days_covered.mean():.1f}%")
 
    # Determine stations that show up in one file but not the other
    daily_ids = set(daily["location_id"].unique())
    hourly_ids = set(hourly["location_id"].unique())
 
    print(f"\nStations with daily data but no hourly data at all: {len(daily_ids - hourly_ids)}")
    print(f"Stations with hourly data but no daily data at all: {len(hourly_ids - daily_ids)}")
    print(f"Stations present in both files: {len(daily_ids & hourly_ids)}")
 
    # Per-station comparison table
    comparison = pd.DataFrame({
        "daily_pct_days_filled": daily_pct_days,
        "hourly_pct_hours_filled": hourly_pct_hours,
        "hourly_pct_days_covered": hourly_pct_days_covered,
    }).reset_index().rename(columns = {"index": "location_id"})
    
    comparison["gap_daily_minus_hourly_days"] = comparison["daily_pct_days_filled"] - comparison["hourly_pct_days_covered"]
    comparison = comparison.sort_values("gap_daily_minus_hourly_days", ascending = False)
    comparison.to_csv(OUTPUT_DETAIL_FILE, index = False)
 
    print(f"\nBiggest gaps (daily coverage far exceeds hourly coverage) - top 10 stations:")
    print(comparison.head(10).to_string(index = False)) 
 
if __name__ == "__main__":
    main()