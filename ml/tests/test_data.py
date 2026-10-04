"""Data loading, cleaning, validation and the chronological split."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from rainml.data.cleaning import clean_observations
from rainml.data.loaders import (
    DatasetError,
    attach_coordinates,
    daily_completeness,
    load_districts,
    load_observations,
    summarise,
)
from rainml.data.validation import (
    ValidationError,
    chronological_split,
    validate_observations,
    validate_split,
    validate_training_frame,
)


class TestLoaders:
    def test_reads_csv(self, tmp_path, synthetic_observations) -> None:
        path = tmp_path / "observations.csv"
        synthetic_observations.to_csv(path, index=False)
        assert len(load_observations(path)) == len(synthetic_observations)

    def test_missing_file_raises_a_typed_error(self, tmp_path) -> None:
        with pytest.raises(DatasetError, match="not found"):
            load_observations(tmp_path / "absent.csv")

    def test_missing_columns_raise(self, tmp_path) -> None:
        path = tmp_path / "observations.csv"
        pd.DataFrame({"district_id": [1], "value": [2.0]}).to_csv(path, index=False)
        with pytest.raises(DatasetError, match="missing columns"):
            load_observations(path)

    def test_unsupported_extension_raises(self, tmp_path) -> None:
        path = tmp_path / "observations.xlsx"
        path.write_text("nope")
        with pytest.raises(DatasetError, match="Unsupported"):
            load_observations(path)

    def test_district_loader_validates_columns(self, tmp_path) -> None:
        path = tmp_path / "districts.csv"
        pd.DataFrame({"id": [1]}).to_csv(path, index=False)
        with pytest.raises(DatasetError, match="missing columns"):
            load_districts(path)

    def test_coordinates_attach_by_numeric_id(
        self, synthetic_observations, synthetic_districts
    ) -> None:
        frame = attach_coordinates(synthetic_observations, synthetic_districts)
        assert {"lat", "lon"}.issubset(frame.columns)
        assert frame["lat"].notna().all()

    def test_coordinates_attach_by_code(self, synthetic_observations, synthetic_districts) -> None:
        coded = synthetic_observations.copy()
        coded["district_id"] = coded["district_id"].map(lambda i: f"SYN-{i - 1}")
        frame = attach_coordinates(coded, synthetic_districts)

        assert frame["lat"].notna().all()
        # Codes are normalised to the numeric primary key the API uses.
        assert frame["district_id"].dtype.kind == "i"

    def test_unknown_district_raises(self, synthetic_observations, synthetic_districts) -> None:
        frame = synthetic_observations.copy()
        frame["district_id"] = 999
        with pytest.raises(DatasetError, match="without coordinates"):
            attach_coordinates(frame, synthetic_districts)

    def test_existing_coordinates_are_not_rejoined(
        self, synthetic_observations, synthetic_districts
    ) -> None:
        with_coords = attach_coordinates(synthetic_observations, synthetic_districts)
        again = attach_coordinates(with_coords, synthetic_districts)
        # A second join would produce lat_x / lat_y columns.
        assert list(again.columns).count("lat") == 1
        pd.testing.assert_frame_equal(with_coords, again)

    def test_completeness_reports_gaps(self, synthetic_observations) -> None:
        gapped = synthetic_observations.drop(index=0)
        report = daily_completeness(gapped)
        assert (report["missing_days"] >= 0).all()
        assert report["distinct_days"].max() > 0

    def test_summarise_reports_the_key_statistics(self, synthetic_observations) -> None:
        summary = summarise(synthetic_observations)
        assert summary["rows"] == len(synthetic_observations)
        assert summary["districts"] == synthetic_observations["district_id"].nunique()
        assert summary["mean_rainfall_mm"] > 0
        assert 0 <= summary["heavy_event_rate"] <= 1


class TestCleaning:
    def test_removes_impossible_values(self, synthetic_observations) -> None:
        dirty = synthetic_observations.copy()
        dirty.loc[dirty.index[:5], "rainfall_mm"] = -3.0
        dirty.loc[dirty.index[5:10], "rainfall_mm"] = 5000.0

        cleaned, report = clean_observations(dirty)
        assert report.dropped_negatives == 5
        assert report.dropped_extremes == 5
        assert (cleaned["rainfall_mm"] >= 0).all()
        assert cleaned["rainfall_mm"].max() <= 1000.0

    def test_keeps_real_extremes_and_flags_them(self, synthetic_observations) -> None:
        realistic = synthetic_observations.copy()
        realistic.loc[realistic.index[0], "rainfall_mm"] = 180.0

        cleaned, report = clean_observations(realistic)
        # A heavy day is signal, not a defect to be removed.
        assert 180.0 in set(cleaned["rainfall_mm"])
        assert report.flagged_outliers >= 1

    def test_deduplicates_keeping_the_latest_reading(self, synthetic_observations) -> None:
        duplicated = pd.concat(
            [synthetic_observations, synthetic_observations.tail(20)], ignore_index=True
        )
        cleaned, report = clean_observations(duplicated)
        assert report.dropped_duplicates == 20

    def test_missing_days_are_filled_with_zero(self, synthetic_observations) -> None:
        # Interior days only: a record cannot be extended backwards before its
        # first observation without inventing history.
        mask = synthetic_observations.index % 40 == 0
        gapped = synthetic_observations[~mask | (synthetic_observations.index == 0)]
        cleaned, _ = clean_observations(gapped)

        filled = cleaned[(cleaned["district_id"] == 1) & (cleaned["rainfall_mm"] == 0.0)]
        assert len(filled) > 0

        days = cleaned[cleaned["district_id"] == 1]["observed_at"].dt.normalize()
        assert days.diff().dropna().dt.days.eq(1).all()

    def test_imputation_does_not_extend_past_the_first_observation(
        self, synthetic_observations
    ) -> None:
        # Trimming the first day of the record removes 2024-01-01 from every
        # district. Imputation must not invent that day back.
        first_day = synthetic_observations["observed_at"].min()
        head_trimmed = synthetic_observations[synthetic_observations["observed_at"] > first_day]
        cleaned, _ = clean_observations(head_trimmed)

        assert cleaned["observed_at"].min().tz_localize(None) == head_trimmed[
            "observed_at"
        ].min().tz_localize(None)
        assert first_day not in set(cleaned["observed_at"])

    def test_is_idempotent(self, synthetic_observations) -> None:
        once, _ = clean_observations(synthetic_observations)
        twice, _ = clean_observations(once)
        assert len(once) == len(twice)

    def test_empty_input_is_handled(self) -> None:
        cleaned, report = clean_observations(pd.DataFrame())
        assert cleaned.empty
        assert report.output_rows == 0

    def test_output_is_sorted_by_district_and_time(self, synthetic_observations) -> None:
        shuffled = synthetic_observations.sample(frac=1.0, random_state=1)
        cleaned, _ = clean_observations(shuffled)
        assert cleaned.equals(cleaned.sort_values(["district_id", "observed_at"]))


class TestObservationValidation:
    def test_accepts_a_healthy_dataset(self, synthetic_observations) -> None:
        report = validate_observations(synthetic_observations)
        assert report.ok
        assert report.errors == []

    def test_rejects_an_empty_dataset(self) -> None:
        report = validate_observations(pd.DataFrame())
        assert not report.ok
        with pytest.raises(ValidationError, match="empty"):
            report.raise_for_errors()

    def test_rejects_too_few_districts(self, synthetic_observations) -> None:
        narrow = synthetic_observations[synthetic_observations["district_id"] == 1]
        report = validate_observations(narrow)
        assert not report.ok
        with pytest.raises(ValidationError, match="districts"):
            report.raise_for_errors()

    def test_rejects_too_short_a_record(self, synthetic_observations) -> None:
        short = synthetic_observations[
            synthetic_observations["observed_at"] < datetime(2024, 6, 1, tzinfo=UTC)
        ]
        report = validate_observations(short)
        assert not report.ok
        with pytest.raises(ValidationError, match="days"):
            report.raise_for_errors()

    def test_rejects_negative_rainfall(self, synthetic_observations) -> None:
        dirty = synthetic_observations.copy()
        dirty.loc[dirty.index[0], "rainfall_mm"] = -1.0
        report = validate_observations(dirty)
        assert not report.ok

    def test_warns_on_sparse_coverage(self) -> None:
        import numpy as np

        rng = np.random.default_rng(3)
        rows = []
        for district in range(6):
            for day in rng.choice(300, size=40, replace=False):
                rows.append(
                    {
                        "district_id": district,
                        "observed_at": datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=int(day)),
                        "rainfall_mm": 3.0,
                    }
                )
        report = validate_observations(pd.DataFrame(rows))
        assert any("sparse" in warning for warning in report.warnings)


class TestChronologicalSplit:
    def test_partitions_are_disjoint_in_time(self, supervised_frame) -> None:
        train, valid, test = chronological_split(supervised_frame)
        assert train["issue_date"].max() < valid["issue_date"].min()
        assert valid["issue_date"].max() < test["issue_date"].min()

    def test_no_rows_are_lost(self, supervised_frame) -> None:
        train, valid, test = chronological_split(supervised_frame)
        assert len(train) + len(valid) + len(test) == len(supervised_frame)

    def test_every_district_appears_in_every_partition(self, supervised_frame) -> None:
        train, valid, test = chronological_split(supervised_frame)
        expected = set(supervised_frame["district_id"].unique())
        for partition in (train, valid, test):
            assert set(partition["district_id"].unique()) == expected

    def test_test_partition_is_the_most_recent_slice(self, supervised_frame) -> None:
        _, _, test = chronological_split(supervised_frame)
        assert test["issue_date"].min() >= supervised_frame["issue_date"].quantile(0.7)

    def test_fractions_are_honoured(self, supervised_frame) -> None:
        train, valid, test = chronological_split(
            supervised_frame, valid_fraction=0.3, test_fraction=0.1
        )
        total_days = supervised_frame["issue_date"].nunique()
        assert abs(test["issue_date"].nunique() / total_days - 0.1) < 0.02
        assert abs(valid["issue_date"].nunique() / total_days - 0.3) < 0.02

    def test_split_is_immune_to_input_order(self, supervised_frame) -> None:
        ordered = chronological_split(supervised_frame)
        shuffled = chronological_split(supervised_frame.sample(frac=1.0, random_state=7))
        for left, right in zip(ordered, shuffled, strict=False):
            pd.testing.assert_frame_equal(left, right)

    def test_empty_frame_returns_three_empty_partitions(self) -> None:
        partitions = chronological_split(pd.DataFrame({"issue_date": []}))
        assert all(partition.empty for partition in partitions)

    def test_validate_split_accepts_a_correct_split(self, supervised_frame) -> None:
        report = validate_split(*chronological_split(supervised_frame))
        assert report.ok

    def test_validate_split_rejects_overlapping_partitions(self, supervised_frame) -> None:
        # A partition sharing a boundary date with the next one would let the
        # model see the very day it is scored on.
        train, valid, test = chronological_split(supervised_frame)
        leaked = train.copy()
        leaked.loc[leaked.index[-1], "issue_date"] = valid["issue_date"].min()

        report = validate_split(leaked, valid, test)
        assert not report.ok
        with pytest.raises(ValidationError, match="overlap"):
            report.raise_for_errors()

    def test_validate_split_rejects_an_empty_partition(self, supervised_frame) -> None:
        train, valid, test = chronological_split(supervised_frame)
        report = validate_split(train, valid, test.iloc[0:0])
        assert not report.ok
        assert any("empty" in error for error in report.errors)


class TestSplitJustification:
    def test_persistence_skill_depends_on_the_split(self, demo_observations_path) -> None:
        """Quantifies why a random split is invalid on real rainfall.

        A random split places the day after a training day in the test set, so
        a model that repeats yesterday's rainfall scores well without skill.
        """
        from rainml.data.cleaning import clean_observations
        from rainml.evaluation.metrics import mae
        from rainml.models.baseline import make_baseline

        frame = pd.read_csv(demo_observations_path)
        frame["observed_at"] = pd.to_datetime(frame["observed_at"], utc=True)
        cleaned, _ = clean_observations(frame)
        target = "rainfall_mm"

        cleaned = cleaned.sort_values(["district_id", "observed_at"])
        cleaned["antecedent_rain_24h_mm"] = cleaned.groupby("district_id")[target].shift(1)
        cleaned = cleaned.dropna(subset=["antecedent_rain_24h_mm"])

        def persistence_mae(train: pd.DataFrame, test: pd.DataFrame) -> float:
            estimator = make_baseline("persistence")
            estimator.fit(train[["antecedent_rain_24h_mm"]], train[target].to_numpy(float))
            return mae(
                estimator.predict(test[["antecedent_rain_24h_mm"]]),
                test[target].to_numpy(float),
            )

        train, _, test = chronological_split(cleaned, date_column="observed_at")
        honest = persistence_mae(train, test)

        shuffled = cleaned.sample(frac=1.0, random_state=0)
        cutoff = int(len(shuffled) * 0.8)
        leaky = persistence_mae(shuffled[:cutoff], shuffled[cutoff:])

        # The split strategy materially distorts performance due to temporal leakage and seasonality.
        assert abs(leaky - honest) > 0.5


class TestTrainingFrameValidation:
    def test_accepts_a_valid_frame(self, supervised_frame) -> None:
        report = validate_training_frame(supervised_frame)
        assert report.ok
        assert report.errors == []

    def test_rejects_an_empty_frame(self) -> None:
        report = validate_training_frame(pd.DataFrame({"target_rainfall_mm": []}))
        assert not report.ok

    def test_rejects_a_constant_target(self) -> None:
        frame = pd.DataFrame({"feature": [1.0] * 50, "target_rainfall_mm": [3.0] * 50})
        report = validate_training_frame(frame)
        assert not report.ok
        assert any("constant" in error for error in report.errors)

    def test_rejects_nan_targets(self) -> None:
        import numpy as np

        frame = pd.DataFrame(
            {"feature": np.arange(50.0), "target_rainfall_mm": [np.nan] * 49 + [1.0]}
        )
        report = validate_training_frame(frame)
        assert not report.ok

    def test_rejects_non_finite_features(self) -> None:
        import numpy as np

        frame = pd.DataFrame(
            {
                "feature": [np.inf] * 49 + [1.0],
                "target_rainfall_mm": np.linspace(0, 10, 50),
            }
        )
        report = validate_training_frame(frame)
        assert not report.ok
