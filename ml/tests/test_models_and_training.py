"""Baselines, candidate models, artifact registry and the training pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from rainml.data.validation import chronological_split
from rainml.models.baseline import (
    PersistenceRegressor,
    RollingMeanRegressor,
    baseline_estimators,
    make_baseline,
)
from rainml.models.forecasting import CANDIDATES, build_pipeline, make_quantile_pipeline
from rainml.models.registry import (
    build_metadata,
    list_versions,
    load_metadata,
    next_version,
    save_artifact,
    verify_checksum,
)
from rainml.training.configuration import TrainingConfig, load_config, set_global_seed
from rainml.training.trainer import run_training

TARGET = "target_rainfall_mm"
# The supervised fixture has no lat/lon columns; the coordinates are attached
# by the loader before feature engineering, which the fixture bypasses.
TEST_FEATURES = [
    "antecedent_rain_24h_mm",
    "antecedent_rain_72h_mm",
    "rain_last_3d_mm",
    "rain_last_7d_mm",
    "rain_last_30d_mm",
    "doy_sin",
]


@pytest.fixture
def splits(supervised_frame):
    train, valid, test = chronological_split(supervised_frame)
    return train, valid, test


class TestBaselines:
    def test_persistence_repeats_the_previous_day(self, splits) -> None:
        train, _, test = splits
        estimator = make_baseline("persistence")
        estimator.fit(train[["antecedent_rain_24h_mm"]], train[TARGET].to_numpy(float))

        expected = test["antecedent_rain_24h_mm"].to_numpy(float)
        assert np.allclose(estimator.predict(test[["antecedent_rain_24h_mm"]]), expected)

    def test_rolling_mean_divides_by_the_window(self, splits) -> None:
        train, _, test = splits
        estimator = make_baseline("rolling_mean_7d")
        estimator.fit(train[["rain_last_7d_mm"]], train[TARGET].to_numpy(float))

        expected = test["rain_last_7d_mm"].to_numpy(float) / 7.0
        assert np.allclose(estimator.predict(test[["rain_last_7d_mm"]]), expected)

    def test_seasonal_climatology_learns_from_training_only(self, splits) -> None:
        train, _, test = splits
        estimator = make_baseline("seasonal_climatology")
        columns = ["district_id", "target_month"]
        estimator.fit(train[columns], train[TARGET].to_numpy(float))

        # The lookup table must contain exactly the training districts/months.
        assert len(estimator.table_) <= train["district_id"].nunique() * 12
        predictions = estimator.predict(test[columns])
        assert np.isfinite(predictions).all()

    def test_seasonal_climatology_falls_back_for_unseen_districts(self, splits) -> None:
        train, _, test = splits
        estimator = make_baseline("seasonal_climatology")
        columns = ["district_id", "target_month"]
        estimator.fit(train[columns], train[TARGET].to_numpy(float))

        unseen = test[columns].copy()
        unseen["district_id"] = 9999
        predictions = estimator.predict(unseen)
        assert np.allclose(predictions, estimator.global_mean_)

    def test_global_mean_predicts_the_training_mean(self, splits) -> None:
        train, _, test = splits
        estimator = make_baseline("global_mean")
        estimator.fit(train[["antecedent_rain_24h_mm"]], train[TARGET].to_numpy(float))

        assert np.allclose(
            estimator.predict(test[["antecedent_rain_24h_mm"]]), train[TARGET].mean()
        )

    def test_all_baselines_are_registered(self) -> None:
        assert set(baseline_estimators()) == {
            "persistence",
            "rolling_mean_7d",
            "seasonal_climatology",
            "global_mean",
        }

    def test_unknown_baseline_raises(self) -> None:
        with pytest.raises(KeyError, match="Unknown baseline"):
            make_baseline("crystal_ball")

    def test_persistence_falls_back_to_zero_without_its_column(self) -> None:
        estimator = PersistenceRegressor()
        assert np.allclose(estimator.predict(pd.DataFrame({"other": [1.0, 2.0]})), 0.0)

    def test_rolling_mean_falls_back_to_zero_without_its_column(self) -> None:
        estimator = RollingMeanRegressor()
        assert np.allclose(estimator.predict(pd.DataFrame({"other": [1.0]})), 0.0)


class TestCandidateModels:
    @pytest.mark.parametrize("spec", CANDIDATES, ids=lambda spec: spec.name)
    def test_each_candidate_fits_and_predicts(self, splits, spec) -> None:
        train, valid, _ = splits
        features = TEST_FEATURES

        pipeline = build_pipeline(spec, features)
        pipeline.fit(train[features], train[TARGET].to_numpy(float))
        predictions = pipeline.predict(valid[features])

        assert len(predictions) == len(valid)
        assert np.isfinite(predictions).all()

    def test_every_candidate_documents_its_rationale(self) -> None:
        for spec in CANDIDATES:
            assert spec.rationale
            assert spec.family

    def test_pipeline_persists_preprocessing(self, splits) -> None:
        train, valid, _ = splits
        features = TEST_FEATURES
        spec = next(s for s in CANDIDATES if s.name == "ridge")

        pipeline = build_pipeline(spec, features)
        assert "preprocessor" in pipeline.named_steps
        assert "regressor" in pipeline.named_steps

        pipeline.fit(train[features], train[TARGET].to_numpy(float))
        assert np.isfinite(pipeline.predict(valid[features])).all()

    def test_feature_selector_is_added_when_needed(self) -> None:
        spec = next(s for s in CANDIDATES if s.name == "ridge")
        many = [f"f{i}" for i in range(20)]
        assert "selector" in build_pipeline(spec, many, max_features=5).named_steps
        assert "selector" not in build_pipeline(spec, many[:3], max_features=5).named_steps

    def test_quantile_pipeline_produces_a_conditional_median(self, splits) -> None:
        train, valid, _ = splits
        features = TEST_FEATURES
        spec = next(s for s in CANDIDATES if s.name == "ridge")

        pipeline = make_quantile_pipeline(spec, features, 0.5)
        pipeline.fit(train[features], train[TARGET].to_numpy(float))
        predictions = pipeline.predict(valid[features])
        assert np.isfinite(predictions).all()

    def test_training_config_rejects_unknown_candidates(
        self, tmp_path, demo_observations_path, demo_districts_path
    ) -> None:
        report = run_training(
            observations_path=demo_observations_path,
            districts_path=demo_districts_path,
            artifact_root=tmp_path,
            config=TrainingConfig(candidate_names=["not_a_model"]),
        )
        assert report.status == "failed"
        assert "Unknown candidate" in report.error


class TestArtifactRegistry:
    def test_next_version_increments(self, tmp_path) -> None:
        assert next_version(tmp_path) == "v001"
        (tmp_path / "v001").mkdir()
        (tmp_path / "v001" / "metadata.json").write_text("{}")
        assert next_version(tmp_path) == "v002"

    def test_lists_only_directories_with_metadata(self, tmp_path) -> None:
        (tmp_path / "v001").mkdir()
        (tmp_path / "v001" / "metadata.json").write_text("{}")
        (tmp_path / "v002").mkdir()
        (tmp_path / "v003").mkdir()
        (tmp_path / "stray.txt").write_text("x")

        assert list_versions(tmp_path) == ["v001"]

    def test_empty_root_lists_nothing(self, tmp_path) -> None:
        assert list_versions(tmp_path) == []

    def test_checksum_verifies_a_saved_artifact(self, tmp_path, splits) -> None:
        from sklearn.dummy import DummyRegressor

        pipeline = build_pipeline(
            next(s for s in CANDIDATES if s.name == "ridge"), ["antecedent_rain_24h_mm"]
        )
        directory = save_artifact(
            root=tmp_path,
            version="v001",
            pipeline=pipeline,
            features=["antecedent_rain_24h_mm"],
            metadata={"version": "v001"},
            metrics={},
        )
        assert verify_checksum(tmp_path, "v001")
        assert (directory / "feature_columns.json").exists()
        assert (directory / "metadata.json").exists()
        assert DummyRegressor is not None

    def test_overwriting_is_refused(self, tmp_path) -> None:
        pipeline = build_pipeline(
            next(s for s in CANDIDATES if s.name == "ridge"), ["antecedent_rain_24h_mm"]
        )
        save_artifact(tmp_path, "v001", pipeline, ["antecedent_rain_24h_mm"], {}, {})

        with pytest.raises(FileExistsError, match="immutable"):
            save_artifact(tmp_path, "v001", pipeline, ["antecedent_rain_24h_mm"], {}, {})

    def test_overwrite_flag_allows_replacement(self, tmp_path) -> None:
        pipeline = build_pipeline(
            next(s for s in CANDIDATES if s.name == "ridge"), ["antecedent_rain_24h_mm"]
        )
        save_artifact(tmp_path, "v001", pipeline, ["antecedent_rain_24h_mm"], {}, {})
        save_artifact(
            tmp_path, "v001", pipeline, ["antecedent_rain_24h_mm"], {}, {}, overwrite=True
        )
        assert verify_checksum(tmp_path, "v001")

    def test_tampering_is_detected(self, tmp_path) -> None:
        pipeline = build_pipeline(
            next(s for s in CANDIDATES if s.name == "ridge"), ["antecedent_rain_24h_mm"]
        )
        directory = save_artifact(tmp_path, "v001", pipeline, ["antecedent_rain_24h_mm"], {}, {})
        (directory / "model.joblib").write_bytes(b"tampered")
        assert not verify_checksum(tmp_path, "v001")

    def test_metadata_records_the_model_card_fields(self) -> None:
        from datetime import UTC, datetime

        metadata = build_metadata(
            model_name="test",
            version="v001",
            features=["a", "b"],
            target_column="target_rainfall_mm",
            hyperparameters={"alpha": 1.0},
            metrics={"mae_mm": 4.0},
            training_data_start=datetime(2024, 1, 1, tzinfo=UTC),
            training_data_end=datetime(2024, 6, 1, tzinfo=UTC),
            dataset_path="data.csv",
            dataset_rows=1000,
            selected_model="ridge",
        )

        for field in (
            "model_name",
            "version",
            "trained_at",
            "training_data_range",
            "features",
            "metrics",
            "framework_version",
            "status",
            "selected_model",
        ):
            assert field in metadata
        assert metadata["status"] == "candidate"
        assert json.loads(json.dumps(metadata)) == metadata


class TestConfiguration:
    def test_defaults_are_used_when_no_file_exists(self, tmp_path) -> None:
        config = load_config(tmp_path / "absent.yaml")
        assert config.random_seed == 42
        assert config.event_threshold_mm == 15.0

    def test_repository_config_loads(self) -> None:
        config = load_config()
        assert config.horizon_days == 1
        assert "ridge" in config.candidate_names

    def test_unknown_keys_are_rejected(self, tmp_path) -> None:
        path = tmp_path / "training.yaml"
        path.write_text("mystery_knob: 3")
        with pytest.raises(ValueError, match="Unknown configuration keys"):
            load_config(path)

    def test_fingerprint_ignores_notes(self) -> None:
        first = TrainingConfig(notes="run A")
        second = TrainingConfig(notes="run B")
        assert first.fingerprint() == second.fingerprint()

    def test_fingerprint_changes_with_the_seed(self) -> None:
        assert (
            TrainingConfig(random_seed=1).fingerprint()
            != TrainingConfig(random_seed=2).fingerprint()
        )

    def test_set_global_seed_makes_fitting_reproducible(self, splits) -> None:
        train, valid, _ = splits
        spec = next(s for s in CANDIDATES if s.name == "random_forest")

        def fit_once() -> np.ndarray:
            set_global_seed(7)
            pipeline = build_pipeline(spec, TEST_FEATURES)
            pipeline.fit(train[TEST_FEATURES], train[TARGET].to_numpy(float))
            return pipeline.predict(valid[TEST_FEATURES])

        assert np.allclose(fit_once(), fit_once())


class TestTrainingPipeline:
    def test_runs_end_to_end_and_writes_an_artifact(
        self, tmp_path, demo_observations_path, demo_districts_path
    ) -> None:
        config = TrainingConfig(candidate_names=["ridge"], fit_interval_models=True, max_features=6)
        report = run_training(
            observations_path=demo_observations_path,
            districts_path=demo_districts_path,
            artifact_root=tmp_path,
            config=config,
        )

        assert report.status == "succeeded", report.error
        assert report.version == "v001"
        assert Path(report.artifact_path).exists()
        assert (Path(report.artifact_path) / "model.joblib").exists()
        assert (Path(report.artifact_path) / "lower_model.joblib").exists()
        assert (Path(report.artifact_path) / "metadata.json").exists()
        assert verify_checksum(tmp_path, "v001")

    def test_report_captures_every_stage(
        self, tmp_path, demo_observations_path, demo_districts_path
    ) -> None:
        report = run_training(
            observations_path=demo_observations_path,
            districts_path=demo_districts_path,
            artifact_root=tmp_path,
            config=TrainingConfig(candidate_names=["ridge"], fit_interval_models=False),
        )

        assert report.validation["observations"]["rows"] > 0
        assert report.cleaning["output_rows"] > 0
        assert report.split_sizes["train"] > 0
        assert report.split_sizes["test"] > 0
        assert report.feature_selection["selected"]
        assert report.split_dates["train_end"] < report.split_dates["valid_start"]
        assert report.split_dates["valid_end"] < report.split_dates["test_start"]

    def test_records_baselines_and_candidates(
        self, tmp_path, demo_observations_path, demo_districts_path
    ) -> None:
        report = run_training(
            observations_path=demo_observations_path,
            districts_path=demo_districts_path,
            artifact_root=tmp_path,
            config=TrainingConfig(candidate_names=["ridge", "random_forest"]),
        )

        assert "persistence" in report.metrics["validation"]
        assert "ridge" in report.metrics["validation"]
        assert report.metrics["best_baseline"] is not None
        assert report.selected_model is not None

    def test_is_reproducible(self, tmp_path, demo_observations_path, demo_districts_path) -> None:
        config = TrainingConfig(candidate_names=["ridge"], fit_interval_models=False)
        first = run_training(
            observations_path=demo_observations_path,
            districts_path=demo_districts_path,
            artifact_root=tmp_path / "a",
            config=config,
            version="run",
        )
        second = run_training(
            observations_path=demo_observations_path,
            districts_path=demo_districts_path,
            artifact_root=tmp_path / "b",
            config=config,
            version="run",
        )

        assert first.metrics["validation"] == second.metrics["validation"]
        assert first.selected_model == second.selected_model

    def test_failure_is_reported_not_raised(self, tmp_path) -> None:
        report = run_training(
            observations_path=tmp_path / "missing.csv",
            districts_path=tmp_path / "missing.csv",
            artifact_root=tmp_path,
            config=TrainingConfig(),
        )

        assert report.status == "failed"
        assert report.error
        assert report.artifact_path is None

    def test_records_the_run_through_the_callback(
        self, tmp_path, demo_observations_path, demo_districts_path
    ) -> None:
        calls: list[dict] = []

        def recorder(**payload):
            calls.append(payload)

        report = run_training(
            observations_path=demo_observations_path,
            districts_path=demo_districts_path,
            artifact_root=tmp_path,
            config=TrainingConfig(candidate_names=["ridge"], fit_interval_models=False),
            register_run=recorder,
        )

        assert report.status == "succeeded"
        statuses = [call.get("status") for call in calls]
        assert "running" in statuses
        assert "succeeded" in statuses
        assert any(call.get("created_model_version") == "v001" for call in calls)

    def test_records_failures_through_the_callback(self, tmp_path) -> None:
        calls: list[dict] = []

        run_training(
            observations_path=tmp_path / "missing.csv",
            districts_path=tmp_path / "missing.csv",
            artifact_root=tmp_path,
            config=TrainingConfig(),
            register_run=lambda **payload: calls.append(payload),
        )

        assert any(call.get("status") == "failed" for call in calls)
        assert any(call.get("error_message") for call in calls)

    def test_saved_metadata_matches_the_loader(
        self, tmp_path, demo_observations_path, demo_districts_path
    ) -> None:
        report = run_training(
            observations_path=demo_observations_path,
            districts_path=demo_districts_path,
            artifact_root=tmp_path,
            config=TrainingConfig(candidate_names=["ridge"], fit_interval_models=False),
        )
        metadata = load_metadata(tmp_path, "v001")

        assert metadata["version"] == report.version
        assert metadata["features"] == report.feature_selection["selected"]
        assert metadata["dataset_rows"] == report.dataset_rows
