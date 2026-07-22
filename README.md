# openaq-data-analysis

Tools for downloading, processing, and analyzing global air quality data from [OpenAQ](https://openaq.org/) — including station coverage exploration, daily PM2.5 and MDA8 ozone computation, and validation against external reference datasets.

This repository holds a set of standalone Python scripts (no orchestration framework — each script is run manually, in order) that together answer three questions:

1. **How much and what kind of data does OpenAQ actually have?** (`check_sensor_coverage.py`)
2. **How well does OpenAQ agree with an independent, previously-published ground-truth dataset (Xu et al.)?** (`fetch_global_stations.py` → `fetch_global_hourly_window.py` → `aggregate_daily_mda8.py` → `match_and_compare.py` → `diagnose_worst_stations.py` → `plot_global_station_map.py`)
3. **For a single country (India), how much data do you lose if you only have daily averages instead of full hourly readings?** (`india_daily_data.py`, `india_hourly_data.py`, `compare_india_coverage.py`)

## Data source

All measurements come from the [OpenAQ v3 API](https://docs.openaq.org/). Two pollutants are covered throughout the project:

- **PM2.5** — fine particulate matter, aggregated as a simple daily mean of hourly readings.
- **O3 (ozone)** — aggregated as **MDA8**, the maximum 8-hour rolling average within a day (the standard regulatory metric for ozone), with unit conversion between µg/m³, ppb, and ppm (using 1.963 as the ppb → µg/m³ factor at 25°C / 1 atm).

The validation workflow additionally compares against a compiled external reference dataset ("Xu et al.") of ~5,600 PM2.5 stations and ~6,900 O3 stations, provided as `.rds` (R data) files and read into Python with `pyreadr`. These reference files are large and not redistributed in this repository — see [Data availability](#data-availability) below.

## Repository structure

```
.
├── src/                              # All processing/analysis scripts
│   ├── fetch_global_stations.py      # Step 1 (global): download station list for a pollutant
│   ├── check_sensor_coverage.py      # Sample sensors and check reporting frequency / history depth
│   ├── fetch_global_hourly_window.py # Step 2 (global): download a fixed hourly window for all sensors
│   ├── aggregate_daily_mda8.py       # Step 3 (global): hourly -> daily PM2.5 mean / O3 MDA8
│   ├── match_and_compare.py          # Step 4 (global): match OpenAQ <-> Xu et al. stations, compare values
│   ├── diagnose_worst_stations.py    # Step 5 (global): plot the worst-agreeing stations
│   ├── plot_global_station_map.py    # Step 6 (global): interactive map of coverage + bias
│   ├── india_daily_data.py           # India: download daily PM2.5
│   ├── india_hourly_data.py          # India: download hourly PM2.5
│   └── compare_india_coverage.py     # India: daily vs. hourly data-completeness comparison
├── data/                             # Inputs/outputs (large raw downloads are not checked in — see below)
├── figures/                          # Generated plots and interactive HTML maps
├── requirements.txt
└── .gitignore
```

## How it works

### 1. Global OpenAQ vs. Xu et al. validation

This workflow builds a snapshot of global OpenAQ coverage for a ~41-day window (Jan 1 – Feb 10, 2019 — chosen to overlap with the Xu et al. reference dataset), aggregates it to daily values, and checks how well it agrees with the reference stations.

| Step | Script | What it does | Output |
|---|---|---|---|
| 1 | `fetch_global_stations.py` | Pages through `/v3/locations` for a given `parameters_id` (PM2.5 or O3 — edit the constant at the top and re-run once per pollutant) and saves the full global station list. | `data/global_pm25_stations.json`, `data/global_o3_stations.json` |
| 2 | `check_sensor_coverage.py` | Randomly samples 500 sensors per pollutant and queries `/v3/sensors/{id}` to classify each as hourly/daily/other-interval reporting, and whether its history reaches back to Jan 2000. | `data/sensor_coverage_sample.csv` |
| 3 | `fetch_global_hourly_window.py` | Downloads hourly readings for every known PM2.5/O3 sensor over the fixed 2019 window, resuming from where a partial run left off. | `data/global_hourly_2019_window.csv` (raw, not checked in) |
| 4 | `aggregate_daily_mda8.py` | Collapses hourly data into one row per station-day: PM2.5 as the daily mean, O3 as MDA8 (requires at least 6 of the 8 hours present in a window to count). Attaches station coordinates. | `data/openaq_daily_aggregated_2019_window.csv` |
| 5 | `match_and_compare.py` | Nearest-neighbor matches OpenAQ stations to Xu et al. stations by haversine distance (≤ 1 km, checked in both directions), then joins matched station-days and computes correlation / mean absolute difference per pollutant. | `data/station_matches.csv`, `data/daily_value_comparison.csv` |
| 6 | `diagnose_worst_stations.py` | Among matched stations with ≥ 10 overlapping days, plots side-by-side daily time series for the 4 stations with the largest bias and the 4 with the lowest correlation, per pollutant — useful for telling a calibration offset apart from a location mismatch or a one-off spike. | `figures/Largest Difference Comparison/*.png` |
| 7 | `plot_global_station_map.py` | Builds an interactive Plotly map per pollutant: co-located stations colored by mean bias (outlined in black where correlation > 0.9), plus OpenAQ-only and Xu-only stations shown separately. | `figures/global_station_map_pm25.html`, `figures/global_station_map_o3.html` |

### 2. India: daily vs. hourly coverage

A smaller, country-specific workflow that asks a practical question: if you can only afford to pull *daily* aggregates from the API instead of full *hourly* data, how much completeness do you actually lose?

| Script | What it does | Output |
|---|---|---|
| `india_daily_data.py` | Downloads daily PM2.5 values (`/v3/sensors/{id}/days`) for every PM2.5 sensor listed in `data/india_stations.json`. | `data/india_pm25_jan_jun_2026.csv` |
| `india_hourly_data.py` | Downloads the equivalent hourly data (`/v3/sensors/{id}/hours`) for the same stations — roughly 24× the row count of the daily pull, so it takes noticeably longer to run. | `data/india_pm25_jan_jun_2026_hourly.csv` (raw, not checked in) |
| `compare_india_coverage.py` | For each station, computes % of expected days with data, % of expected hours with data, and % of days with *at least one* hourly reading, then ranks stations by how much worse hourly coverage is than daily coverage. | `data/india_coverage_comparison.csv` |

`data/india_stations.json` (OpenAQ station metadata for India, used as the sensor list for all three scripts above) is included in the repo as a starting point.

## Setup

You'll need an OpenAQ API key (free tier: 60 requests/minute, 2,000/hour — the scripts are paced to stay under this). Create a `.env` file in the repo root:

```
OPENAQ_API_KEY=your_key_here
```

Get a key at [explore.openaq.org](https://explore.openaq.org/register).

## Running the scripts

All scripts expect to be run from the repository root, since file paths (`data/...`, `figures/...`) are relative:

```bash
python src/fetch_global_stations.py       # run once per pollutant, editing PARAMETER_ID/OUTPUT_FILE
python src/fetch_global_hourly_window.py
python src/aggregate_daily_mda8.py
python src/match_and_compare.py
python src/diagnose_worst_stations.py
python src/plot_global_station_map.py
```

Long-running fetch scripts (`fetch_global_hourly_window.py`, `india_hourly_data.py`) write progress to disk incrementally and can be safely re-run — they pick up where a previous run left off rather than starting over, and back off automatically on HTTP 429 (rate limit) responses.

## Data availability

Large raw downloads are **not** checked into this repository (either because of GitHub's file size limits or because they're simple to regenerate): the full global hourly window, the per-pollutant global station lists, and the India hourly pull. Run the corresponding script to regenerate them locally.

The Xu et al. reference dataset (`data/PM25_data_5661_stations_cleaned_2000_2019.rds` and `data/O3_data_6851_stations_cleaned_2000_2019.rds`) is an external, previously-published compilation and is not redistributed here — `match_and_compare.py` and `plot_global_station_map.py` expect these files to be supplied separately.

Everything else needed to inspect the results without re-running the pipeline — aggregated daily values, station matches, comparison tables, and the generated figures — is included in `data/` and `figures/`.
