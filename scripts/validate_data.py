#!/usr/bin/env python3
"""Dataset Validation Script for Authoritative Environmental & Disaster Datasets.

Validates:
- Raw and processed datasets exist and have valid structure
- Enforces dataset size limit: FAIL if total raw size > 5 GB, WARN if > 1 GB
- Reports rows, date ranges, spatial coverage, missing percentages, and disk sizes
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw"
DEFAULT_PROCESSED_DIR = REPO_ROOT / "data" / "processed"
DEFAULT_CONFIG = REPO_ROOT / "data" / "config" / "data_sources.yaml"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate environmental and disaster forecasting datasets.")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="Path to raw data directory")
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR, help="Path to processed directory")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Path to data sources configuration")
    parser.add_argument("--fail-on-missing", action="store_true", help="Fail if processed datasets are not generated yet")
    return parser.parse_args(argv)


def get_dir_size_bytes(directory: Path) -> int:
    if not directory.exists():
        return 0
    return sum(f.stat().st_size for f in directory.rglob("*") if f.is_file() and not f.name.startswith("."))


def validate_cwc_telemetry(
    file_path: Path, value_col: str, date_col: str = "Data Acquisition Time"
) -> dict[str, Any]:
    if not file_path.exists():
        return {"status": "missing", "error": f"File not found: {file_path}"}

    disk_size = file_path.stat().st_size
    try:
        # Sample or full read depending on size
        df = pd.read_csv(file_path, low_memory=False)
    except Exception as exc:
        return {"status": "corrupt", "error": str(exc), "disk_size": disk_size}

    rows = len(df)
    stations = int(df["Station"].nunique()) if "Station" in df.columns else 0
    districts = int(df["District"].nunique()) if "District" in df.columns else 0

    dates = pd.to_datetime(df[date_col], format="%d-%m-%Y %H:%M", errors="coerce")
    min_date = dates.min()
    max_date = dates.max()

    val_series = pd.to_numeric(df[value_col], errors="coerce") if value_col in df.columns else pd.Series(dtype=float)
    # Exclude offline negative telemetry flags (< 0) from valid count
    valid_mask = val_series.notna() & (val_series >= 0)
    missing_pct = float(100.0 * (1.0 - valid_mask.sum() / max(rows, 1)))

    lat_min, lat_max = (float(df["Latitude"].min()), float(df["Latitude"].max())) if "Latitude" in df.columns else (0.0, 0.0)
    lon_min, lon_max = (float(df["Longitude"].min()), float(df["Longitude"].max())) if "Longitude" in df.columns else (0.0, 0.0)

    return {
        "status": "valid",
        "rows": rows,
        "stations": stations,
        "districts": districts,
        "date_range": f"{min_date.strftime('%Y-%m-%d') if pd.notna(min_date) else 'N/A'} to {max_date.strftime('%Y-%m-%d') if pd.notna(max_date) else 'N/A'}",
        "spatial_coverage": f"Lat [{lat_min:.2f}, {lat_max:.2f}], Lon [{lon_min:.2f}, {lon_max:.2f}]",
        "missing_percentage": round(missing_pct, 2),
        "disk_size_mb": round(disk_size / (1024 * 1024), 2),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    print("=" * 70)
    print("DATASET VALIDATION REPORT")
    print("=" * 70)

    total_raw_bytes = get_dir_size_bytes(args.raw_dir)
    total_processed_bytes = get_dir_size_bytes(args.processed_dir)

    total_raw_mb = total_raw_bytes / (1024 * 1024)
    total_raw_gb = total_raw_bytes / (1024 * 1024 * 1024)
    total_processed_mb = total_processed_bytes / (1024 * 1024)

    # 1. Validate Raw Sources
    print("\n[RAW DATASETS - Central Water Commission & CPCB]")
    print("-" * 70)

    cwc_rain_file = args.raw_dir / "rainfall_tel_hr_cwc_mh_2021_2025.csv"
    res_rain = validate_cwc_telemetry(cwc_rain_file, "Telemetry Hourly Rainfall (mm)")
    print("CWC Rainfall (Maharashtra):")
    if res_rain["status"] == "valid":
        print(f"  Rows:               {res_rain['rows']:,}")
        print(f"  Stations:           {res_rain['stations']}")
        print(f"  Districts:          {res_rain['districts']}")
        print(f"  Date range:         {res_rain['date_range']}")
        print(f"  Spatial coverage:   {res_rain['spatial_coverage']}")
        print(f"  Missing percentage: {res_rain['missing_percentage']}%")
        print(f"  Disk size:          {res_rain['disk_size_mb']} MB")
    else:
        print(f"  Status: {res_rain['status']} ({res_rain.get('error')})")

    cwc_wl_file = args.raw_dir / "rwl_tel_hr_cwc_006_2021_2025.csv"
    res_wl = validate_cwc_telemetry(cwc_wl_file, "River Water Level Telemetry Hourly (meter)")
    print("\nCWC Water Level (Godavari Basin):")
    if res_wl["status"] == "valid":
        print(f"  Rows:               {res_wl['rows']:,}")
        print(f"  Stations:           {res_wl['stations']}")
        print(f"  Districts:          {res_wl['districts']}")
        print(f"  Date range:         {res_wl['date_range']}")
        print(f"  Spatial coverage:   {res_wl['spatial_coverage']}")
        print(f"  Missing percentage: {res_wl['missing_percentage']}%")
        print(f"  Disk size:          {res_wl['disk_size_mb']} MB")
    else:
        print(f"  Status: {res_wl['status']} ({res_wl.get('error')})")

    cwc_dis_file = args.raw_dir / "river_discharge_tele_hr_cwc_od_1970_2025.csv"
    res_dis = validate_cwc_telemetry(cwc_dis_file, "Telemetry Hourly River Water Discharge (m3/sec)")
    print("\nCWC River Discharge (Odisha / Reference):")
    if res_dis["status"] == "valid":
        print(f"  Rows:               {res_dis['rows']:,}")
        print(f"  Stations:           {res_dis['stations']}")
        print(f"  Date range:         {res_dis['date_range']}")
        print(f"  Spatial coverage:   {res_dis['spatial_coverage']}")
        print(f"  Missing percentage: {res_dis['missing_percentage']}%")
        print(f"  Disk size:          {res_dis['disk_size_mb']} MB")
    else:
        print(f"  Status: {res_dis['status']} ({res_dis.get('error')})")

    cwc_temp_file = args.raw_dir / "temprature_tel_hr_cwc_mh_2021_2025.csv"
    res_temp = validate_cwc_telemetry(cwc_temp_file, "Air Temperature Telemetry Hourly (ºC)")
    print("\nCWC Temperature (Maharashtra):")
    if res_temp["status"] == "valid":
        print(f"  Rows:               {res_temp['rows']:,}")
        print(f"  Stations:           {res_temp['stations']}")
        print(f"  Date range:         {res_temp['date_range']}")
        print(f"  Missing percentage: {res_temp['missing_percentage']}%")
        print(f"  Disk size:          {res_temp['disk_size_mb']} MB")
    else:
        print(f"  Status: {res_temp['status']} ({res_temp.get('error')})")

    cpcb_file = args.raw_dir / "swq_chemical_parameter_manual_cpcb_mh_2021_2025.csv"
    res_cpcb = validate_cwc_telemetry(cpcb_file, "Dissolved oxygen (mg/L)")
    print("\nCPCB Surface Water Quality (Chemical Parameters):")
    if res_cpcb["status"] == "valid":
        print(f"  Rows:               {res_cpcb['rows']:,}")
        print(f"  Stations:           {res_cpcb['stations']}")
        print(f"  Date range:         {res_cpcb['date_range']}")
        print(f"  Missing percentage: {res_cpcb['missing_percentage']}%")
        print(f"  Disk size:          {res_cpcb['disk_size_mb']} MB")
    else:
        print(f"  Status: {res_cpcb['status']} ({res_cpcb.get('error')})")

    # 2. Validate Processed Datasets
    print("\n" + "=" * 70)
    print("[PROCESSED DATASETS]")
    print("-" * 70)

    obs_file = args.processed_dir / "observations.csv"
    dist_file = args.processed_dir / "districts.csv"
    flood_pq = args.processed_dir / "flood_features.parquet"
    air_pq = args.processed_dir / "air_quality_features.parquet"

    processed_status = True

    if obs_file.exists():
        df_obs = pd.read_csv(obs_file)
        dates = pd.to_datetime(df_obs["observed_at"], utc=True)
        print(f"Observations (observations.csv):")
        print(f"  Rows:             {len(df_obs):,}")
        print(f"  Districts:        {df_obs['district_id'].nunique()}")
        print(f"  Date range:       {dates.min().strftime('%Y-%m-%d')} to {dates.max().strftime('%Y-%m-%d')}")
        print(f"  Mean rainfall:    {df_obs['rainfall_mm'].mean():.2f} mm")
        print(f"  Max daily rain:   {df_obs['rainfall_mm'].max():.2f} mm")
        print(f"  Disk size:        {obs_file.stat().st_size / (1024 * 1024):.2f} MB")
    else:
        print(f"Observations (observations.csv): NOT FOUND (Run python scripts/preprocess_data.py)")
        processed_status = False

    if dist_file.exists():
        df_dist = pd.read_csv(dist_file)
        print(f"\nDistricts dimension (districts.csv):")
        print(f"  Districts count:  {len(df_dist)}")
        print(f"  Regions:          {df_dist['region'].unique().tolist()}")
        print(f"  Disk size:        {dist_file.stat().st_size / 1024:.2f} KB")
    else:
        print(f"\nDistricts dimension: NOT FOUND")
        processed_status = False

    if flood_pq.exists():
        try:
            df_flood = pd.read_parquet(flood_pq)
            print(f"\nHydrological / Flood Features ({flood_pq.name}):")
            print(f"  Rows:             {len(df_flood):,}")
            print(f"  Columns:          {len(df_flood.columns)}")
            print(f"  Feature set:      {list(df_flood.columns)[:6]}...")
            print(f"  Disk size:        {flood_pq.stat().st_size / (1024 * 1024):.2f} MB")
        except Exception as exc:
            print(f"\nHydrological / Flood Features: read error {exc}")
    else:
        print(f"\nHydrological / Flood Features ({flood_pq.name}): NOT GENERATED YET")

    if air_pq.exists():
        try:
            df_air = pd.read_parquet(air_pq)
            print(f"\nEnvironmental Quality Features ({air_pq.name}):")
            print(f"  Rows:             {len(df_air):,}")
            print(f"  Columns:          {len(df_air.columns)}")
            print(f"  Parameters:       {list(df_air.columns)[:5]}...")
            print(f"  Disk size:        {air_pq.stat().st_size / 1024:.2f} KB")
        except Exception as exc:
            print(f"\nEnvironmental Quality Features: read error {exc}")

    # Storage Budget Checks
    print("\n" + "=" * 70)
    print("STORAGE SUMMARY & BUDGET ENFORCEMENT")
    print("-" * 70)
    print(f"Total raw size:       {total_raw_mb:.2f} MB ({total_raw_gb:.3f} GB)")
    print(f"Total processed size: {total_processed_mb:.2f} MB")
    print(f"Total combined size:  {(total_raw_mb + total_processed_mb):.2f} MB")

    if total_raw_gb > 5.0:
        print(f"\n[CRITICAL ERROR] Total raw size ({total_raw_gb:.2f} GB) EXCEEDS hard maximum of 5.0 GB!", file=sys.stderr)
        return 1

    if total_raw_gb > 1.0:
        print(f"\n[WARNING] Total raw size ({total_raw_gb:.2f} GB) exceeds preferred target of 1.0 GB (within 5.0 GB max).")
    else:
        print(f"\n[SUCCESS] Total raw size ({total_raw_mb:.2f} MB) satisfies the preferred <= 1.0 GB target.")

    if args.fail_on_missing and not processed_status:
        print("\n[ERROR] Processed datasets are missing. Run: python scripts/preprocess_data.py", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
