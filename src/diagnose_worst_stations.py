'''
Diagnoses the worst-disagreeing stations between OpenAQ and Xu et al., for
both pm25 and o3. For each pollutant, computes each co-located station's mean
bias, correlation, and number of matched days (from daily_value_comparison.csv),
filters out stations with too few matched days to be statistically meaningful
(< MIN_MATCHED_DAYS), then picks the 4 stations with the largest absolute bias
and the 4 with the lowest correlation.

For each of those flagged stations, plots a time series of OpenAQ's vs Xu's
daily values side by side, to help visually diagnose the likely cause of
disagreement: a consistent parallel gap suggests a measurement/calibration
offset, unrelated day-to-day patterns suggest the matched sites aren't really
the same location, and an otherwise-close match broken by one or two sharp
spikes suggests a handful of bad/anomalous readings rather than a systemic
issue.
'''

import pandas as pd
import matplotlib.pyplot as plt

DAILY_VALUE_COMPARISON = "data/daily_value_comparison.csv"
MIN_MATCHED_DAYS = 10

# Calculate Correlation
def station_corr(group):
    return group["openaq_value"].corr(group["xu_value"])

# Do same for pm25 and o3
for species in ["pm25", "o3"]:
    # Calculate bias
    daily_value_comparison_df = pd.read_csv(DAILY_VALUE_COMPARISON)
    species_comparison = daily_value_comparison_df[daily_value_comparison_df["parameter"] == species].copy()
    species_comparison["bias"] = species_comparison["openaq_value"] - species_comparison["xu_value"]

    # Calculate mean bias and correlation
    station_bias = species_comparison.groupby("location_id")["bias"].mean().reset_index(name = "mean_bias")
    station_corr_df = species_comparison.groupby("location_id").apply(station_corr).reset_index(name = "correlation")
    station_days = species_comparison.groupby("location_id").size().reset_index(name = "days_matched")

    # Merge stats and filter out locations with < 10 days
    station_stats = station_bias.merge(station_corr_df, on = "location_id").merge(station_days, on = "location_id")
    station_stats = station_stats[station_stats["days_matched"] >= MIN_MATCHED_DAYS]

    # Calculte worst bias and corr
    station_stats["abs_mean_bias"] = station_stats["mean_bias"].apply(abs)
    worst_bias = station_stats.sort_values("abs_mean_bias", ascending = False).head(4)
    worst_corr = station_stats.sort_values("correlation", ascending = True).head(4)

    # Get date and values for worst location ids
    worst_bias_data = species_comparison[species_comparison["location_id"].isin(worst_bias["location_id"])][["location_id", "date", "openaq_value", "xu_value"]]
    worst_corr_data = species_comparison[species_comparison["location_id"].isin(worst_corr["location_id"])][["location_id", "date", "openaq_value", "xu_value"]]

    # Plot graphs
    for station_id, group in worst_bias_data.groupby("location_id"):
        fig, ax = plt.subplots(figsize = (10, 6))
    
        group = group.sort_values("date")
        ax.plot(group["date"], group["openaq_value"], label = "OpenAQ", marker = "o", color = "red")
        ax.plot(group["date"], group["xu_value"], label = "Xu", marker = "o", color = "blue")

        ax.set_title(f"Station {station_id} ({species})")
        ax.set_xlabel("Date")
        ax.set_ylabel("Daily value")
        ax.legend()
    
        plt.xticks(rotation = 45)
        plt.tight_layout()
    
        plt.savefig(f"figures/Largest Difference Comparison/Bias_{station_id}_{species}.png")
        plt.show()
    
    for station_id, group in worst_corr_data.groupby("location_id"):
        fig, ax = plt.subplots(figsize = (10, 6))
    
        group = group.sort_values("date")
        ax.plot(group["date"], group["openaq_value"], label = "OpenAQ", marker = "o", color = "red")
        ax.plot(group["date"], group["xu_value"], label = "Xu", marker = "o", color = "blue")

        ax.set_title(f"Station {station_id} ({species})")
        ax.set_xlabel("Date")
        ax.set_ylabel("Daily value")
        ax.legend()
    
        plt.xticks(rotation = 45)
        plt.tight_layout()
    
        plt.savefig(f"figures/Largest Difference Comparison/Correlation_{station_id}_{species}.png")
        plt.show()  