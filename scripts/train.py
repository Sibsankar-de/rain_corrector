#!/usr/bin/env python3
"""Model training CLI wrapper.

Trains baseline and candidate models on real environmental and hydrological datasets,
evaluates on a strictly chronological split (preventing future leakage), computes
continuous (MAE, RMSE, NSE) and categorical (POD, FAR, CSI) metrics, and saves versioned
artifacts.

Usage:
    python scripts/train.py
    python scripts/train.py --promote
    python scripts/train.py --observations data/processed/observations.csv --districts data/processed/districts.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from run_training import main as run_training_main  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train rainfall & flood forecasting models.")
    parser.add_argument("--observations", default=str(REPO_ROOT / "data" / "processed" / "observations.csv"))
    parser.add_argument("--districts", default=str(REPO_ROOT / "data" / "processed" / "districts.csv"))
    parser.add_argument("--artifact-root", default=str(REPO_ROOT / "ml" / "artifacts"))
    parser.add_argument("--config", default=None)
    parser.add_argument("--version", default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--promote", action="store_true", default=False)
    parser.add_argument("--no-register", dest="register", action="store_false", default=True)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cmd_args = [
        "--observations", args.observations,
        "--districts", args.districts,
        "--artifact-root", args.artifact_root,
    ]
    if args.config:
        cmd_args.extend(["--config", args.config])
    if args.version:
        cmd_args.extend(["--version", args.version])
    if args.seed is not None:
        cmd_args.extend(["--seed", str(args.seed)])
    if args.promote:
        cmd_args.append("--promote")
    if not args.register:
        cmd_args.append("--no-register")
    if args.json:
        cmd_args.append("--json")

    return run_training_main(cmd_args)


if __name__ == "__main__":
    raise SystemExit(main())
