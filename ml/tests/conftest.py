"""Shared fixtures for the ML test suite."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT.parent / "data" / "processed"
ARTIFACT_ROOT = Path(__file__).resolve().parents[1] / "artifacts"

if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))


@pytest.fixture
def demo_observations_path() -> Path:
    path = DATA_DIR / "observations.csv"
    if not path.exists():
        pytest.skip("no demo dataset; run scripts/generate_demo_dataset.py first")
    return path


@pytest.fixture
def demo_districts_path() -> Path:
    path = DATA_DIR / "districts.csv"
    if not path.exists():
        pytest.skip("no demo district file; run scripts/generate_demo_dataset.py first")
    return path


@pytest.fixture
def artifact_root() -> Path:
    if not ARTIFACT_ROOT.exists() or not any(ARTIFACT_ROOT.iterdir()):
        pytest.skip("no model artifacts; run scripts/run_training.py first")
    return ARTIFACT_ROOT


@pytest.fixture
def trained_artifact(artifact_root: Path) -> Path:
    versions = sorted(p for p in artifact_root.iterdir() if (p / "metadata.json").exists())
    if not versions:
        pytest.skip("no trained model version available")
    return versions[-1]


@pytest.fixture
def synthetic_observations() -> pd.DataFrame:
    """Monsoon-like daily rainfall for several districts."""
    rng = np.random.default_rng(20240101)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    days = 400
    rows: list[dict] = []
    # Coordinates are deliberately omitted: the loader is responsible for
    # attaching them, and a fixture that already had them would skip that path.
    for district in range(5):
        # A regional state variable plus district noise gives spatial coherence.
        state = 0.0
        for day in range(days):
            doy = (start + timedelta(days=day)).timetuple().tm_yday
            seasonal = np.exp(-0.5 * ((doy - 200) / 45.0) ** 2)
            state = 0.7 * state + float(rng.normal(0, 0.4))
            signal = max(seasonal * (1 + 0.5 * state) + 0.1, 0.05)
            amount = float(rng.gamma(shape=signal * 0.6, scale=6.0 / max(signal, 0.2)))
            rows.append(
                {
                    "district_id": district + 1,
                    "observed_at": start + timedelta(days=day),
                    "rainfall_mm": round(max(amount, 0.0), 2),
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def synthetic_districts() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": index + 1,
                "code": f"SYN-{index}",
                "name": f"Synthetic {index}",
                "region": "Synthetic",
                "centroid_lat": 19.0 + index,
                "centroid_lon": 72.0 + index,
                "population": 1_000_000,
            }
            for index in range(5)
        ]
    )


@pytest.fixture
def supervised_frame(synthetic_observations, synthetic_districts) -> pd.DataFrame:
    from rainml.data.cleaning import clean_observations
    from rainml.evaluation.metrics import add_target_month
    from rainml.features.engineering import build_training_frame

    cleaned, _ = clean_observations(synthetic_observations)
    return add_target_month(build_training_frame(cleaned))
