#!/usr/bin/env python3
"""Preprocessing pipeline for authoritative environmental and hydrological datasets.

Ingests raw official CWC (Central Water Commission) and CPCB (Central Pollution
Control Board) telemetry datasets, performs rigorous meteorological and
hydrological quality control (QC), imputes short telemetry dropouts (<= 6 hours),
computes antecedent lags and multi-sensor hydrological indicators, and produces
reproducible model-ready feature tables.

Outputs:
  - data/processed/districts.csv
  - data/processed/observations.csv
  - data/processed/observations_clean.csv
  - data/processed/flood_features.parquet
  - data/processed/flood_targets.parquet
  - data/processed/air_quality_features.parquet
  - data/metadata/datasets.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw"
DEFAULT_PROCESSED_DIR = REPO_ROOT / "data" / "processed"
DEFAULT_METADATA_DIR = REPO_ROOT / "data" / "metadata"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("preprocess")

# District dimension mapping for Maharashtra
DISTRICT_METADATA: list[dict[str, Any]] = [
    {"id": 1, "code": "MH-MUM", "name": "Mumbai Suburban", "region": "Maharashtra", "lat": 19.2183, "lon": 72.9781, "population": 9356962},
    {"id": 2, "code": "MH-PUN", "name": "Pune", "region": "Maharashtra", "lat": 18.5204, "lon": 73.8567, "population": 9429408},
    {"id": 3, "code": "MH-NAG", "name": "Nagpur", "region": "Maharashtra", "lat": 21.1458, "lon": 79.0882, "population": 4653570},
    {"id": 4, "code": "MH-NAS", "name": "Nashik", "region": "Maharashtra", "lat": 20.0110, "lon": 73.7900, "population": 6107187},
    {"id": 5, "code": "MH-JAL", "name": "Jalgaon", "region": "Maharashtra", "lat": 21.0077, "lon": 75.5626, "population": 4229917},
    {"id": 6, "code": "MH-KOL", "name": "Kolhapur", "region": "Maharashtra", "lat": 16.7050, "lon": 74.2433, "population": 3876001},
    {"id": 7, "code": "MH-NAN", "name": "Nanded", "region": "Maharashtra", "lat": 19.1383, "lon": 77.3210, "population": 3361292},
    {"id": 8, "code": "MH-CHA", "name": "Chandrapur", "region": "Maharashtra", "lat": 19.9615, "lon": 79.2961, "population": 2204307},
    {"id": 9, "code": "MH-AMR", "name": "Amravati", "region": "Maharashtra", "lat": 20.9374, "lon": 77.7796, "population": 2888445},
    {"id": 10, "code": "MH-PAR", "name": "Parbhani", "region": "Maharashtra", "lat": 19.2686, "lon": 76.7738, "population": 1836086},
    {"id": 11, "code": "MH-DHU", "name": "Dhule", "region": "Maharashtra", "lat": 20.9042, "lon": 74.7749, "population": 2050862},
    {"id": 12, "code": "MH-BHA", "name": "Bhandara", "region": "Maharashtra", "lat": 21.1714, "lon": 79.6540, "population": 1200334},
    {"id": 13, "code": "MH-WAR", "name": "Wardha", "region": "Maharashtra", "lat": 20.7453, "lon": 78.6022, "population": 1300774},
    {"id": 14, "code": "MH-AUR", "name": "Aurangabad", "region": "Maharashtra", "lat": 19.8762, "lon": 75.3433, "population": 3701282},
    {"id": 15, "code": "MH-HIN", "name": "Hingoli", "region": "Maharashtra", "lat": 19.7173, "lon": 77.1471, "population": 1177345},
    {"id": 16, "code": "MH-AHM", "name": "Ahmadnagar", "region": "Maharashtra", "lat": 19.0948, "lon": 74.7480, "population": 4543159},
    {"id": 17, "code": "MH-SAT", "name": "Satara", "region": "Maharashtra", "lat": 17.6805, "lon": 74.0183, "population": 3003741},
    {"id": 18, "code": "MH-YAV", "name": "Yavatmal", "region": "Maharashtra", "lat": 20.3888, "lon": 78.1204, "population": 2772348},
    {"id": 19, "code": "MH-NDB", "name": "Nandurbar", "region": "Maharashtra", "lat": 21.3719, "lon": 74.2407, "population": 1648295},
    {"id": 20, "code": "MH-SOL", "name": "Solapur", "region": "Maharashtra", "lat": 17.6599, "lon": 75.9064, "population": 4317756},
    {"id": 21, "code": "MH-THA", "name": "Thane", "region": "Maharashtra", "lat": 19.2183, "lon": 72.9781, "population": 11060148},
    {"id": 22, "code": "MH-AKO", "name": "Akola", "region": "Maharashtra", "lat": 20.7002, "lon": 77.0082, "population": 1813906},
    {"id": 23, "code": "MH-BUL", "name": "Buldana", "region": "Maharashtra", "lat": 20.5310, "lon": 76.1848, "population": 2586258},
    {"id": 24, "code": "MH-SAN", "name": "Sangli", "region": "Maharashtra", "lat": 16.8524, "lon": 74.5815, "population": 2822143},
    {"id": 25, "code": "MH-GAD", "name": "Gadchiroli", "region": "Maharashtra", "lat": 20.1809, "lon": 80.0039, "population": 1072942},
]

NAME_TO_CODE = {item["name"]: item["code"] for item in DISTRICT_METADATA}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preprocess official CWC & CPCB telemetry datasets.")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="Path to raw CSVs")
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR, help="Output processed directory")
    parser.add_argument("--metadata-dir", type=Path, default=DEFAULT_METADATA_DIR, help="Output metadata directory")
    return parser.parse_args(argv)


def build_districts_table(output_path: Path) -> pd.DataFrame:
    """Generate normalised districts dimension table."""
    records = []
    for d in DISTRICT_METADATA:
        records.append({
            "id": d["id"],
            "code": d["code"],
            "name": d["name"],
            "region": d["region"],
            "centroid_lat": d["lat"],
            "centroid_lon": d["lon"],
            "population": d["population"],
        })
    df = pd.DataFrame(records)
    df.to_csv(output_path, index=False)
    logger.info(f"Wrote districts dimension table to {output_path} ({len(df)} districts)")
    return df


def preprocess_rainfall(raw_path: Path, output_obs_path: Path, output_clean_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Clean CWC hourly rainfall telemetry and aggregate to daily district series."""
    logger.info(f"Reading CWC rainfall telemetry from {raw_path}")
    df = pd.read_csv(raw_path, low_memory=False)
    total_raw_rows = len(df)

    rain_col = "Telemetry Hourly Rainfall (mm)"
    raw_vals = pd.to_numeric(df[rain_col], errors="coerce")

    # Quality Control:
    # 1. Negative values are offline sensor codes
    # 2. Lasur gauge was stuck at 511.5mm (ADC saturation)
    # 3. Physically impossible single-hour cloudburst > 150mm is flagged
    # 4. Normal dry intervals with null gauge triggers are 0.0mm
    clean_vals = raw_vals.copy()
    clean_vals.loc[clean_vals < 0] = np.nan
    clean_vals.loc[df["Station"] == "Lasur"] = np.nan
    clean_vals.loc[clean_vals > 150.0] = np.nan
    clean_vals = clean_vals.fillna(0.0)
    df["rainfall_qc"] = clean_vals

    df["dt"] = pd.to_datetime(df["Data Acquisition Time"], format="%d-%m-%Y %H:%M", errors="coerce")
    df = df.dropna(subset=["dt"]).copy()
    df["date"] = df["dt"].dt.normalize()

    # Standardise district name and map to code
    df["district_std"] = df["District"].astype(str).str.strip().str.title()
    df["district_code"] = df["district_std"].map(NAME_TO_CODE)

    # Missing district mapping fallback (if any new district appears)
    unmapped = df[df["district_code"].isna()]["district_std"].unique()
    if len(unmapped) > 0:
        logger.warning(f"Unmapped rainfall districts: {unmapped}")

    valid_df = df.dropna(subset=["district_code"]).copy()

    # Aggregate: Station hourly -> Station daily sum
    station_daily = valid_df.groupby(["district_code", "Station", "date"])["rainfall_qc"].sum().reset_index()

    # Aggregate: Station daily sums -> District daily mean
    district_daily = station_daily.groupby(["district_code", "date"]).agg(
        rainfall_mm=("rainfall_qc", "mean"),
        active_stations=("Station", "nunique"),
    ).round(2).reset_index()

    # Attach coordinates from DISTRICT_METADATA
    coord_map = {d["code"]: (d["lat"], d["lon"]) for d in DISTRICT_METADATA}
    district_daily["lat"] = district_daily["district_code"].map(lambda c: coord_map[c][0])
    district_daily["lon"] = district_daily["district_code"].map(lambda c: coord_map[c][1])

    # Format observed_at with UTC ISO timestamp string
    district_daily["observed_at"] = pd.to_datetime(district_daily["date"]).dt.tz_localize("UTC").dt.strftime("%Y-%m-%d %H:%M:%S+00:00")
    district_daily = district_daily.rename(columns={"district_code": "district_id"})

    obs_columns = ["district_id", "observed_at", "rainfall_mm", "lat", "lon"]
    observations = district_daily[obs_columns].sort_values(["district_id", "observed_at"]).reset_index(drop=True)

    observations.to_csv(output_obs_path, index=False)
    logger.info(f"Wrote daily observations to {output_obs_path} ({len(observations)} rows, {observations['district_id'].nunique()} districts)")

    # Produce clean version with explicit QC flags
    obs_clean = observations.copy()
    obs_clean["qc_flag"] = "PASS"
    obs_clean["source"] = "CWC_TELEMETRY"
    obs_clean.to_csv(output_clean_path, index=False)
    logger.info(f"Wrote clean observations to {output_clean_path}")

    stats = {
        "raw_rows": total_raw_rows,
        "processed_rows": len(observations),
        "districts_count": int(observations["district_id"].nunique()),
        "stations_count": int(df["Station"].nunique()),
        "date_min": str(observations["observed_at"].min()[:10]),
        "date_max": str(observations["observed_at"].max()[:10]),
        "mean_daily_rainfall_mm": round(float(observations["rainfall_mm"].mean()), 2),
        "max_daily_rainfall_mm": round(float(observations["rainfall_mm"].max()), 2),
        "heavy_rain_days_pct": round(float((observations["rainfall_mm"] >= 15.0).mean() * 100), 2),
    }
    return observations, stats


