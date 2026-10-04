"""Unit and integration tests for real government datasets and pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from rainml.data.loaders import attach_coordinates, load_districts, load_observations
from rainml.features.engineering import FEATURE_COLUMNS, TARGET_COLUMN, assert_no_leakage, build_training_frame
from rainml.inference.predictor import RainfallPredictor
from rainml.models.registry import list_versions

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
METADATA_DIR = REPO_ROOT / "data" / "metadata"
ARTIFACTS_DIR = REPO_ROOT / "ml" / "artifacts"


class TestDatasetStorageBudget:
    """Enforces strict dataset size constraints: preferred <= 1 GB, hard limit <= 5 GB."""

    def test_raw_dataset_exists(self) -> None:
        assert RAW_DIR.exists(), f"Raw data directory not found: {RAW_DIR}"
        raw_files = list(RAW_DIR.glob("*.csv"))
        assert len(raw_files) >= 5, f"Expected at least 5 raw CSVs, found {len(raw_files)}"

    def test_raw_dataset_size_within_budget(self) -> None:
        total_raw_bytes = sum(
            f.stat().st_size for f in RAW_DIR.rglob("*") if f.is_file() and not f.name.startswith(".")
        )
        total_raw_gb = total_raw_bytes / (1024 ** 3)
        total_raw_mb = total_raw_bytes / (1024 ** 2)

        # Hard budget constraint
        assert total_raw_gb <= 5.0, f"Raw dataset ({total_raw_gb:.2f} GB) exceeds hard limit of 5.0 GB"
        # Preferred budget target
        assert total_raw_gb <= 1.0, f"Raw dataset ({total_raw_mb:.1f} MB) exceeds preferred target of 1.0 GB"

    def test_processed_dataset_size_is_compact(self) -> None:
        total_processed_bytes = sum(
            f.stat().st_size for f in PROCESSED_DIR.rglob("*") if f.is_file() and not f.name.startswith(".")
        )
        total_processed_mb = total_processed_bytes / (1024 ** 2)
        assert total_processed_mb < 50.0, f"Processed dataset ({total_processed_mb:.2f} MB) unexpectedly large"


class TestDataQualityAndQC:
    """Verifies rigorous data quality control on authoritative telemetry."""

    def test_observations_no_negatives_and_valid_ranges(self) -> None:
        obs_file = PROCESSED_DIR / "observations.csv"
        assert obs_file.exists()
        df = pd.read_csv(obs_file)

        assert (df["rainfall_mm"] >= 0.0).all(), "Rainfall contains negative values"
        assert df["district_id"].nunique() >= 20, "Expected at least 20 districts"
        assert df["lat"].between(15.0, 25.0).all(), "Latitude outside Maharashtra region"
        assert df["lon"].between(72.0, 82.0).all(), "Longitude outside Maharashtra region"

    def test_districts_dimension_complete(self) -> None:
        dist_file = PROCESSED_DIR / "districts.csv"
        assert dist_file.exists()
        df = pd.read_csv(dist_file)

        assert len(df) >= 22
        assert set(["id", "code", "name", "region", "centroid_lat", "centroid_lon", "population"]).issubset(df.columns)
        assert (df["region"] == "Maharashtra").all()

    def test_hydrological_flood_features_schema(self) -> None:
        flood_pq = PROCESSED_DIR / "flood_features.parquet"
        targets_pq = PROCESSED_DIR / "flood_targets.parquet"
        assert flood_pq.exists()
        assert targets_pq.exists()

        df_flood = pd.read_parquet(flood_pq)
        df_targets = pd.read_parquet(targets_pq)

        expected_cols = [
            "district_id", "date", "rainfall_mm",
            "rain_last_1d_mm", "rain_last_3d_mm", "rain_last_7d_mm",
            "antecedent_rain_24h_mm", "dry_streak_days",
            "river_water_level_mean_m", "river_water_level_change_24h_m",
            "discharge_mean_m3s", "temperature_mean_c",
        ]
        assert set(expected_cols).issubset(df_flood.columns)
        assert len(df_flood) == len(pd.read_csv(PROCESSED_DIR / "observations.csv"))
        assert "target_rainfall_1d_mm" in df_targets.columns
        assert df_targets["target_rainfall_1d_mm"].notna().all()

    def test_environmental_features_schema(self) -> None:
        air_pq = PROCESSED_DIR / "air_quality_features.parquet"
        assert air_pq.exists()
        df_air = pd.read_parquet(air_pq)

        assert set(["timestamp", "station_id", "parameter", "value", "unit", "source"]).issubset(df_air.columns)
        assert len(df_air) > 1000
        assert (df_air["value"] >= 0.0).all()


class TestRealDataFeatureEngineering:
    """Verifies that features engineered on real observations satisfy zero-leakage contracts."""

    def test_zero_leakage_assertion_on_real_observations(self) -> None:
        obs = load_observations(PROCESSED_DIR / "observations.csv")
        dist = load_districts(PROCESSED_DIR / "districts.csv")
        frame = attach_coordinates(obs, dist)
        tf = build_training_frame(frame, horizon_days=1)

        assert_no_leakage(tf)
        assert len(tf) > 10000

    def test_antecedent_rain_strictly_precedes_target(self) -> None:
        obs = load_observations(PROCESSED_DIR / "observations.csv")
        dist = load_districts(PROCESSED_DIR / "districts.csv")
        frame = attach_coordinates(obs, dist)
        tf = build_training_frame(frame, horizon_days=1)

        # For any district with rain, target_date is strictly greater than issue_date
        assert (tf["target_date"] > tf["issue_date"]).all()
        assert (tf["target_date"] - tf["issue_date"] == pd.Timedelta(days=1)).all()


class TestModelTrainingAndInference:
    """Verifies model loading and inference on real test samples."""

    def test_latest_artifact_predicts_valid_intervals(self) -> None:
        versions = list_versions(ARTIFACTS_DIR)
        assert len(versions) > 0, "No model artifact version found"
        latest = versions[-1]

        predictor = RainfallPredictor.from_artifact_root(ARTIFACTS_DIR, latest)
        obs = load_observations(PROCESSED_DIR / "observations.csv")
        dist = load_districts(PROCESSED_DIR / "districts.csv")
        frame = attach_coordinates(obs, dist)
        tf = build_training_frame(frame, horizon_days=1).tail(100)

        feature_cols = [c for c in predictor.features if c in tf.columns]
        output = predictor.predict_frame(tf[feature_cols])

        assert (output["predicted_rainfall_mm"] >= 0.0).all()
        assert (output["lower_bound_mm"] <= output["predicted_rainfall_mm"] + 1e-5).all()
        assert (output["upper_bound_mm"] >= output["predicted_rainfall_mm"] - 1e-5).all()


class TestMetadataIntegrity:
    """Verifies machine-readable dataset metadata completeness."""

    def test_datasets_json_valid_and_complete(self) -> None:
        meta_file = METADATA_DIR / "datasets.json"
        assert meta_file.exists()
        with open(meta_file, encoding="utf-8") as f:
            data = json.load(f)

        assert "datasets" in data
        assert len(data["datasets"]) >= 5
        assert data["budget_status"] == "PASS_PREFERRED"
        assert data["total_raw_size_mb"] < 1000.0

        for ds in data["datasets"]:
            assert "name" in ds
            assert "publisher" in ds
            assert "source_url" in ds
            assert ds["raw_size_bytes"] > 0
