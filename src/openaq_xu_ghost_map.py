'''
Builds interactive global maps showing OpenAQ, Xu et al., and GHOST station
locations as three independent, toggleable layers — no co-location matching.
Click legend entries to show/hide any combination of the three sources.
One map per pollutant (pm25 and o3).
'''

import pandas as pd
import pyreadr
import plotly.graph_objects as go

OPENAQ_DAILY = "data/openaq_daily_aggregated_2019_window.csv"
XU_PM25_FILE = "data/PM25_data_5661_stations_cleaned_2000_2019.rds"
XU_O3_FILE = "data/O3_data_6851_stations_cleaned_2000_2019.rds"
GHOST_FILE = "data/ghost_combined_2019window.csv"
GHOST_FILE_O3 = "data/ghost_combined_o3_2019window.csv"

def load_rds(path):
    result = pyreadr.read_r(path)
    return result[None] if None in result else list(result.values())[0]

openaq_daily_df = pd.read_csv(OPENAQ_DAILY)
xu_pm25_df = load_rds(XU_PM25_FILE)
xu_o3_df = load_rds(XU_O3_FILE)
ghost_df = pd.read_csv(GHOST_FILE)
ghost_o3_df = pd.read_csv(GHOST_FILE_O3)

for species in ["pm25", "o3"]:
    openaq_coords = openaq_daily_df[openaq_daily_df["parameter"] == species][["location_id", "latitude", "longitude"]].drop_duplicates("location_id")

    xu_df = xu_pm25_df if species == "pm25" else xu_o3_df
    xu_coords = xu_df[["station_id", "lat", "lon"]].drop_duplicates("station_id")

    ghost_source = ghost_df if species == "pm25" else ghost_o3_df
    ghost_coords = ghost_source[["station_reference", "latitude", "longitude"]].drop_duplicates("station_reference")

    fig = go.Figure()

    fig.add_trace(go.Scattergeo(
        lon = openaq_coords["longitude"], lat = openaq_coords["latitude"],
        mode = "markers",
        marker = dict(size = 9, symbol = "circle", color = "orange", line = dict(width = 1, color = "black")),
        name = "OpenAQ",
    ))
    fig.add_trace(go.Scattergeo(
        lon = xu_coords["lon"], lat = xu_coords["lat"],
        mode = "markers", marker = dict(size = 6, symbol = "diamond", color = "purple"),
        name = "Xu et al.",
    ))
    fig.add_trace(go.Scattergeo(
        lon = ghost_coords["longitude"], lat = ghost_coords["latitude"],
        mode = "markers", marker = dict(size = 9, symbol = "star", color = "green"),
        name = "GHOST",
    ))

    fig.update_layout(
        title = f"OpenAQ vs Xu et al. vs GHOST Station Locations for {species} (click legend to toggle)",
        legend = dict(x = 0.01, y = 0.05, xanchor = "left", yanchor = "bottom"),
        geo = dict(projection_type = "natural earth", showland = True, landcolor = "rgb(150, 200, 150)"),
    )

    fig.write_html(f"figures/global_station_layers_{species}.html", include_plotlyjs = "cdn")
    fig.show()