"""Dataset validation gates applied before training.

Validation raises instead of warning: a training run on invalid data produces a
model card with meaningless metrics, which is worse than a failed run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from rainml.data.loaders import summarise

MIN_ROWS = 500
MIN_DISTRICTS = 5
MIN_DISTINCT_DAYS = 180
TARGET_MIN_ROWS = 200
MAX_MISSING_FRACTION = 0.35


class ValidationError(ValueError):
    """Raised when the dataset cannot support a training run."""


@dataclass
class ValidationReport:
    ok: bool = True
    summary: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def raise_for_errors(self) -> None:
        if self.errors:
            raise ValidationError("; ".join(self.errors))


def validate_observations(frame: pd.DataFrame) -> ValidationReport:
    report = ValidationReport()
    if frame.empty:
        report.ok = False
        report.errors.append("observation dataset is empty")
        return report

    report.summary = summarise(frame)

    if len(frame) < MIN_ROWS:
        report.errors.append(f"only {len(frame)} rows, need at least {MIN_ROWS}")
    districts = int(frame["district_id"].nunique())
    if districts < MIN_DISTRICTS:
        report.errors.append(f"only {districts} districts, need at least {MIN_DISTRICTS}")
    days = int(pd.to_datetime(frame["observed_at"]).dt.normalize().nunique())
    if days < MIN_DISTINCT_DAYS:
        report.errors.append(f"only {days} distinct days, need at least {MIN_DISTINCT_DAYS}")

    missing = float(frame["rainfall_mm"].isna().mean())
    if missing > MAX_MISSING_FRACTION:
        report.errors.append(f"{missing:.1%} of rainfall values are missing")
    elif missing > 0:
        report.warnings.append(f"{missing:.1%} of rainfall values are missing")

    if (frame["rainfall_mm"] < 0).any():
        report.errors.append("negative rainfall values present")
    if float(frame["rainfall_mm"].max()) > 1000:
        report.errors.append("rainfall values above the physical daily maximum")

    if days > 0 and len(frame) / max(districts, 1) / days < 0.6:
        report.warnings.append(
            "sparse coverage: average district has fewer than 60% of the calendar days"
        )

    report.ok = not report.errors
    return report


def validate_training_frame(
    frame: pd.DataFrame, target: str = "target_rainfall_mm"
) -> ValidationReport:
    report = ValidationReport()
    if frame.empty:
        report.ok = False
        report.errors.append("training frame is empty after feature construction")
        return report
    if len(frame) < TARGET_MIN_ROWS:
        report.errors.append(f"only {len(frame)} supervised rows, need at least {TARGET_MIN_ROWS}")
    if frame[target].isna().any():
        report.errors.append("target column contains NaN")

    spread = float(frame[target].std())
    if np.isclose(spread, 0.0):
        report.errors.append("target column is constant; the model cannot be trained")
    elif spread < 1e-3:
        report.warnings.append(f"target standard deviation is very low ({spread:.5f} mm)")

    non_finite = ~np.isfinite(frame.select_dtypes(include=[np.number]).to_numpy(dtype=float))
    if non_finite.any():
        report.errors.append("feature matrix contains NaN or infinite values")
    report.ok = not report.errors
    return report


def validate_split(
    train: pd.DataFrame,
    valid: pd.DataFrame,
    test: pd.DataFrame,
    date_column: str = "issue_date",
) -> ValidationReport:
    """Confirm the three partitions are disjoint in time and in time order.

    The partitions are passed in rather than recomputed, so this actually
    inspects what will be fitted instead of a fresh split of the same rows.
    """
    report = ValidationReport()

    if train.empty or valid.empty or test.empty:
        report.ok = False
        report.errors.append("a chronological partition is empty")
        return report

    train_max = train[date_column].max()
    valid_min = valid[date_column].min()
    valid_max = valid[date_column].max()
    test_min = test[date_column].min()
    if not (train_max < valid_min <= valid_max < test_min):
        report.ok = False
        report.errors.append(
            f"partitions overlap in time: train<={train_max}, "
            f"valid={valid_min}..{valid_max}, test>={test_min}"
        )

    combined = pd.concat([train, valid, test], ignore_index=True)
    if len(combined.drop_duplicates()) != len(combined):
        report.ok = False
        report.errors.append("partitions contain duplicate rows")

    report.ok = report.ok and not report.errors
    return report


def chronological_split(
    frame: pd.DataFrame,
    date_column: str = "issue_date",
    valid_fraction: float = 0.2,
    test_fraction: float = 0.2,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split on date boundaries, never on row counts.

    Rainfall is strongly autocorrelated day to day; a random split lets the
    model see near-duplicates of its own test rows and reports inflated skill.

    Every district contributes a row for the same issue date, so cutting by row
    count would slice *through* a date and leave the same day in two partitions.
    The split therefore picks whole dates: the fraction is measured in distinct
    days, and each partition contains every district's rows for its days.
    """
    if frame.empty:
        empty = frame.reset_index(drop=True)
        return empty, empty, empty

    # District is the tie-breaker because every district shares an issue date;
    # without it, the order within a day depends on the input order and the
    # split is not reproducible.
    sort_keys = [date_column] + (["district_id"] if "district_id" in frame.columns else [])
    ordered = frame.sort_values(sort_keys).reset_index(drop=True)
    unique_dates = pd.Index(ordered[date_column].dropna().unique()).sort_values()
    total_days = len(unique_dates)
    if total_days < 3:
        empty = ordered.iloc[0:0]
        return ordered, empty, empty

    test_days = max(int(round(total_days * test_fraction)), 1)
    valid_days = max(int(round(total_days * valid_fraction)), 1)
    while test_days + valid_days >= total_days:
        valid_days = max(valid_days - 1, 1)
        test_days = max(test_days - 1, 1)

    test_start_date = unique_dates[total_days - test_days]
    valid_start_date = unique_dates[total_days - test_days - valid_days]

    train = ordered[ordered[date_column] < valid_start_date]
    valid = ordered[
        (ordered[date_column] >= valid_start_date) & (ordered[date_column] < test_start_date)
    ]
    test = ordered[ordered[date_column] >= test_start_date]
    return (
        train.reset_index(drop=True),
        valid.reset_index(drop=True),
        test.reset_index(drop=True),
    )
