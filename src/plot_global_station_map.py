'''
Builds interactive global maps comparing OpenAQ, Xu et al, and GHOST station coverage,
one map per pollutant (pm25 and o3). Each station is categorized as:
    - Co-located: matched between OpenAQ and Xu (within 1 km), colored by mean
      bias and outlined in black where correlation > 0.9
    - OpenAQ-only: OpenAQ stations with no nearby Xu match
    - Xu-only: Xu stations with no nearby OpenAQ match
    - GHOST only: GHOST provided stations not nearby an OpenAQ or Xu station

Bias/correlation values come from the ~41-day Jan 1 - Feb 10, 2019 comparison
window (daily_value_comparison.csv), not Xu's full 2000-2019 historical record.
'''

import pandas as pd
import pyreadr
import plotly.graph_objects as go
from sklearn.neighbors import BallTree
import numpy as np
import xarray as xr

STATION_MATCHES = "data/station_matches.csv"
DAILY_VALUE_COMPARISON = "data/daily_value_comparison.csv"
OPENAQ_DAILY = "data/openaq_daily_aggregated_2019_window.csv"
XU_PM25_FILE = "data/PM25_data_5661_stations_cleaned_2000_2019.rds"
XU_O3_FILE = "data/O3_data_6851_stations_cleaned_2000_2019.rds"

# Load rds files
def load_rds(path):
    result = pyreadr.read_r(path)
    return result[None] if None in result else list(result.values())[0]

# Calculate correlation for station match
def station_corr(group):
    return group["openaq_value"].corr(group["xu_value"])

# Calculate closest station distance and see if its within 1 km
def has_match_within_1km(points_df, ref_df, lat_col, lon_col, ref_lat_col, ref_lon_col):
        tree = BallTree(np.radians(ref_df[[ref_lat_col, ref_lon_col]].values), metric = "haversine")
        dist, _ = tree.query(np.radians(points_df[[lat_col, lon_col]].values), k = 1)
        return (dist.flatten() * 6371) <= 1

# Read files
station_matches_df = pd.read_csv(STATION_MATCHES)
daily_value_comparison_df = pd.read_csv(DAILY_VALUE_COMPARISON)

# Extract GHOST data
def extract_ghost_component(nc_folder, component, year_months, network_name):
    """Pulls one component (e.g. pm2p5) across given months from one network's folder."""
    monthly_dfs = []
    for ym in year_months:
        try:
            ds = xr.open_dataset(f"{nc_folder}/{component}_{ym}.nc")
            month_df = pd.DataFrame({
                "value": ds[component].values.flatten(),
                "value_prefiltered": ds[f"{component}_prefiltered_defaultqa"].values.flatten(),
                "station_reference": pd.Series(ds["station_reference"].values).repeat(len(ds["time"])).values,
                "latitude": pd.Series(ds["latitude"].values).repeat(len(ds["time"])).values,
                "longitude": pd.Series(ds["longitude"].values).repeat(len(ds["time"])).values,
                "date": list(ds["time"].values) * len(ds["station_reference"]),
            })
        
            month_df["network"] = network_name
            monthly_dfs.append(month_df)
            ds.close()
        except:
            print("Error in extract_ghost_component")
            
    return pd.concat(monthly_dfs, ignore_index = True)

# List of networks from GHOST to add
networks_to_add = [
    ("data/GHOST/daily_us_epa/pm2p5", "US_EPA"),
    ("data/GHOST/daily_canada_naps/pm2p5", "CANADA_NAPS"),
    ("data/GHOST/daily_chile_sinca/pm2p5", "CHILE_SINCA"),
    ("data/GHOST/daily_mexico_cdmx/pm2p5", "MEXICO_CDMX"),
    ("data/GHOST/daily_ebas_emep/pm2p5", "EBAS_EMEP"),
    ("data/GHOST/daily_uk_air/pm2p5", "UK_AIR")
]

