'''
Builds a per-country gap report comparing OpenAQ, Xu et al., and GHOST station
coverage, separately for pm25 and o3. For each country, counts how many
stations are Xu-only (no OpenAQ match), OpenAQ-only (no Xu match), matched (co-located within 1 km), 
and GHOST only, then computes the average bias (OpenAQ minus Xu) and average correlation across all 
matched stations in that country.

Outputs a CSV per pollutant, sorted by number of matched stations
(descending), with columns: country, xu_only_count, openaq_only_count,
matched_count, mean_bias, corr.
'''

import pandas as pd
import pyreadr
from babel import Locale
import reverse_geocoder as rg
from sklearn.neighbors import BallTree
import numpy as np

# All files
STATION_MATCHES = "data/station_matches.csv"
DAILY_VALUE_COMPARISON = "data/daily_value_comparison.csv"
OPENAQ_DAILY = "data/openaq_daily_aggregated_2019_window.csv"
XU_PM25_FILE = "data/PM25_data_5661_stations_cleaned_2000_2019.rds"
XU_O3_FILE = "data/O3_data_6851_stations_cleaned_2000_2019.rds"
GHOST_FILE = "data/ghost_combined_2019window.csv"
GHOST_FILE_O3 = "data/ghost_combined_o3_2019window.csv"

territories = Locale('en').territories

df_ghost = pd.read_csv(GHOST_FILE)
df_ghost_o3 = pd.read_csv(GHOST_FILE_O3)

ghost_stations = df_ghost[['station_reference', 'latitude', 'longitude']].drop_duplicates('station_reference').reset_index(drop = True)
ghost_stations_o3 = df_ghost_o3[['station_reference', 'latitude', 'longitude']].drop_duplicates('station_reference').reset_index(drop = True)

def nearest_within_1km(source_df, target_df, target_id_col, isXu):
    '''For each row in source_df, returns nearest target_df id if within 1km, else None.'''
    src = np.radians(source_df[['latitude', 'longitude']].values)
    
    if not isXu:
        tgt = np.radians(target_df[['latitude', 'longitude']].values)
    else:
        tgt = np.radians(target_df[['lat', 'lon']].values)
        
    dist, idx = BallTree(tgt, metric = 'haversine').query(src, k = 1)
    dist_km = dist[:, 0] * 6371
    return pd.Series(np.where(dist_km <= 1, target_df[target_id_col].values[idx[:, 0]], None), index = source_df.index)

geo = rg.search(list(zip(ghost_stations['latitude'], ghost_stations['longitude'])), mode = 1)
geo_o3 = rg.search(list(zip(ghost_stations_o3['latitude'], ghost_stations_o3['longitude'])), mode = 1)

ghost_stations['country'] = [territories.get(r['cc']) for r in geo]
ghost_stations_o3['country'] = [territories.get(r['cc']) for r in geo_o3]

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
   
    # Merge together the three dfs for co-located, open aq only, and xu only.
    report = xu_only_counts.merge(openaq_only_counts, on = "country", how = "outer").merge(co_located_counts, on = "country", how = "outer")
    
    openaq_stations = pd.read_csv(OPENAQ_DAILY)
    openaq_stations = openaq_stations[openaq_stations['parameter'] == SPECIES]
    openaq_stations = openaq_stations[['location_id', 'latitude', 'longitude']].drop_duplicates('location_id')
    
    if SPECIES == "pm25":
        xu_geo = xu_pm25_df[['station_id', 'lat', 'lon']].drop_duplicates('station_id') if 'lat' in xu_pm25_df else load_rds(XU_PM25_FILE)[['station_id', 'lat', 'lon']].drop_duplicates('station_id')
        ghost_stations['matched_openaq'] = nearest_within_1km(ghost_stations, openaq_stations, 'location_id', False)
        ghost_stations['matched_xu'] = nearest_within_1km(ghost_stations, xu_geo, 'station_id', True)
        
        ghost_only_counts = ghost_stations[ghost_stations['matched_openaq'].isna() & ghost_stations['matched_xu'].isna()] \
                .groupby('country').size().reset_index(name = 'ghost_only_count')
    else:
        xu_geo = xu_o3_df[['station_id', 'lat', 'lon']].drop_duplicates('station_id') if 'lat' in xu_o3_df else load_rds(XU_O3_FILE)[['station_id', 'lat', 'lon']].drop_duplicates('station_id')
        ghost_stations_o3['matched_openaq'] = nearest_within_1km(ghost_stations_o3, openaq_stations, 'location_id', False)
        ghost_stations_o3['matched_xu'] = nearest_within_1km(ghost_stations_o3, xu_geo, 'station_id', True)
        
        ghost_only_counts =     ghost_stations_o3[ghost_stations_o3['matched_openaq'].isna() & ghost_stations_o3['matched_xu'].isna()] \
                .groupby('country').size().reset_index(name = 'ghost_only_count')
    
    report = report.merge(ghost_only_counts, on = 'country', how = 'outer')
        
    # Replace Na with 0
    report[["xu_only_count", "openaq_only_count", "matched_count"]] = report[["xu_only_count", "openaq_only_count", "matched_count"]].fillna(0)
    report['ghost_only_count'] = report['ghost_only_count'].fillna(0)
    
    # Round bias and corr to 2 decimals
    report['mean_bias'] = round(report['mean_bias'], 2)
    report['corr'] = round(report['corr'], 2)
    
    # Sort and save
    report = report.sort_values('matched_count', ascending = False)
    report.to_csv(f"data/{SPECIES}_country_gap_report_ghost.csv", index = False)
