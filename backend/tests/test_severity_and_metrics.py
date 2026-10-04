"""Severity classification, verification metrics and the colour legend."""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from app.services import severity as severity_module
from app.services import verification_metrics as vm
from app.services.severity import SEVERITY_BANDS, band_for, classify, legend


class TestClassify:
    @pytest.mark.parametrize(
        ("rainfall", "expected"),
        [
            (0.0, "none"),
            (0.09, "none"),
            (0.1, "light"),
            (2.4, "light"),
            (2.5, "moderate"),
            (7.5, "moderate"),
            (7.6, "heavy"),
            (15.5, "heavy"),
            (15.6, "very_heavy"),
            (31.7, "very_heavy"),
            (31.8, "extreme"),
            (250.0, "extreme"),
        ],
    )
    def test_boundaries_are_half_open(self, rainfall: float, expected: str) -> None:
        assert classify(rainfall) == expected

    def test_negative_values_are_treated_as_no_rain(self) -> None:
        # A model can emit a small negative after a tree split; it must not
        # render as a distinct category.
        assert classify(-3.0) == "none"

    def test_band_boundaries_do_not_overlap(self) -> None:
        for (_, label, severity, _), (
            next_upper,
            next_label,
            next_severity,
            _,
        ) in itertools.pairwise(SEVERITY_BANDS):
            assert next_upper > 0
            assert label != next_label
            assert severity != next_severity

    def test_band_for_returns_both_bounds(self) -> None:
        band = band_for(5.0)
        assert band.min_mm == 2.5
        assert band.max_mm == 7.6

    def test_top_band_has_no_upper_bound(self) -> None:
        assert band_for(1000.0).max_mm is None

    def test_legend_is_contiguous_and_ordered(self) -> None:
        entries = legend()
        assert [e["severity"] for e in entries] == [band[2] for band in SEVERITY_BANDS]

        for previous, current in itertools.pairwise(entries):
            assert previous["max_mm"] == current["min_mm"]


class TestContinuousMetrics:
    def test_perfect_forecast_has_zero_error(self) -> None:
        observed = np.array([0.0, 5.0, 20.0])
        metrics = vm.continuous_metrics(observed, observed)
        assert metrics.mean_absolute_error_mm == 0.0
        assert metrics.rmse_mm == 0.0
        assert metrics.bias_mm == 0.0

    def test_bias_is_forecast_minus_observation(self) -> None:
        metrics = vm.continuous_metrics(np.array([10.0]), np.array([4.0]))
        assert metrics.bias_mm == pytest.approx(6.0)
        assert metrics.mean_error_mm == pytest.approx(-6.0)

    def test_rmse_is_at_least_mae(self) -> None:
        forecast = np.array([0.0, 0.0, 0.0])
        observed = np.array([1.0, 2.0, 3.0])
        metrics = vm.continuous_metrics(forecast, observed)
        assert metrics.rmse_mm >= metrics.mean_absolute_error_mm

    def test_empty_input_returns_zeroes(self) -> None:
        metrics = vm.continuous_metrics(np.array([]), np.array([]))
        assert metrics.sample_size == 0

    def test_nse_is_one_for_a_perfect_forecast(self) -> None:
        observed = np.array([1.0, 4.0, 9.0, 16.0])
        assert vm.nash_sutcliffe_efficiency(observed, observed) == pytest.approx(1.0)

    def test_nse_returns_none_without_observation_variance(self) -> None:
        # Reporting 0.0 here would be a claim about skill that cannot be made.
        constant = np.array([5.0, 5.0, 5.0])
        assert vm.nash_sutcliffe_efficiency(np.array([4.0, 6.0, 5.0]), constant) is None

    def test_nse_returns_none_for_a_single_sample(self) -> None:
        assert vm.nash_sutcliffe_efficiency(np.array([3.0]), np.array([4.0])) is None


class TestCategoricalMetrics:
    def test_confusion_matrix_is_exact(self) -> None:
        forecast = np.array([20.0, 20.0, 1.0, 1.0])
        observed = np.array([20.0, 1.0, 20.0, 1.0])
        counts = vm.categorical_counts(forecast, observed, threshold_mm=15.0)
        assert counts.to_dict()["hits"] == 1
        assert counts.to_dict()["false_alarms"] == 1
        assert counts.to_dict()["misses"] == 1
        assert counts.to_dict()["correct_negatives"] == 1
        assert counts.total == 4

    def test_pod_far_and_csi_against_known_values(self) -> None:
        forecast = np.array([20.0, 20.0, 1.0, 1.0])
        observed = np.array([20.0, 1.0, 20.0, 1.0])
        scores = vm.categorical_metrics(forecast, observed, threshold_mm=15.0)

        assert scores.pod == pytest.approx(0.5)  # 1 hit / 2 events
        assert scores.far == pytest.approx(0.5)  # 1 false alarm / 2 forecasts
        assert scores.csi == pytest.approx(0.25)  # 1 hit / 4 samples

    def test_scores_are_none_without_samples(self) -> None:
        scores = vm.categorical_metrics(np.array([]), np.array([]))
        assert scores.pod is None
        assert scores.csi is None

    def test_a_never_forecasting_model_has_zero_detection(self) -> None:
        forecast = np.zeros(5)
        observed = np.array([20.0, 25.0, 30.0, 1.0, 2.0])
        scores = vm.categorical_metrics(forecast, observed, threshold_mm=15.0)
        assert scores.pod == 0.0
        assert scores.far is None  # nothing was forecast, so FAR is undefined
        assert scores.counts.misses == 3
        assert scores.counts.correct_negatives == 2


class TestLeadTimeBuckets:
    @pytest.mark.parametrize(
        ("hours", "bucket"),
        [(0, "0-6h"), (6, "0-6h"), (7, "6-12h"), (12, "6-12h"), (24, "12-24h"), (72, ">48h")],
    )
    def test_buckets(self, hours: float, bucket: str) -> None:
        assert vm.lead_time_bucket(hours) == bucket


class TestSkillScore:
    def test_positive_skill_when_better_than_reference(self) -> None:
        assert vm.skill_score(4.0, 5.0) == pytest.approx(0.2)

    def test_none_when_reference_is_zero(self) -> None:
        assert vm.skill_score(1.0, 0.0) is None


def test_severity_to_alert_covers_every_band() -> None:
    for _, _, band_severity, _ in SEVERITY_BANDS:
        assert band_severity in severity_module.SEVERITY_TO_ALERT
