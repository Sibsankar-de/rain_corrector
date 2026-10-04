#!/usr/bin/env python3
"""Inference script for district rainfall and hazard level forecasting.

Uses the trained model artifact to produce single- or multi-district forecasts
with uncertainty intervals (P10, P50, P90) and severity classification.

Usage:
    python scripts/predict.py
    python scripts/predict.py --districts MH-NAS,MH-JAL,MH-KOL --date 2025-07-15
    python scripts/predict.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
ML_SRC = REPO_ROOT / "ml" / "src"
if str(ML_SRC) not in sys.path:
    sys.path.insert(0, str(ML_SRC))

from rainml.data.loaders import attach_coordinates, load_districts, load_observations  # noqa: E402
from rainml.inference.predictor import DistrictHistory, RainfallPredictor  # noqa: E402
from rainml.models.registry import list_versions  # noqa: E402

DEFAULT_OBSERVATIONS = REPO_ROOT / "data" / "processed" / "observations.csv"
DEFAULT_DISTRICTS = REPO_ROOT / "data" / "processed" / "districts.csv"
DEFAULT_ARTIFACTS = REPO_ROOT / "ml" / "artifacts"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Issue rainfall and hazard forecasts for districts.")
    parser.add_argument("--observations", default=str(DEFAULT_OBSERVATIONS))
    parser.add_argument("--districts-file", default=str(DEFAULT_DISTRICTS))
    parser.add_argument("--artifact-root", default=str(DEFAULT_ARTIFACTS))
    parser.add_argument("--version", default=None, help="Model version. Defaults to latest.")
    parser.add_argument("--districts", default=None, help="Comma-separated district codes (e.g. MH-NAS,MH-JAL).")
    parser.add_argument("--date", default=None, help="Issue date YYYY-MM-DD. Defaults to latest in dataset.")
    parser.add_argument("--horizon-days", type=int, default=1, help="Forecast lead time in days.")
    parser.add_argument("--json", action="store_true", help="Print predictions as JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    artifact_root = Path(args.artifact_root)
    versions = list_versions(artifact_root)
    if not versions:
        print("No trained model versions found. Run: python scripts/train.py", file=sys.stderr)
        return 1

    version = args.version or versions[-1]
    predictor = RainfallPredictor.from_artifact_root(artifact_root, version)

    obs_df = load_observations(args.observations)
    dist_df = load_districts(args.districts_file)
    obs_df["dt"] = pd.to_datetime(obs_df["observed_at"]).dt.tz_localize(None)

    if args.date:
        issue_dt = pd.to_datetime(args.date).normalize()
    else:
        issue_dt = obs_df["dt"].max().normalize()

    issue_date = issue_dt.date()

    # Filter requested districts
    target_districts = dist_df.copy()
    if args.districts:
        codes = [c.strip().upper() for c in args.districts.split(",")]
        target_districts = target_districts[target_districts["code"].isin(codes)]
        if target_districts.empty:
            print(f"Error: None of requested districts {codes} found in {args.districts_file}", file=sys.stderr)
            return 1

    # Build district histories for inference
    histories: list[DistrictHistory] = []
    start_dt = issue_dt - timedelta(days=60)
    history_obs = obs_df[(obs_df["dt"] >= start_dt) & (obs_df["dt"] < issue_dt)]

    for _, dist in target_districts.iterrows():
        code = str(dist["code"])
        sub = history_obs[history_obs["district_id"] == code]
        daily_rainfall = {row["dt"].date(): float(row["rainfall_mm"]) for _, row in sub.iterrows()}

        histories.append(
            DistrictHistory(
                district_id=code,
                latitude=float(dist["centroid_lat"]),
                longitude=float(dist["centroid_lon"]),
                daily_rainfall_mm=daily_rainfall,
            )
        )

    predictions = predictor.predict_districts(histories, issue_date=issue_date, horizon_days=args.horizon_days)

    if args.json:
        out = {
            "model_version": version,
            "issue_date": issue_date.isoformat(),
            "target_date": (issue_date + timedelta(days=args.horizon_days)).isoformat(),
            "horizon_days": args.horizon_days,
            "forecasts": [p.as_dict() for p in predictions],
        }
        print(json.dumps(out, indent=2))
    else:
        target_date = issue_date + timedelta(days=args.horizon_days)
        print("=" * 72)
        print(f"RAINFALL & HAZARD FORECAST: {predictor.metadata.get('model_name', 'model')} ({version})")
        print(f"Issue Date:  {issue_date} -> Target Date: {target_date} (+{args.horizon_days}d)")
        print("=" * 72)
        print(f"{'District':<12} {'Forecast (mm)':<15} {'Interval (P10 - P90)':<24} {'Severity':<12}")
        print("-" * 72)
        for p in predictions:
            dist_name = target_districts[target_districts["code"] == p.district_id]["name"].iloc[0] if (target_districts["code"] == p.district_id).any() else p.district_id
            interval_str = f"[{p.lower_bound_mm:.1f} .. {p.upper_bound_mm:.1f}]"
            print(f"{dist_name:<12} {p.predicted_rainfall_mm:<15.2f} {interval_str:<24} {p.severity.upper():<12}")
        print("=" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