# Extract ghost information for pm2.5 and o3
try:
    ghost_df = pd.read_csv("data/ghost_combined_2019window.csv")
    ghost_df["date"] = pd.to_datetime(ghost_df["date"])
except:
    ghost_df = pd.DataFrame(columns = ["network"])
    print("CSV doesn't exist yet")
    
for folder, name in networks_to_add:
    if len(ghost_df[ghost_df['network'] == name]) == 0:
        new_data = extract_ghost_component(folder, "pm2p5", ["201901", "201902"], name)
        ghost_df = pd.concat([ghost_df, new_data], ignore_index = True)
        ghost_df = ghost_df[ghost_df['date'] <= "2019-02-10"]
        
ghost_df.to_csv("data/ghost_combined_2019window.csv", index = False)

try:
    ghost_o3_df = pd.read_csv("data/ghost_combined_o3_2019window.csv")
    ghost_o3_df["date"] = pd.to_datetime(ghost_o3_df["date"])
except:
    ghost_o3_df = pd.DataFrame(columns = ["network"])
    print("CSV doesn't exist yet for o3")    
    
for folder, name in networks_to_add:
    if len(ghost_o3_df[ghost_o3_df['network'] == name]) == 0:
        new_data = extract_ghost_component(folder.replace("pm2p5", "sconco3"), "sconco3", ["201901", "201902"], name)
        ghost_o3_df = pd.concat([ghost_o3_df, new_data], ignore_index = True)
        ghost_o3_df = ghost_o3_df[ghost_o3_df['date'] <= "2019-02-10"]
        
ghost_o3_df.to_csv("data/ghost_combined_o3_2019window.csv", index = False)