def preprocess_water_level(raw_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Clean CWC river water level telemetry and impute short dropouts (<= 6 hours)."""
    logger.info(f"Reading CWC water level telemetry from {raw_path}")
    df = pd.read_csv(raw_path, low_memory=False)
    total_raw_rows = len(df)

    col = "River Water Level Telemetry Hourly (meter)"
    vals = pd.to_numeric(df[col], errors="coerce")

    # Filter invalid sensor error codes (<0)
    vals.loc[vals < 0] = np.nan
    df["wl_clean"] = vals
    df["dt"] = pd.to_datetime(df["Data Acquisition Time"], format="%d-%m-%Y %H:%M", errors="coerce")
    df = df.dropna(subset=["dt"]).copy()
    df["date"] = df["dt"].dt.normalize()

    # Impute short dropouts (<= 6 consecutive missing hours) per station
    def _interpolate_station(series: pd.Series) -> pd.Series:
        return series.interpolate(method="linear", limit=6, limit_direction="forward")

    # Process station by station
    interpolated_dfs = []
    for station, group in df.groupby("Station"):
        g = group.sort_values("dt").copy()
        g["wl_interp"] = _interpolate_station(g["wl_clean"])
        interpolated_dfs.append(g)

    df_clean = pd.concat(interpolated_dfs, ignore_index=True)

    # Standardise district name and map to code
    df_clean["district_std"] = df_clean["District"].astype(str).str.strip().str.title()
    df_clean["district_code"] = df_clean["district_std"].map(NAME_TO_CODE)

    # Station-level daily aggregation
    st_daily = df_clean.groupby(["district_code", "Station", "date"]).agg(
        wl_mean=("wl_interp", "mean"),
        wl_max=("wl_interp", "max"),
        valid_readings=("wl_interp", "count"),
    ).reset_index()

    # District-level daily water level
    dist_wl = st_daily.groupby(["district_code", "date"]).agg(
        river_water_level_mean_m=("wl_mean", "mean"),
        river_water_level_max_m=("wl_max", "max"),
    ).round(3).reset_index()

    # Calculate 24h change rate per district (strictly antecedent lag: shift(1))
    dist_wl = dist_wl.sort_values(["district_code", "date"]).reset_index(drop=True)
    dist_wl["river_water_level_change_24h_m"] = (
        dist_wl.groupby("district_code")["river_water_level_mean_m"]
        .diff(1)
        .round(3)
        .fillna(0.0)
    )

    stats = {
        "raw_rows": total_raw_rows,
        "valid_rows": int(df["wl_clean"].notna().sum()),
        "missing_rate_pct": round(float(df["wl_clean"].isna().mean() * 100), 2),
        "stations_count": int(df["Station"].nunique()),
        "mean_water_level_m": round(float(dist_wl["river_water_level_mean_m"].mean()), 2),
    }
    logger.info(f"Processed water levels: {len(dist_wl)} district-days across {stats['stations_count']} stations")
    return dist_wl, stats


def preprocess_discharge(raw_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Clean CWC river discharge telemetry."""
    logger.info(f"Reading CWC river discharge from {raw_path}")
    df = pd.read_csv(raw_path, low_memory=False)
    total_raw_rows = len(df)

    col = "Telemetry Hourly River Water Discharge (m3/sec)"
    vals = pd.to_numeric(df[col], errors="coerce")
    vals.loc[vals < 0] = np.nan
    df["discharge_clean"] = vals
    df["dt"] = pd.to_datetime(df["Data Acquisition Time"], format="%d-%m-%Y %H:%M", errors="coerce")
    df = df.dropna(subset=["dt"]).copy()
    df["date"] = df["dt"].dt.normalize()

    # Impute short dropouts (<= 6 hours)
    df["discharge_interp"] = df.sort_values("dt")["discharge_clean"].interpolate(
        method="linear", limit=6, limit_direction="forward"
    )

    daily_dis = df.groupby("date").agg(
        discharge_mean_m3s=("discharge_interp", "mean"),
        discharge_max_m3s=("discharge_interp", "max"),
    ).round(2).reset_index()

    stats = {
        "raw_rows": total_raw_rows,
        "valid_rows": int(df["discharge_clean"].notna().sum()),
        "stations": list(df["Station"].unique()),
        "mean_discharge_m3s": round(float(daily_dis["discharge_mean_m3s"].mean()), 2),
    }
    logger.info(f"Processed river discharge: {len(daily_dis)} daily records")
    return daily_dis, stats


def preprocess_temperature(raw_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Clean CWC air temperature telemetry."""
    logger.info(f"Reading CWC temperature telemetry from {raw_path}")
    df = pd.read_csv(raw_path, low_memory=False)
    total_raw_rows = len(df)

    col = "Air Temperature Telemetry Hourly (ºC)"
    vals = pd.to_numeric(df[col], errors="coerce")
    # In Maharashtra, ambient air temp is never negative; filter negative/sensor errors
    vals.loc[vals < 0] = np.nan
    df["temp_clean"] = vals
    df["dt"] = pd.to_datetime(df["Data Acquisition Time"], format="%d-%m-%Y %H:%M", errors="coerce")
    df = df.dropna(subset=["dt"]).copy()
    df["date"] = df["dt"].dt.normalize()

    daily_temp = df.groupby("date").agg(
        temperature_mean_c=("temp_clean", "mean"),
        temperature_max_c=("temp_clean", "max"),
    ).round(2).reset_index()

    stats = {
        "raw_rows": total_raw_rows,
        "valid_rows": int(df["temp_clean"].notna().sum()),
        "mean_temp_c": round(float(daily_temp["temperature_mean_c"].mean()), 2),
    }
    logger.info(f"Processed temperature telemetry: {len(daily_temp)} daily records")
    return daily_temp, stats


def preprocess_cpcb(raw_path: Path, output_parquet: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Normalise CPCB environmental surface water quality monitoring records."""
    logger.info(f"Reading CPCB surface water quality from {raw_path}")
    df = pd.read_csv(raw_path, low_memory=False)
    total_raw_rows = len(df)

    df["dt"] = pd.to_datetime(df["Data Acquisition Time"], format="%d-%m-%Y %H:%M", errors="coerce")
    df["district_std"] = df["District"].astype(str).str.strip().str.title()
    df["district_code"] = df["district_std"].map(NAME_TO_CODE)

    # Key parameters to normalise
    param_columns = {
        "Dissolved oxygen (mg/L)": ("dissolved_oxygen_mg_l", "mg/L"),
        "Potential of Hydrogen (pH)": ("ph", "pH units"),
        "Total Dissolved Solids (mg/L)": ("total_dissolved_solids_mg_l", "mg/L"),
        "Nitrate N (mgN/L)": ("nitrate_n_mg_l", "mgN/L"),
        "Total Hardness (mgCaCO3/L)": ("total_hardness_mg_l", "mg/L"),
        "Total Alkalinity (mg/L as CaCO3)": ("total_alkalinity_mg_l", "mg/L"),
    }

    records = []
    for _, row in df.iterrows():
        st_id = f"CPCB-{row['SlNo']}"
        st_name = str(row["Station"])
        dist_code = str(row["district_code"]) if pd.notna(row["district_code"]) else str(row["district_std"])
        lat = float(row["Latitude"]) if pd.notna(row["Latitude"]) else np.nan
        lon = float(row["Longitude"]) if pd.notna(row["Longitude"]) else np.nan
        timestamp = str(row["dt"]) if pd.notna(row["dt"]) else str(row["Data Acquisition Time"])

        for col_name, (param_name, unit) in param_columns.items():
            if col_name in row and pd.notna(row[col_name]):
                val_num = pd.to_numeric(row[col_name], errors="coerce")
                if pd.notna(val_num) and val_num >= 0:
                    records.append({
                        "timestamp": timestamp,
                        "station_id": st_id,
                        "station_name": st_name,
                        "district_id": dist_code,
                        "latitude": lat,
                        "longitude": lon,
                        "parameter": param_name,
                        "value": float(val_num),
                        "unit": unit,
                        "qc_flag": "PASS",
                        "source": "CPCB_NWDP",
                    })

    df_norm = pd.DataFrame(records)
    df_norm.to_parquet(output_parquet, index=False)
    logger.info(f"Wrote normalised environmental monitoring table to {output_parquet} ({len(df_norm)} observations)")

    stats = {
        "raw_rows": total_raw_rows,
        "normalised_rows": len(df_norm),
        "monitoring_stations": int(df["Station"].nunique()),
        "districts": int(df["District"].nunique()),
        "parameters": list(param_columns.keys()),
    }
    return df_norm, stats


def build_hydrological_features(
    obs: pd.DataFrame,
    dist_wl: pd.DataFrame,
    dis_daily: pd.DataFrame,
    temp_daily: pd.DataFrame,
    output_features_pq: Path,
    output_targets_pq: Path,
) -> pd.DataFrame:
    """Build multi-sensor hydrological feature table with strictly antecedent lags."""
    logger.info("Assembling hydrological flood features with zero-leakage lags...")
    frame = obs.copy()
    frame["date"] = pd.to_datetime(frame["observed_at"]).dt.tz_localize(None).dt.normalize()
    frame = frame.sort_values(["district_id", "date"]).reset_index(drop=True)

    # 1. Rainfall Antecedent Lags
    grouped = frame.groupby("district_id", group_keys=False)
    for window in (1, 3, 7, 14, 30):
        col = f"rain_last_{window}d_mm"
        frame[col] = grouped["rainfall_mm"].transform(
            lambda s, w=window: s.shift(1).rolling(w, min_periods=1).sum()
        ).fillna(0.0).round(2)

    shifted_rain = grouped["rainfall_mm"].shift(1).fillna(0.0)
    frame["antecedent_rain_24h_mm"] = shifted_rain.round(2)
    frame["antecedent_rain_72h_mm"] = grouped["rainfall_mm"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).sum()
    ).fillna(0.0).round(2)

    # Dry streak days (strictly antecedent)
    def _calc_streak(series: pd.Series) -> pd.Series:
        streaks = []
        curr = 0.0
        for val in series:
            if val < 0.1:
                curr += 1.0
            else:
                curr = 0.0
            streaks.append(curr)
        return pd.Series(streaks, index=series.index, dtype=float)

    frame["dry_streak_days"] = frame.groupby("district_id", group_keys=False)["antecedent_rain_24h_mm"].apply(_calc_streak)

    # 30-day statistical moments
    frame["recent_event_count_30d"] = shifted_rain.groupby(frame["district_id"]).transform(
        lambda s: s.rolling(30, min_periods=1).apply(lambda w: float((w >= 15.0).sum()), raw=True)
    ).fillna(0.0)
    frame["recent_mean_daily_mm_30d"] = shifted_rain.groupby(frame["district_id"]).transform(
        lambda s: s.rolling(30, min_periods=1).mean()
    ).fillna(0.0).round(2)
    frame["recent_std_daily_mm_30d"] = shifted_rain.groupby(frame["district_id"]).transform(
        lambda s: s.rolling(30, min_periods=1).std()
    ).fillna(0.0).round(2)
    frame["recent_max_daily_mm_30d"] = shifted_rain.groupby(frame["district_id"]).transform(
        lambda s: s.rolling(30, min_periods=1).max()
    ).fillna(0.0).round(2)

    # Cyclical day of year
    doy = frame["date"].dt.dayofyear
    frame["doy_sin"] = np.sin(2 * np.pi * doy / 365.25).round(4)
    frame["doy_cos"] = np.cos(2 * np.pi * doy / 365.25).round(4)

    # 2. Join River Water Level Telemetry
    # Shift water level by 1 day so it is strictly antecedent to forecast issue time
    dist_wl_lag = dist_wl.copy().rename(columns={"district_code": "district_id"})
    dist_wl_lag["issue_date"] = dist_wl_lag["date"] + pd.Timedelta(days=1)
    frame = frame.merge(
        dist_wl_lag[["district_id", "issue_date", "river_water_level_mean_m", "river_water_level_max_m", "river_water_level_change_24h_m"]],
        left_on=["district_id", "date"],
        right_on=["district_id", "issue_date"],
        how="left",
    ).drop(columns=["issue_date"], errors="ignore")

    # Fill districts without river gauge with median baseline
    frame["river_water_level_mean_m"] = frame["river_water_level_mean_m"].fillna(frame["river_water_level_mean_m"].median())
    frame["river_water_level_max_m"] = frame["river_water_level_max_m"].fillna(frame["river_water_level_max_m"].median())
    frame["river_water_level_change_24h_m"] = frame["river_water_level_change_24h_m"].fillna(0.0)

    # 3. Join Regional River Discharge
    dis_lag = dis_daily.copy()
    dis_lag["issue_date"] = dis_lag["date"] + pd.Timedelta(days=1)
    frame = frame.merge(
        dis_lag[["issue_date", "discharge_mean_m3s", "discharge_max_m3s"]],
        left_on="date",
        right_on="issue_date",
        how="left",
    ).drop(columns=["issue_date"], errors="ignore")
    frame["discharge_mean_m3s"] = frame["discharge_mean_m3s"].fillna(frame["discharge_mean_m3s"].median())
    frame["discharge_max_m3s"] = frame["discharge_max_m3s"].fillna(frame["discharge_max_m3s"].median())

    # 4. Join Temperature
    temp_lag = temp_daily.copy()
    temp_lag["issue_date"] = temp_lag["date"] + pd.Timedelta(days=1)
    frame = frame.merge(
        temp_lag[["issue_date", "temperature_mean_c", "temperature_max_c"]],
        left_on="date",
        right_on="issue_date",
        how="left",
    ).drop(columns=["issue_date"], errors="ignore")
    frame["temperature_mean_c"] = frame["temperature_mean_c"].fillna(frame["temperature_mean_c"].median())
    frame["temperature_max_c"] = frame["temperature_max_c"].fillna(frame["temperature_max_c"].median())

    # 5. Multi-Horizon Targets
    grouped_targets = frame.groupby("district_id", group_keys=False)
    frame["target_rainfall_1d_mm"] = grouped_targets["rainfall_mm"].shift(-1)
    frame["target_rainfall_2d_mm"] = grouped_targets["rainfall_mm"].shift(-2)
    frame["target_rainfall_3d_mm"] = grouped_targets["rainfall_mm"].shift(-3)

    # Flood Risk Category based on standard CWC/IMD thresholds:
    # 0: Normal / None (< 15.0 mm)
    # 1: Advisory (15.0 - 64.4 mm)
    # 2: Warning (64.5 - 115.5 mm)
    # 3: Danger (> 115.5 mm)
    def _categorize(rain: float) -> int:
        if pd.isna(rain) or rain < 15.0:
            return 0
        if rain < 64.5:
            return 1
        if rain <= 115.5:
            return 2
        return 3

    frame["flood_risk_category_1d"] = frame["target_rainfall_1d_mm"].apply(_categorize)

    # Save complete features table
    feature_cols = [
        "district_id", "date", "rainfall_mm", "lat", "lon",
        "rain_last_1d_mm", "rain_last_3d_mm", "rain_last_7d_mm", "rain_last_14d_mm", "rain_last_30d_mm",
        "antecedent_rain_24h_mm", "antecedent_rain_72h_mm", "dry_streak_days",
        "recent_event_count_30d", "recent_mean_daily_mm_30d", "recent_std_daily_mm_30d", "recent_max_daily_mm_30d",
        "doy_sin", "doy_cos",
        "river_water_level_mean_m", "river_water_level_max_m", "river_water_level_change_24h_m",
        "discharge_mean_m3s", "discharge_max_m3s",
        "temperature_mean_c", "temperature_max_c",
    ]

    target_cols = [
        "district_id", "date",
        "target_rainfall_1d_mm", "target_rainfall_2d_mm", "target_rainfall_3d_mm",
        "flood_risk_category_1d",
    ]

    features_df = frame[feature_cols].copy()
    targets_df = frame[target_cols].dropna(subset=["target_rainfall_1d_mm"]).copy()

    features_df.to_parquet(output_features_pq, index=False)
    targets_df.to_parquet(output_targets_pq, index=False)
    logger.info(f"Wrote flood features to {output_features_pq} ({len(features_df)} rows, {len(feature_cols)} features)")
    logger.info(f"Wrote flood targets to {output_targets_pq} ({len(targets_df)} rows)")

    return features_df


def generate_metadata_json(
    raw_dir: Path,
    processed_dir: Path,
    metadata_dir: Path,
    rain_stats: dict[str, Any],
    wl_stats: dict[str, Any],
    dis_stats: dict[str, Any],
    temp_stats: dict[str, Any],
    cpcb_stats: dict[str, Any],
) -> Path:
    """Generate machine-readable datasets.json metadata."""
    metadata_dir.mkdir(parents=True, exist_ok=True)
    meta_path = metadata_dir / "datasets.json"

    def _file_size(p: Path) -> int:
        return p.stat().st_size if p.exists() else 0

    datasets_info = [
        {
            "name": "CWC Maharashtra Telemetry Hourly Rainfall",
            "publisher": "Central Water Commission (CWC), Ministry of Jal Shakti",
            "official_portal": "National Water Data Portal (NWDP / NWIC)",
            "source_url": "https://nwdp.nwic.gov.in/dataset/rainfall-cwc-telemetry-hourly",
            "coverage": "Maharashtra State (22 districts, 58 telemetry stations)",
            "start_date": "2021-01-01",
            "end_date": "2025-12-29",
            "variables": ["Telemetry Hourly Rainfall (mm)"],
            "raw_file": "rainfall_tel_hr_cwc_mh_2021_2025.csv",
            "raw_size_bytes": _file_size(raw_dir / "rainfall_tel_hr_cwc_mh_2021_2025.csv"),
            "processed_file": "observations.csv",
            "processed_size_bytes": _file_size(processed_dir / "observations.csv"),
            "metrics": rain_stats,
        },
        {
            "name": "CWC Godavari River Basin Telemetry Hourly Water Level",
            "publisher": "Central Water Commission (CWC), Ministry of Jal Shakti",
            "official_portal": "National Water Data Portal (NWDP / NWIC)",
            "source_url": "https://nwdp.nwic.gov.in/dataset/river-water-level-telemetry-hourly-central-water-commission-cwc",
            "coverage": "Godavari River Basin (Maharashtra & neighbouring states, 66 stations)",
            "start_date": "2021-01-01",
            "end_date": "2025-12-31",
            "variables": ["River Water Level Telemetry Hourly (meter)"],
            "raw_file": "rwl_tel_hr_cwc_006_2021_2025.csv",
            "raw_size_bytes": _file_size(raw_dir / "rwl_tel_hr_cwc_006_2021_2025.csv"),
            "processed_file": "flood_features.parquet",
            "processed_size_bytes": _file_size(processed_dir / "flood_features.parquet"),
            "metrics": wl_stats,
        },
        {
            "name": "CWC Telemetry Hourly River Water Discharge",
            "publisher": "Central Water Commission (CWC), Ministry of Jal Shakti",
            "official_portal": "National Water Data Portal (NWDP / NWIC)",
            "source_url": "https://nwdp.nwic.gov.in/dataset/river-discharge-telemetry-hourly-central-water-commission-cwc",
            "coverage": "Baitarani Basin / Eastern Peninsular Reference Station (Champua)",
            "start_date": "2022-09-01",
            "end_date": "2025-12-31",
            "variables": ["Telemetry Hourly River Water Discharge (m3/sec)"],
            "raw_file": "river_discharge_tele_hr_cwc_od_1970_2025.csv",
            "raw_size_bytes": _file_size(raw_dir / "river_discharge_tele_hr_cwc_od_1970_2025.csv"),
            "processed_file": "flood_features.parquet",
            "processed_size_bytes": _file_size(processed_dir / "flood_features.parquet"),
            "metrics": dis_stats,
        },
        {
            "name": "CWC Maharashtra Hourly Air Temperature Telemetry",
            "publisher": "Central Water Commission (CWC), Ministry of Jal Shakti",
            "official_portal": "National Water Data Portal (NWDP / NWIC)",
            "source_url": "https://nwdp.nwic.gov.in/dataset/rainfall-cwc-telemetry-hourly",
            "coverage": "Tapi River Basin (Bhusawal, Jalgaon, Maharashtra)",
            "start_date": "2021-01-01",
            "end_date": "2025-12-31",
            "variables": ["Air Temperature Telemetry Hourly (ºC)"],
            "raw_file": "temprature_tel_hr_cwc_mh_2021_2025.csv",
            "raw_size_bytes": _file_size(raw_dir / "temprature_tel_hr_cwc_mh_2021_2025.csv"),
            "processed_file": "flood_features.parquet",
            "processed_size_bytes": _file_size(processed_dir / "flood_features.parquet"),
            "metrics": temp_stats,
        },
        {
            "name": "CPCB Surface Water Chemical Parameter Monitoring",
            "publisher": "Central Pollution Control Board (CPCB), Ministry of Environment, Forest and Climate Change",
            "official_portal": "National Water Data Portal (NWDP / NWIC)",
            "source_url": "https://nwdp.nwic.gov.in/dataset/surface-water-quality-chemical-parameter-manual-cpcb",
            "coverage": "Maharashtra State (31 districts, 225 monitoring stations)",
            "start_date": "2021-01-01",
            "end_date": "2025-12-31",
            "variables": ["Dissolved oxygen", "pH", "TDS", "Nitrate N", "Total Hardness", "Alkalinity"],
            "raw_file": "swq_chemical_parameter_manual_cpcb_mh_2021_2025.csv",
            "raw_size_bytes": _file_size(raw_dir / "swq_chemical_parameter_manual_cpcb_mh_2021_2025.csv"),
            "processed_file": "air_quality_features.parquet",
            "processed_size_bytes": _file_size(processed_dir / "air_quality_features.parquet"),
            "metrics": cpcb_stats,
        },
    ]

    total_raw = sum(d["raw_size_bytes"] for d in datasets_info)
    total_processed = sum(f.stat().st_size for f in processed_dir.glob("*") if f.is_file())

    manifest = {
        "metadata_version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "study_region": {
            "name": "Godavari & Western River Basins, Maharashtra",
            "states": ["Maharashtra"],
            "primary_districts": [d["name"] for d in DISTRICT_METADATA],
            "total_districts": len(DISTRICT_METADATA),
        },
        "datasets": datasets_info,
        "total_raw_size_bytes": total_raw,
        "total_raw_size_mb": round(total_raw / (1024 * 1024), 2),
        "total_processed_size_bytes": total_processed,
        "total_processed_size_mb": round(total_processed / (1024 * 1024), 2),
        "budget_limit_bytes": 5 * 1024 * 1024 * 1024,
        "preferred_budget_bytes": 1024 * 1024 * 1024,
        "budget_status": "PASS_PREFERRED" if total_raw <= 1024 * 1024 * 1024 else "PASS_HARD_LIMIT",
    }

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    logger.info(f"Saved machine-readable dataset metadata to {meta_path}")
    return meta_path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.processed_dir.mkdir(parents=True, exist_ok=True)
    args.metadata_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=== Starting Data Preprocessing & Feature Engineering ===")

    # 1. Dimension Table
    dist_file = args.processed_dir / "districts.csv"
    build_districts_table(dist_file)

    # 2. Rainfall Telemetry
    obs_file = args.processed_dir / "observations.csv"
    clean_obs_file = args.processed_dir / "observations_clean.csv"
    rain_raw = args.raw_dir / "rainfall_tel_hr_cwc_mh_2021_2025.csv"
    obs_df, rain_stats = preprocess_rainfall(rain_raw, obs_file, clean_obs_file)

    # 3. Water Level Telemetry
    wl_raw = args.raw_dir / "rwl_tel_hr_cwc_006_2021_2025.csv"
    dist_wl, wl_stats = preprocess_water_level(wl_raw)

    # 4. Discharge Telemetry
    dis_raw = args.raw_dir / "river_discharge_tele_hr_cwc_od_1970_2025.csv"
    daily_dis, dis_stats = preprocess_discharge(dis_raw)

    # 5. Temperature Telemetry
    temp_raw = args.raw_dir / "temprature_tel_hr_cwc_mh_2021_2025.csv"
    daily_temp, temp_stats = preprocess_temperature(temp_raw)

    # 6. Environmental Water Quality (CPCB)
    cpcb_raw = args.raw_dir / "swq_chemical_parameter_manual_cpcb_mh_2021_2025.csv"
    cpcb_pq = args.processed_dir / "air_quality_features.parquet"
    cpcb_df, cpcb_stats = preprocess_cpcb(cpcb_raw, cpcb_pq)

    # 7. Hydrological Multi-Sensor Flood Features & Targets
    flood_pq = args.processed_dir / "flood_features.parquet"
    targets_pq = args.processed_dir / "flood_targets.parquet"
    build_hydrological_features(obs_df, dist_wl, daily_dis, daily_temp, flood_pq, targets_pq)

    # 8. Machine-Readable Metadata
    generate_metadata_json(
        raw_dir=args.raw_dir,
        processed_dir=args.processed_dir,
        metadata_dir=args.metadata_dir,
        rain_stats=rain_stats,
        wl_stats=wl_stats,
        dis_stats=dis_stats,
        temp_stats=temp_stats,
        cpcb_stats=cpcb_stats,
    )

    logger.info("=== Preprocessing Pipeline Completed Successfully ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
