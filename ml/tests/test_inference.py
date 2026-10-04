"""Serving-side inference: preprocessing parity, prediction and severity."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from rainml.inference.predictor import (
    ModelInferenceError,
    Prediction,
    RainfallPredictor,
    classify_severity,
)
from rainml.inference.preprocessing import (
    FEATURE_COLUMNS,
    DistrictHistory,
    build_feature_frame,
    to_feature_frame,
)


def history(district: int = 1, days: int = 60, seed: int = 0) -> DistrictHistory:
    rng = np.random.default_rng(seed + district)
    start = datetime(2024, 6, 1, tzinfo=UTC).date()
    return DistrictHistory(
        district_id=district,
        latitude=19.0 + (district - 1),
        longitude=72.0 + (district - 1),
        daily_rainfall_mm={
            start + timedelta(days=day): float(round(rng.gamma(1.2, 5.0), 2)) for day in range(days)
        },
    )


class TestBuildFeatureFrame:
    def test_column_order_is_the_contract(self) -> None:
        frame = build_feature_frame([history()], datetime(2024, 7, 1).date())
        assert list(frame.columns) == list(FEATURE_COLUMNS)

    def test_all_values_are_finite(self) -> None:
        frame = build_feature_frame([history(), history(2, seed=5)], datetime(2024, 7, 1).date())
        assert np.isfinite(frame.to_numpy(dtype=float)).all()

    def test_empty_batch_returns_an_empty_frame(self) -> None:
        frame = build_feature_frame([], datetime(2024, 7, 1).date())
        assert frame.empty
        assert list(frame.columns) == list(FEATURE_COLUMNS)

    def test_to_feature_frame_matches_the_batch_builder(self) -> None:
        record = {
            "district_id": 1,
            "lat": 19.0,
            "lon": 72.0,
            "daily_rainfall_mm": history().daily_rainfall_mm,
        }
        issue_time = datetime(2024, 7, 1, tzinfo=UTC)
        single = to_feature_frame(record, issue_time)
        batched = build_feature_frame([history()], issue_time.date())
        pd.testing.assert_frame_equal(single, batched)

    def test_windows_do_not_reach_beyond_the_history(self) -> None:
        frame = build_feature_frame([history()], datetime(2030, 1, 1).date())
        # The record ends in July 2024, so a 2030 issue date has nothing inside
        # any 30 day window.
        assert frame["rain_last_30d_mm"].iloc[0] == 0.0
        assert frame["rain_last_7d_mm"].iloc[0] == 0.0

    def test_antecedent_is_the_latest_day_before_issue(self) -> None:
        record = history()
        issue_day = datetime(2024, 7, 20).date()
        frame = build_feature_frame([record], issue_day)

        latest = max(day for day in record.daily_rainfall_mm if day < issue_day)
        assert frame["antecedent_rain_24h_mm"].iloc[0] == pytest.approx(
            record.daily_rainfall_mm[latest]
        )


class TestSeverityClassification:
    @pytest.mark.parametrize(
        ("rainfall", "expected"),
        [
            (0.0, "none"),
            (0.2, "light"),
            (3.0, "moderate"),
            (10.0, "heavy"),
            (20.0, "very_heavy"),
            (50.0, "extreme"),
            (-1.0, "none"),
        ],
    )
    def test_bands(self, rainfall: float, expected: str) -> None:
        assert classify_severity(rainfall) == expected


class TestPredictor:
    def test_loads_a_trained_artifact(self, trained_artifact: Path) -> None:
        predictor = RainfallPredictor(trained_artifact)
        assert predictor.version == trained_artifact.name
        assert predictor.features
        assert predictor.pipeline is not None

    def test_rejects_a_directory_without_metadata(self, tmp_path) -> None:
        with pytest.raises(ModelInferenceError, match="not a valid artifact"):
            RainfallPredictor.from_artifact_root(tmp_path, "v999")

    def test_rejects_a_tampered_artifact(self, trained_artifact: Path, tmp_path) -> None:
        import shutil

        copy = tmp_path / trained_artifact.name
        shutil.copytree(trained_artifact, copy)
        (copy / "model.joblib").write_bytes(b"corrupted")

        with pytest.raises(ModelInferenceError, match="Checksum mismatch"):
            RainfallPredictor(copy)

    def test_predicts_from_a_feature_frame(self, trained_artifact: Path) -> None:
        predictor = RainfallPredictor(trained_artifact)
        frame = build_feature_frame([history(), history(2, seed=9)], datetime(2024, 7, 20).date())
        output = predictor.predict_frame(frame)

        assert len(output) == 2
        assert {"predicted_rainfall_mm", "lower_bound_mm", "upper_bound_mm"}.issubset(
            output.columns
        )
        assert (output["predicted_rainfall_mm"] >= 0).all()

    def test_interval_brackets_the_point_forecast(self, trained_artifact: Path) -> None:
        predictor = RainfallPredictor(trained_artifact)
        frame = build_feature_frame(
            [history(d, seed=d * 3) for d in range(1, 6)], datetime(2024, 7, 20).date()
        )
        output = predictor.predict_frame(frame)

        assert (output["lower_bound_mm"] <= output["predicted_rainfall_mm"]).all()
        assert (output["predicted_rainfall_mm"] <= output["upper_bound_mm"]).all()

    def test_missing_feature_columns_are_refused(self, trained_artifact: Path) -> None:
        predictor = RainfallPredictor(trained_artifact)
        with pytest.raises(ModelInferenceError, match="missing features"):
            predictor.predict_frame(pd.DataFrame({"lat": [19.0]}))

    def test_predict_districts_returns_typed_output(self, trained_artifact: Path) -> None:
        predictor = RainfallPredictor(trained_artifact)
        predictions = predictor.predict_districts(
            [history(), history(2, seed=11)], issue_date=datetime(2024, 7, 20).date()
        )

        assert len(predictions) == 2
        assert all(isinstance(p, Prediction) for p in predictions)
        assert {p.district_id for p in predictions} == {1, 2}
        assert all(
            p.severity in {"none", "light", "moderate", "heavy", "very_heavy", "extreme"}
            for p in predictions
        )
        assert all(p.model_version == trained_artifact.name for p in predictions)

    def test_predictions_serialise(self, trained_artifact: Path) -> None:
        predictor = RainfallPredictor(trained_artifact)
        prediction = predictor.predict_districts(
            [history()], issue_date=datetime(2024, 7, 20).date()
        )[0]
        payload = prediction.as_dict()

        assert json.loads(json.dumps(payload))["model_version"] == trained_artifact.name
        assert payload["target_date"] == "2024-07-21"

    def test_predictions_are_deterministic(self, trained_artifact: Path) -> None:
        predictor = RainfallPredictor(trained_artifact)
        frame = build_feature_frame([history()], datetime(2024, 7, 20).date())

        first = predictor.predict_frame(frame)["predicted_rainfall_mm"].tolist()
        second = predictor.predict_frame(frame)["predicted_rainfall_mm"].tolist()
        assert first == second

    def test_observations_after_the_issue_date_are_ignored(self, trained_artifact: Path) -> None:
        # Adding future observations must not change a forecast, which is the
        # property that guarantees the feature build is causal.
        predictor = RainfallPredictor(trained_artifact)
        issue_day = datetime(2024, 7, 20).date()
        known = history(days=49)
        extended = DistrictHistory(
            district_id=known.district_id,
            latitude=known.latitude,
            longitude=known.longitude,
            daily_rainfall_mm={
                **known.daily_rainfall_mm,
                **{
                    day: 99.0
                    for day in [issue_day + timedelta(days=offset) for offset in range(1, 20)]
                },
            },
        )

        before = predictor.predict_frame(build_feature_frame([known], issue_day))
        after = predictor.predict_frame(build_feature_frame([extended], issue_day))
        pd.testing.assert_frame_equal(before, after)
