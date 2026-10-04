"""Feature engineering, leakage prevention, selection and preprocessing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from rainml.features.engineering import (
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    assert_no_leakage,
    build_training_frame,
)
from rainml.features.selection import analyse_features, build_preprocessor
from rainml.inference.preprocessing import DistrictHistory, build_feature_frame

TOLERANCE = 1e-6


def make_series(district: int, days: int = 60, seed: int = 0) -> pd.DataFrame:
    # District ids start at 1 to match the seeded dimension table.
    rng = np.random.default_rng(seed + district)
    start = datetime(2024, 6, 1, tzinfo=UTC)
    return pd.DataFrame(
        {
            "district_id": district + 1,
            "observed_at": [start + timedelta(days=d) for d in range(days)],
            "rainfall_mm": np.round(rng.gamma(1.1, 5.0, size=days), 2),
            "lat": 19.0 + district,
            "lon": 72.0 + district,
        }
    )


@pytest.fixture
def observations() -> pd.DataFrame:
    return pd.concat([make_series(d, seed=d * 10) for d in range(3)], ignore_index=True)


@pytest.fixture
def frame(observations) -> pd.DataFrame:
    return build_training_frame(observations)


class TestFeatureColumns:
    def test_every_declared_feature_is_produced(self, frame) -> None:
        assert set(FEATURE_COLUMNS).issubset(frame.columns)

    def test_no_feature_is_all_nan(self, frame) -> None:
        for column in FEATURE_COLUMNS:
            assert frame[column].notna().all(), column

    def test_features_are_finite(self, frame) -> None:
        values = frame[list(FEATURE_COLUMNS)].to_numpy(dtype=float)
        assert np.isfinite(values).all()

    def test_target_has_no_nan(self, frame) -> None:
        assert frame[TARGET_COLUMN].notna().all()

    def test_horizon_shift_matches_the_target(self, observations, frame) -> None:
        target_date = frame["target_date"].iloc[0]
        source = observations[
            (observations["district_id"] == 1)
            & (observations["observed_at"].dt.tz_localize(None) == target_date)
        ]
        assert frame[TARGET_COLUMN].iloc[0] == pytest.approx(source["rainfall_mm"].iloc[0])

    def test_two_day_horizon_shifts_further(self, observations) -> None:
        one_day = build_training_frame(observations, horizon_days=1)
        three_day = build_training_frame(observations, horizon_days=3)
        assert len(one_day) > len(three_day)
        assert three_day["target_date"].iloc[0] > one_day["target_date"].iloc[0]

    def test_output_is_deterministic(self, observations) -> None:
        pd.testing.assert_frame_equal(
            build_training_frame(observations), build_training_frame(observations)
        )


class TestLeakagePrevention:
    def test_assertion_passes_on_a_clean_frame(self, frame) -> None:
        assert_no_leakage(frame)

    def test_antecedent_matches_the_previous_day_not_the_target(self, frame) -> None:
        # shift(1) means the antecedent term is the previous day's rainfall; a
        # leaky build would show the target's own value instead.
        source = frame.set_index(["district_id", "issue_date"])
        for district in frame["district_id"].unique():
            rows = source.loc[district].sort_index()
            shifted = rows[TARGET_COLUMN].shift(-1)
            common = shifted.notna() & rows["antecedent_rain_24h_mm"].notna()
            if common.any():
                assert not (rows.loc[common, "antecedent_rain_24h_mm"] == shifted[common]).all()

    def test_leakage_is_detected_when_a_feature_is_the_target(self, observations) -> None:
        leaked = build_training_frame(observations)
        leaked["antecedent_rain_24h_mm"] = leaked[TARGET_COLUMN]
        with pytest.raises(AssertionError, match="future observations"):
            assert_no_leakage(leaked)

    def test_windows_ignore_the_issue_day(self, observations) -> None:
        frame = build_training_frame(observations)
        row = frame[
            (frame["district_id"] == 1) & (frame["issue_date"] == pd.Timestamp("2024-06-10"))
        ].iloc[0]

        source = observations[
            (observations["district_id"] == 1)
            & (observations["observed_at"] < pd.Timestamp("2024-06-10", tz="UTC"))
        ]
        expected = source["rainfall_mm"].tail(7).sum()
        assert row["rain_last_7d_mm"] == pytest.approx(expected, abs=TOLERANCE)

    def test_rolling_window_sums_match_a_manual_computation(self, observations) -> None:
        frame = build_training_frame(observations)
        row = frame[
            (frame["district_id"] == 2) & (frame["issue_date"] == pd.Timestamp("2024-06-20"))
        ].iloc[0]
        source = observations[
            (observations["district_id"] == 2)
            & (observations["observed_at"] < pd.Timestamp("2024-06-20", tz="UTC"))
        ]
        for window, column in (
            (1, "rain_last_1d_mm"),
            (3, "rain_last_3d_mm"),
            (30, "rain_last_30d_mm"),
        ):
            assert row[column] == pytest.approx(
                source["rainfall_mm"].tail(window).sum(), abs=TOLERANCE
            )

    def test_dry_streak_counts_consecutive_dry_days(self, observations) -> None:
        series = observations[observations["district_id"] == 1].sort_values("observed_at").copy()
        # The last row has no target and is dropped, so the last scored row's
        # antecedent is the second-to-last observation.
        series.loc[series.index[-6:], "rainfall_mm"] = 0.0
        frame = build_training_frame(series)

        # Five dry observations precede the last scored issue date.
        assert frame.iloc[-1]["dry_streak_days"] == 5

    def test_seasonal_term_uses_the_target_date(self, observations) -> None:
        frame = build_training_frame(observations)
        row = frame.iloc[0]
        doy = row["target_date"].timetuple().tm_yday
        assert row["doy_sin"] == pytest.approx(np.sin(2 * np.pi * doy / 365.25))
        assert row["doy_cos"] == pytest.approx(np.cos(2 * np.pi * doy / 365.25))

    def test_regional_term_is_a_cross_sectional_mean(self, observations) -> None:
        frame = build_training_frame(observations)
        expected = frame.groupby("issue_date")["rain_last_7d_mm"].transform("mean")
        assert np.allclose(frame["regional_mean_rain_7d_mm"], expected)


class TestFeatureSelection:
    def test_reports_selected_and_dropped_features(self, frame) -> None:
        report = analyse_features(frame, max_features=6)
        assert len(report.selected) == 6
        assert set(report.selected).isdisjoint(report.dropped)
        assert len(report.selected) + len(report.dropped) + len(report.constant) <= len(
            FEATURE_COLUMNS
        )

    def test_scores_are_populated(self, frame) -> None:
        report = analyse_features(frame)
        assert report.scores
        assert all(isinstance(value, float) for value in report.scores.values())

    def test_constant_features_are_detected(self, frame) -> None:
        degenerate = frame.copy()
        degenerate["flat"] = 1.0
        report = analyse_features(degenerate, features=list(FEATURE_COLUMNS) + ["flat"])
        assert "flat" in report.constant

    def test_selection_ranks_by_f_regression(self, frame) -> None:
        report = analyse_features(frame, max_features=5)
        best = sorted(report.scores, key=lambda name: report.scores[name], reverse=True)[:5]
        assert set(report.selected) == set(best)

    def test_more_features_than_available_is_handled(self, frame) -> None:
        report = analyse_features(frame, max_features=999)
        assert len(report.selected) <= len(FEATURE_COLUMNS)


class TestPreprocessor:
    def test_output_shape_matches_input(self, frame) -> None:
        preprocessor = build_preprocessor(list(FEATURE_COLUMNS))
        transformed = preprocessor.fit_transform(frame[list(FEATURE_COLUMNS)])
        assert transformed.shape == (len(frame), len(FEATURE_COLUMNS))

    def test_imputation_handles_missing_values(self, frame) -> None:
        with_gaps = frame.copy()
        with_gaps.loc[with_gaps.index[:10], "rain_last_7d_mm"] = np.nan

        preprocessor = build_preprocessor(list(FEATURE_COLUMNS))
        transformed = preprocessor.fit_transform(with_gaps[list(FEATURE_COLUMNS)])
        assert np.isfinite(transformed).all()

    def test_scaling_is_robust_to_extremes(self, frame) -> None:
        skewed = frame.copy()
        skewed.loc[skewed.index[0], "rain_last_30d_mm"] = 5000.0

        preprocessor = build_preprocessor(list(FEATURE_COLUMNS))
        transformed = preprocessor.fit_transform(skewed[list(FEATURE_COLUMNS)])
        assert np.isfinite(transformed).all()

    def test_transform_is_deterministic(self, frame) -> None:
        preprocessor = build_preprocessor(list(FEATURE_COLUMNS))
        first = preprocessor.fit_transform(frame[list(FEATURE_COLUMNS)])
        second = preprocessor.fit_transform(frame[list(FEATURE_COLUMNS)])
        assert np.allclose(first, second)


class TestInferenceFeaturesMatchTraining:
    """Training and serving must compute the same features for the same day."""

    def test_columns_and_order_match(self) -> None:
        assert list(build_feature_frame([], datetime(2024, 7, 1).date()).columns) == list(
            FEATURE_COLUMNS
        )

    def test_values_agree_with_the_training_pipeline(self, observations) -> None:
        frame = build_training_frame(observations)
        target_day = pd.Timestamp("2024-06-15")

        history = DistrictHistory(
            district_id=1,
            latitude=19.0,
            longitude=72.0,
            daily_rainfall_mm={
                pd.Timestamp(row["observed_at"]).date(): float(row["rainfall_mm"])
                for _, row in observations[observations["district_id"] == 1].iterrows()
            },
        )
        serving = build_feature_frame([history], target_day.date()).iloc[0]

        # The training row that predicts target_day + 1 uses target_day as its
        # issue date, so it is the same feature vector.
        training = frame[(frame["district_id"] == 1) & (frame["issue_date"] == target_day)].iloc[0]

        for column in FEATURE_COLUMNS:
            if column == "regional_mean_rain_7d_mm":
                continue  # a batch-level mean, covered separately
            assert serving[column] == pytest.approx(training[column], abs=1e-6), column

    def test_regional_term_is_the_batch_mean(self, observations) -> None:
        issue_day = datetime(2024, 6, 15).date()
        histories = [
            DistrictHistory(
                district_id=district,
                latitude=19.0 + district,
                longitude=72.0 + district,
                daily_rainfall_mm={
                    pd.Timestamp(row["observed_at"]).date(): float(row["rainfall_mm"])
                    for _, row in observations[observations["district_id"] == district].iterrows()
                },
            )
            for district in (1, 2, 3)
        ]
        frame = build_feature_frame(histories, issue_day)
        expected = frame["rain_last_7d_mm"].mean()
        assert np.allclose(frame["regional_mean_rain_7d_mm"], expected)

    def test_future_observations_are_ignored_at_serving_time(self, observations) -> None:
        issue_day = datetime(2024, 6, 15).date()
        history = DistrictHistory(
            district_id=1,
            latitude=19.0,
            longitude=72.0,
            daily_rainfall_mm={
                pd.Timestamp(row["observed_at"]).date(): float(row["rainfall_mm"])
                for _, row in observations[observations["district_id"] == 1].iterrows()
            },
        )
        with_future = build_feature_frame([history], issue_day)

        truncated = DistrictHistory(
            district_id=1,
            latitude=19.0,
            longitude=72.0,
            daily_rainfall_mm={
                day: value for day, value in history.daily_rainfall_mm.items() if day < issue_day
            },
        )
        without_future = build_feature_frame([truncated], issue_day)

        # Only the regional term can differ, and it is not a look-ahead.
        pd.testing.assert_frame_equal(
            with_future.drop(columns=["regional_mean_rain_7d_mm"]),
            without_future.drop(columns=["regional_mean_rain_7d_mm"]),
        )

    def test_empty_history_produces_zero_antecedents(self) -> None:
        frame = build_feature_frame(
            [DistrictHistory(district_id=1, latitude=19.0, longitude=72.0)],
            datetime(2024, 6, 15).date(),
        )
        row = frame.iloc[0]
        assert row["antecedent_rain_24h_mm"] == 0.0
        assert row["rain_last_7d_mm"] == 0.0
        assert row["dry_streak_days"] == 0.0
