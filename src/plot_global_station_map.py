'''
Builds interactive global maps comparing OpenAQ and Xu et al. station coverage,
one map per pollutant (pm25 and o3). Each station is categorized as:
    - Co-located: matched between OpenAQ and Xu (within 1 km), colored by mean
      bias and outlined in black where correlation > 0.9
    - OpenAQ-only: OpenAQ stations with no nearby Xu match
    - Xu-only: Xu stations with no nearby OpenAQ match

Bias/correlation values come from the ~41-day Jan 1 - Feb 10, 2019 comparison
window (daily_value_comparison.csv), not Xu's full 2000-2019 historical record.
'''

import pandas as pd
import pyreadr
import plotly.graph_objects as go

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

# Read files
station_matches_df = pd.read_csv(STATION_MATCHES)
daily_value_comparison_df = pd.read_csv(DAILY_VALUE_COMPARISON)

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

    fig.write_html(f"figures/global_station_map_{species}.html")
    fig.show()