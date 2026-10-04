"""Verification metrics, model comparison and selection."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from rainml.evaluation.evaluator import compare, predictions_frame, rank, score_predictions
from rainml.evaluation.metrics import (
    DEFAULT_EVENT_THRESHOLD_MM,
    brier_score,
    categorical_scores,
    evaluate,
    evaluate_by_group,
    mae,
    nash_sutcliffe_efficiency,
    rmse,
    skill_score,
)

TOLERANCE = 1e-6


class TestContinuousMetrics:
    def test_mae_matches_a_manual_computation(self) -> None:
        assert mae(np.array([1.0, 2.0]), np.array([3.0, 4.0])) == pytest.approx(2.0)

    def test_rmse_is_at_least_mae(self) -> None:
        forecast = np.array([0.0, 0.0, 0.0])
        observed = np.array([1.0, 2.0, 3.0])
        assert rmse(forecast, observed) >= mae(forecast, observed)

    def test_bias_is_forecast_minus_observed(self) -> None:
        from rainml.evaluation.metrics import bias

        assert bias(np.array([10.0, 4.0]), np.array([5.0, 2.0])) == pytest.approx(3.5)

    def test_nse_is_one_for_a_perfect_forecast(self) -> None:
        observed = np.array([1.0, 4.0, 9.0, 16.0])
        assert nash_sutcliffe_efficiency(observed, observed) == pytest.approx(1.0)

    def test_nse_is_none_without_variance(self) -> None:
        constant = np.array([5.0, 5.0, 5.0])
        assert nash_sutcliffe_efficiency(np.array([4.0, 6.0, 5.0]), constant) is None

    def test_nse_is_none_for_a_single_sample(self) -> None:
        assert nash_sutcliffe_efficiency(np.array([3.0]), np.array([4.0])) is None

    def test_accepts_pandas_series(self) -> None:
        assert mae(pd.Series([1.0, 2.0]), pd.Series([1.0, 4.0])) == pytest.approx(1.0)


class TestCategoricalMetrics:
    def test_confusion_matrix(self) -> None:
        forecast = np.array([20.0, 20.0, 1.0, 1.0])
        observed = np.array([20.0, 1.0, 20.0, 1.0])
        counts = categorical_scores(forecast, observed, threshold_mm=15.0)

        assert counts["hits"] == 1
        assert counts["false_alarms"] == 1
        assert counts["misses"] == 1
        assert counts["correct_negatives"] == 1
        assert counts["pod"] == pytest.approx(0.5)
        assert counts["far"] == pytest.approx(0.5)
        assert counts["csi"] == pytest.approx(0.25)

    def test_perfect_event_forecast(self) -> None:
        forecast = np.array([20.0, 20.0])
        observed = np.array([20.0, 20.0])
        scores = categorical_scores(forecast, observed, threshold_mm=15.0)
        assert scores["pod"] == pytest.approx(1.0)
        assert scores["far"] == pytest.approx(0.0)
        assert scores["csi"] == pytest.approx(1.0)

    def test_scores_are_defined_when_only_correct_negatives_exist(self) -> None:
        # There are samples but no events and no forecasts, so every ratio has a
        # denominator: hit rate is 1 and the event scores are 0.
        forecast = np.zeros(3)
        observed = np.array([0.0, 0.0, 0.0])
        scores = categorical_scores(forecast, observed, threshold_mm=15.0)

        assert scores["hit_rate"] == pytest.approx(1.0)
        assert scores["csi"] == 0.0
        assert scores["correct_negatives"] == 3
        # No events occurred and none were forecast, so POD and FAR have a zero
        # denominator and stay undefined.
        assert scores["pod"] is None
        assert scores["far"] is None

    def test_undefined_when_there_are_no_samples(self) -> None:
        scores = categorical_scores(np.array([]), np.array([]), threshold_mm=15.0)
        assert scores["pod"] is None
        assert scores["csi"] is None

    def test_threshold_is_respected(self) -> None:
        # 14 mm is below the 15 mm event definition, 16 mm is above it.
        below = categorical_scores(np.array([14.0]), np.array([14.0]), threshold_mm=15.0)
        above = categorical_scores(np.array([16.0]), np.array([16.0]), threshold_mm=15.0)
        assert below["hits"] == 0
        assert above["hits"] == 1

    def test_default_threshold_is_documented(self) -> None:
        assert DEFAULT_EVENT_THRESHOLD_MM == 15.0


class TestBrierScore:
    def test_perfect_forecast_is_zero(self) -> None:
        forecast = np.array([20.0, 0.0])
        observed = np.array([20.0, 0.0])
        assert brier_score(forecast, observed, threshold_mm=15.0) == pytest.approx(0.0)

    def test_worst_case_is_one(self) -> None:
        forecast = np.array([0.0, 0.0])
        observed = np.array([20.0, 20.0])
        assert brier_score(forecast, observed, threshold_mm=15.0) == pytest.approx(1.0)

    def test_is_bounded(self) -> None:
        rng = np.random.default_rng(0)
        forecast = rng.gamma(1.5, 6.0, 500)
        observed = rng.gamma(1.5, 6.0, 500)
        assert 0.0 <= brier_score(forecast, observed) <= 1.0


class TestEvaluate:
    def test_reports_sample_size_and_scores(self) -> None:
        scores = evaluate(np.array([1.0, 5.0, 20.0]), np.array([2.0, 3.0, 25.0]))
        assert scores["sample_size"] == 3
        # Scores are rounded for display; 4 decimal places.
        assert scores["mae_mm"] == pytest.approx((1.0 + 2.0 + 5.0) / 3, abs=1e-4)

    def test_evaluate_by_group_splits_correctly(self) -> None:
        frame = pd.DataFrame(
            {
                "prediction": [1.0, 2.0, 30.0, 40.0],
                "target_rainfall_mm": [1.5, 2.5, 35.0, 45.0],
                "group": ["dry", "dry", "wet", "wet"],
            }
        )
        groups = evaluate_by_group(frame, group_column="group")
        assert set(groups) == {"dry", "wet"}
        assert groups["dry"]["sample_size"] == 2
        assert groups["wet"]["mae_mm"] == pytest.approx(5.0)


class TestSkillScore:
    def test_positive_when_better_than_reference(self) -> None:
        assert skill_score(4.0, 5.0) == pytest.approx(0.2)

    def test_zero_when_equal(self) -> None:
        assert skill_score(5.0, 5.0) == pytest.approx(0.0)

    def test_none_when_reference_is_zero(self) -> None:
        assert skill_score(1.0, 0.0) is None


class TestRanking:
    def test_ranks_by_lowest_mae(self) -> None:
        scores = {"a": {"mae_mm": 5.0}, "b": {"mae_mm": 3.0}, "c": {"mae_mm": 4.0}}
        assert rank(scores) == "b"

    def test_ties_break_alphabetically(self) -> None:
        scores = {"z": {"mae_mm": 3.0}, "a": {"mae_mm": 3.0}}
        assert rank(scores) == "a"

    def test_none_when_nothing_is_scorable(self) -> None:
        assert rank({"a": {"mae_mm": None}}) is None
        assert rank({}) is None


class TestComparison:
    @pytest.fixture
    def scores(self) -> tuple[dict, dict]:
        baselines = {
            "persistence": {"mae_mm": 5.0, "sample_size": 100},
            "global_mean": {"mae_mm": 6.0, "sample_size": 100},
        }
        candidates = {
            "ridge": {"mae_mm": 5.5, "sample_size": 100},
            "boosting": {"mae_mm": 4.0, "sample_size": 100},
        }
        test = {
            "persistence": {"mae_mm": 5.2, "sample_size": 50},
            "boosting": {"mae_mm": 4.1, "sample_size": 50},
        }
        return {**baselines, **candidates}, test

    def test_identifies_the_best_of_each_group(self, scores) -> None:
        validation, test = scores
        result = compare(validation, test, baseline_names={"persistence", "global_mean"})

        assert result.best_baseline == "persistence"
        assert result.best_candidate == "boosting"

    def test_reports_skill_against_the_best_baseline(self, scores) -> None:
        validation, test = scores
        result = compare(validation, test, baseline_names={"persistence", "global_mean"})

        assert result.skill_vs_baseline["boosting"] == pytest.approx(1 - 4.1 / 5.2)
        assert result.beats_baseline is True

    def test_reports_when_the_candidate_is_worse(self) -> None:
        validation = {"base": {"mae_mm": 3.0}, "cand": {"mae_mm": 4.0}}
        test = {"base": {"mae_mm": 3.0}, "cand": {"mae_mm": 4.0}}
        result = compare(validation, test, baseline_names={"base"})

        assert result.beats_baseline is False
        assert result.skill_vs_baseline["cand"] < 0

    def test_only_test_scores_for_the_selected_models_are_reported(self, scores) -> None:
        validation, test = scores
        result = compare(validation, test, baseline_names={"persistence", "global_mean"})

        assert set(result.test_scores) == {"persistence", "boosting"}

    def test_serialises_to_json_safe_dict(self, scores) -> None:
        import json

        validation, test = scores
        payload = compare(validation, test, baseline_names={"persistence", "global_mean"}).to_dict()
        assert json.loads(json.dumps(payload))["best_candidate"] == "boosting"


class TestScorePredictions:
    def test_caps_large_samples(self) -> None:
        rng = np.random.default_rng(0)
        forecast = rng.gamma(1.5, 6.0, 10_000)
        observed = rng.gamma(1.5, 6.0, 10_000)

        capped = score_predictions(forecast, observed, cap=500)
        assert capped["sample_size"] == 500

    def test_uncapped_scores_everything(self) -> None:
        forecast = np.array([1.0, 2.0])
        observed = np.array([1.5, 2.5])
        assert score_predictions(forecast, observed, cap=None)["sample_size"] == 2

    def test_predictions_frame_attaches_the_column(self) -> None:
        frame = pd.DataFrame({"district_id": [1, 2]})
        result = predictions_frame(frame, np.array([1.0, 2.0]))
        assert list(result["prediction"]) == [1.0, 2.0]