# Create two maps, one for pm25 and anothe for o3
for species in ["pm25", "o3"]:
    station_matches = station_matches_df[station_matches_df["parameter"] == species]
    oa_to_xu = station_matches[station_matches["direction"] == "oa_to_xu"]
    xu_to_oa = station_matches[station_matches["direction"] == "xu_to_oa"]

    # Separate into co-located, openaq only, and xu only stations
    co_located_ids = oa_to_xu[oa_to_xu["matched"]]["station_id"]
    openaq_only_ids = oa_to_xu[~oa_to_xu["matched"]]["station_id"]
    xu_only_ids = xu_to_oa[~xu_to_oa["matched"]]["xu_station_id"]

    # Read file to get open aq coordinates
    openaq_daily_df = pd.read_csv(OPENAQ_DAILY)
    openaq_coords = openaq_daily_df[["location_id", "latitude", "longitude"]].drop_duplicates(subset = "location_id")
    
    # Read files to get xu station coordinates
    xu_pm25_df = load_rds(XU_PM25_FILE)
    xu_o3_df = load_rds(XU_O3_FILE)
    
    # Combine xu stations and drop duplicates
    xu_coords = pd.concat([xu_pm25_df[["station_id", "lat", "lon"]], xu_o3_df[["station_id", "lat", "lon"]]]).drop_duplicates(subset = "station_id")
    
    # Merge dfs so then every station can now also be identified by their coordinates
    co_located_df = co_located_ids.to_frame().merge(openaq_coords, left_on = "station_id", right_on = "location_id")
    openaq_only_df = openaq_only_ids.to_frame().merge(openaq_coords, left_on = "station_id", right_on = "location_id")
    xu_only_df = xu_only_ids.to_frame().merge(xu_coords, left_on = "xu_station_id", right_on = "station_id")
    
    # For each co-located station for the current species, calculate mean bias and correlation per station
    species_comparison = daily_value_comparison_df[daily_value_comparison_df["parameter"] == species].copy()
    species_comparison["bias"] = species_comparison["openaq_value"] - species_comparison["xu_value"]
    station_bias = species_comparison.groupby("location_id")["bias"].mean().reset_index(name = "mean_bias")
    station_corr_df = species_comparison.groupby("location_id").apply(station_corr).reset_index(name = "correlation")
    station_stats = station_bias.merge(station_corr_df, on = "location_id")
    
    # Merge the station stats with co_located_df containing station ids and coordintes
    co_located_df = co_located_df.merge(station_stats, on = "location_id", how = "left")

    # Create figure
    fig = go.Figure()

    outline_widths = co_located_df["correlation"].apply(lambda c: 2 if c > 0.9 else 0)

    # Plot co-located points
    max_abs_bias = co_located_df["mean_bias"].abs().max()
    fig.add_trace(go.Scattergeo(
        lon = co_located_df["longitude"],
        lat = co_located_df["latitude"],
        mode = "markers",
        marker = dict(
            size = 8,
            color = co_located_df["mean_bias"],
            colorscale = "RdBu_r",
            cmin = -max_abs_bias,
            cmax = max_abs_bias,
            colorbar = dict(title = "Mean Bias"),
            line = dict(width = outline_widths, color = "black"),
        ),
        name = "Co-located",
        hovertemplate = "Co-located<br>Bias: %{marker.color:.1f}<extra></extra>"
    ))

    # Plot Open-AQ only station points
    fig.add_trace(go.Scattergeo(
        lon = openaq_only_df["longitude"],
        lat = openaq_only_df["latitude"],
        mode = "markers",
        marker = dict(
            size = 6,
            symbol = "triangle-up",
            color = "gray",
        ),
        name = "OpenAQ-only",
    ))

    # Plot Xu only station points
    fig.add_trace(go.Scattergeo(
        lon = xu_only_df["lon"],
        lat = xu_only_df["lat"],
        mode = "markers",
        marker = dict(
            size = 6,
            symbol = "diamond",
            color = "purple",
        ),
        name = "Xu-only",
    ))
    
    # Plot GHOST-only coordinates
    if species == "pm25":
        ghost_coords = ghost_df[["station_reference", "latitude", "longitude"]].drop_duplicates(subset = "station_reference")
        xu_species_coords = xu_pm25_df[["station_id", "lat", "lon"]].drop_duplicates(subset = "station_id")
    else:
        ghost_coords = ghost_o3_df[["station_reference", "latitude", "longitude"]].drop_duplicates(subset = "station_reference")
        xu_species_coords = xu_o3_df[["station_id", "lat", "lon"]].drop_duplicates(subset = "station_id")

    openaq_daily_df = pd.read_csv(OPENAQ_DAILY)
    openaq_species_df = openaq_daily_df[openaq_daily_df["parameter"] == species]
    openaq_coords = openaq_species_df[["location_id", "latitude", "longitude"]].drop_duplicates(subset = "location_id")
    
    matched_openaq = has_match_within_1km(ghost_coords, openaq_coords, "latitude", "longitude", "latitude", "longitude")
    matched_xu = has_match_within_1km(ghost_coords, xu_species_coords, "latitude", "longitude", "lat", "lon")
    ghost_only_df = ghost_coords[~matched_openaq & ~matched_xu]
    
    fig.add_trace(go.Scattergeo(
        lon = ghost_only_df["longitude"],
        lat = ghost_only_df["latitude"],
        mode = "markers",
        marker = dict(size = 10, symbol = "star", color = "green"),
        name = "GHOST-only",
    ))
    
    print(f"Length of ghost coords for {species}: {len(ghost_coords)}")
    print(f"Length of gost only coords for {species}: {len(ghost_only_df)}")

    fig.update_layout(
        title = f"OpenAQ vs Xu et al. Station Comparison for {species}",
        legend = dict(x = 0.01, y = 0.05, xanchor = "left", yanchor = "bottom"),
        hoverlabel = dict(bgcolor = "black", font = dict(color = "white")),
        geo = dict(
            projection_type = "natural earth",
            showland = True,
            landcolor = "rgb(150, 200, 150)"
        )
    )

    fig.write_html(f"figures/global_station_map_{species}_ghost.html", include_plotlyjs = "cdn")
    fig.show()