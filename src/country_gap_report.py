'''
Builds a per-country gap report comparing OpenAQ and Xu et al. station
coverage, separately for pm25 and o3. For each country, counts how many
stations are Xu-only (no OpenAQ match), OpenAQ-only (no Xu match), and
matched (co-located within 1 km), then computes the average bias
(OpenAQ minus Xu) and average correlation across all matched stations in
that country.

Outputs a CSV per pollutant, sorted by number of matched stations
(descending), with columns: country, xu_only_count, openaq_only_count,
matched_count, mean_bias, corr.
'''

import pandas as pd
import pyreadr
from babel import Locale

# All files
STATION_MATCHES = "data/station_matches.csv"
DAILY_VALUE_COMPARISON = "data/daily_value_comparison.csv"
OPENAQ_DAILY = "data/openaq_daily_aggregated_2019_window.csv"
XU_PM25_FILE = "data/PM25_data_5661_stations_cleaned_2000_2019.rds"
XU_O3_FILE = "data/O3_data_6851_stations_cleaned_2000_2019.rds"

territories = Locale('en').territories

# Read rds file
def load_rds(path):
    result = pyreadr.read_r(path)
    return result[None] if None in result else list(result.values())[0]

# Loop through species
for SPECIES in ["pm25", "o3"]:
    # Read the daily data from 2019 window
    df_openaq_daily = pd.read_csv(OPENAQ_DAILY)
    df_openaq_daily = df_openaq_daily[['location_id', 'country']].drop_duplicates()
    df_openaq_daily['country'] = df_openaq_daily['country'].map(territories)
    
    # Check for any codes that didn't map (e.g. non-standard codes like 'XK' for Kosovo)
    unmapped = df_openaq_daily[df_openaq_daily['country'].isna()]
    if not unmapped.empty:
        print("Unmapped country codes found — handle these manually:", unmapped['country'].unique())
    df_openaq_daily = df_openaq_daily.dropna(subset = ["country"])

    # Read Xu pm2.5 data
    xu_pm25_df = load_rds(XU_PM25_FILE)
    xu_pm25_df = xu_pm25_df[['station_id', 'country']].drop_duplicates()

    # Read o3 data
    xu_o3_df = load_rds(XU_O3_FILE)
    xu_o3_df = xu_o3_df[['station_id', 'country']].drop_duplicates()

    # Combine the pm25 and o3 Xu dfs
    xu_df = pd.concat([xu_pm25_df, xu_o3_df]).drop_duplicates(subset = "station_id")

    # Read station matches and only keep stations for the specified species
    df_station_matches = pd.read_csv(STATION_MATCHES)
    df_station_matches = df_station_matches[df_station_matches['parameter'] == SPECIES]

    # Read value comparisons and only keep those related to species
    df_daily_value = pd.read_csv(DAILY_VALUE_COMPARISON)
    df_daily_value = df_daily_value[df_daily_value['parameter'] == SPECIES]

    # Split between oa->xu and xu->oa
    oa_to_xu = df_station_matches[df_station_matches["direction"] == "oa_to_xu"]
    xu_to_oa = df_station_matches[df_station_matches["direction"] == "xu_to_oa"]

    # Filter out co-located stations, open aq only, and xu only
    co_located_ids = oa_to_xu[oa_to_xu["matched"]]["station_id"]
    openaq_only_ids = oa_to_xu[~oa_to_xu["matched"]]["station_id"]
    xu_only_ids = xu_to_oa[~xu_to_oa["matched"]]["xu_station_id"]

    # Merge station ids with their actual daily data
    co_located_df = co_located_ids.to_frame().merge(df_openaq_daily, left_on = "station_id", right_on = "location_id")
    openaq_only_df = openaq_only_ids.to_frame().merge(df_openaq_daily, left_on = "station_id", right_on = "location_id")
    xu_only_df = xu_only_ids.to_frame().merge(xu_df, left_on = "xu_station_id", right_on = "station_id")

    # Count the number per country for each group
    xu_only_counts = xu_only_df.groupby("country").size().reset_index(name = "xu_only_count")
    openaq_only_counts = openaq_only_df.groupby("country").size().reset_index(name = "openaq_only_count")
    co_located_counts = co_located_df.groupby("country").size().reset_index(name = "matched_count")

    # For co-located locations, calculate the mean bias
    co_located_df = co_located_df.merge(df_daily_value, left_on = "station_id", right_on = "location_id")
    co_located_df['difference'] = co_located_df['openaq_value'] - co_located_df['xu_value']
    bias_by_country = co_located_df.groupby("country")["difference"].mean().reset_index(name = "mean_bias")
    co_located_counts = co_located_counts.merge(bias_by_country, on = "country", how = "left")

    # For co-located locations, calculate the correlation for each station per country and find the mean
    station_corr = co_located_df.groupby("station_id").apply(
    lambda g: pd.Series({
        "country": g["country"].iloc[0],
        "station_corr": g["openaq_value"].corr(g["xu_value"]),
    })).reset_index()
    corr_by_country = station_corr.groupby("country")["station_corr"].mean().reset_index(name = "corr")
    co_located_counts = co_located_counts.merge(corr_by_country, on = "country", how = "left")

    # Merge together the three dfs for co-located, open aq only, and xu only. Replace any Na with 0
    report = xu_only_counts.merge(openaq_only_counts, on = "country", how = "outer").merge(co_located_counts, on = "country", how = "outer")
    report[["xu_only_count", "openaq_only_count", "matched_count"]] = report[["xu_only_count", "openaq_only_count", "matched_count"]].fillna(0)
    
    # Round bias and corr to 2 decimals
    report['mean_bias'] = round(report['mean_bias'], 2)
    report['corr'] = round(report['corr'], 2)
    
    # Sort and save
    report = report.sort_values('matched_count', ascending = False)
    report.to_csv(f"data/{SPECIES}_country_gap_report.csv", index = False)