#!/usr/bin/env python3
"""Model evaluation script.

Evaluates trained rainfall forecasting artifacts on real observation holdout sets,
reporting continuous performance (MAE, RMSE, Bias, NSE) and categorical event
detection capability (POD, FAR, CSI, Brier score) across hazard thresholds.

Usage:
    python scripts/evaluate.py
    python scripts/evaluate.py --version v005
    python scripts/evaluate.py --artifact ml/artifacts/v005 --thresholds 15.0 35.0 65.0
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
ML_SRC = REPO_ROOT / "ml" / "src"
if str(ML_SRC) not in sys.path:
    sys.path.insert(0, str(ML_SRC))

from rainml.data.loaders import attach_coordinates, load_districts, load_observations  # noqa: E402
from rainml.evaluation.metrics import (  # noqa: E402
    bias,
    brier_score,
    categorical_scores,
    mae,
    nash_sutcliffe_efficiency,
    rmse,
)
from rainml.features.engineering import FEATURE_COLUMNS, TARGET_COLUMN, build_training_frame  # noqa: E402
from rainml.inference.predictor import RainfallPredictor  # noqa: E402

DEFAULT_OBSERVATIONS = REPO_ROOT / "data" / "processed" / "observations.csv"
DEFAULT_DISTRICTS = REPO_ROOT / "data" / "processed" / "districts.csv"
DEFAULT_ARTIFACTS = REPO_ROOT / "ml" / "artifacts"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate forecasting model performance.")
    parser.add_argument("--observations", default=str(DEFAULT_OBSERVATIONS))
    parser.add_argument("--districts", default=str(DEFAULT_DISTRICTS))
    parser.add_argument("--artifact-root", default=str(DEFAULT_ARTIFACTS))
    parser.add_argument("--version", default=None, help="Model version (e.g. v005). Defaults to newest.")
    parser.add_argument("--artifact", default=None, help="Direct path to artifact directory.")
    parser.add_argument(
        "--thresholds",
        nargs="+",
        type=float,
        default=[15.0, 35.0, 65.0],
        help="Rainfall hazard event thresholds in mm.",
    )
    parser.add_argument("--test-ratio", type=float, default=0.2, help="Chronological holdout ratio.")
    parser.add_argument("--json", action="store_true", help="Print output as JSON.")
    return parser.parse_args(argv)


def find_latest_version(artifact_root: Path) -> str:
    candidates = sorted([d.name for d in artifact_root.iterdir() if d.is_dir() and d.name.startswith("v")])
    if not candidates:
        raise FileNotFoundError(f"No versioned model artifacts found in {artifact_root}")
    return candidates[-1]


def evaluate_model(
    predictions: np.ndarray,
    observed: np.ndarray,
    thresholds: list[float],
) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "continuous": {
            "samples": int(len(observed)),
            "mae_mm": round(mae(predictions, observed), 4),
            "rmse_mm": round(rmse(predictions, observed), 4),
            "bias_mm": round(bias(predictions, observed), 4),
            "nse": round(nash_sutcliffe_efficiency(predictions, observed) or 0.0, 4),
        },
        "categorical": {},
    }

    for thr in thresholds:
        cat = categorical_scores(predictions, observed, threshold_mm=thr)
        brier = brier_score(predictions, observed, threshold_mm=thr)
        metrics["categorical"][f"{thr}mm"] = {
            "threshold_mm": thr,
            "pod": cat.get("pod"),
            "far": cat.get("far"),
            "csi": cat.get("csi"),
            "brier_score": round(brier, 6),
            "hits": cat.get("hits"),
            "false_alarms": cat.get("false_alarms"),
            "misses": cat.get("misses"),
            "correct_negatives": cat.get("correct_negatives"),
        }
    return metrics


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    artifact_root = Path(args.artifact_root)

    if args.artifact:
        art_path = Path(args.artifact)
        version = art_path.name
        root = art_path.parent
    else:
        version = args.version or find_latest_version(artifact_root)
        root = artifact_root

    predictor = RainfallPredictor.from_artifact_root(root, version)

    obs = load_observations(args.observations)
    dist = load_districts(args.districts)
    frame = attach_coordinates(obs, dist)
    supervised = build_training_frame(frame, horizon_days=1)

    # Chronological holdout split
    ordered = supervised.sort_values("target_date").reset_index(drop=True)
    test_size = max(int(len(ordered) * args.test_ratio), 1)
    test_frame = ordered.iloc[-test_size:].copy()

    feature_cols = [c for c in predictor.features if c in test_frame.columns]
    X_test = test_frame[feature_cols]
    y_test = test_frame[TARGET_COLUMN].to_numpy(dtype=float)

    preds_df = predictor.predict_frame(X_test)
    preds = preds_df["predicted_rainfall_mm"].to_numpy()
    metrics = evaluate_model(preds, y_test, args.thresholds)

    report = {
        "model_name": predictor.metadata.get("model_name", "district_daily_rainfall"),
        "version": predictor.version,
        "test_period": {
            "start": str(test_frame["target_date"].min())[:10],
            "end": str(test_frame["target_date"].max())[:10],
            "records": len(test_frame),
            "districts": int(test_frame["district_id"].nunique()),
        },
        "metrics": metrics,
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("=" * 60)
        print(f"EVALUATION REPORT: {report['model_name']} ({report['version']})")
        print("=" * 60)
        print(f"Test Period:   {report['test_period']['start']} to {report['test_period']['end']}")
        print(f"Test Records:  {report['test_period']['records']:,} ({report['test_period']['districts']} districts)")
        print("\n[Continuous Error Metrics]")
        print(f"  MAE:         {metrics['continuous']['mae_mm']} mm")
        print(f"  RMSE:        {metrics['continuous']['rmse_mm']} mm")
        print(f"  Bias:        {metrics['continuous']['bias_mm']} mm")
        print(f"  NSE:         {metrics['continuous']['nse']}")
        print("\n[Hazard Event Detection Metrics]")
        for k, v in metrics["categorical"].items():
            print(f"  Threshold >= {v['threshold_mm']} mm:")
            print(f"    POD (Detection Rate): {v['pod']}")
            print(f"    FAR (False Alarm):    {v['far']}")
            print(f"    CSI (Threat Score):   {v['csi']}")
            print(f"    Brier Score:          {v['brier_score']}")
            print(f"    Hits={v['hits']}, FA={v['false_alarms']}, Miss={v['misses']}, CN={v['correct_negatives']}")
        print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
