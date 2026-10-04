"""Observation cleaning.

Rainfall gauges report real extremes; a blanket outlier filter would delete
exactly the events the model must learn. Cleaning therefore removes only
impossible values and duplicates, and flags statistical outliers for review
instead of dropping them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

IMPOSSIBLE_NEGATIVE_MM = -0.5
PHYSICAL_MAX_MM_PER_DAY = 1000.0
DUPLICATE_KEY = ["district_id", "observed_at"]


@dataclass
class CleaningReport:
    input_rows: int
    output_rows: int
    dropped_negatives: int = 0
    dropped_extremes: int = 0
    dropped_duplicates: int = 0
    imputed_values: int = 0
    flagged_outliers: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def dropped_rows(self) -> int:
        return self.input_rows - self.output_rows


def clean_observations(
    frame: pd.DataFrame,
    clip_max_mm: float = PHYSICAL_MAX_MM_PER_DAY,
    impute_missing_days: bool = True,
) -> tuple[pd.DataFrame, CleaningReport]:
    working = frame.copy()
    report = CleaningReport(input_rows=len(working), output_rows=0)
    if working.empty:
        report.output_rows = 0
        return working, report

    working["observed_at"] = pd.to_datetime(working["observed_at"], utc=True)
    working["rainfall_mm"] = pd.to_numeric(working["rainfall_mm"], errors="coerce")

    before = len(working)
    working = working.dropna(subset=["district_id", "observed_at", "rainfall_mm"])
    if len(working) != before:
        report.notes.append("dropped rows with unparseable district, timestamp or rainfall")

    negatives = working["rainfall_mm"] < IMPOSSIBLE_NEGATIVE_MM
    report.dropped_negatives = int(negatives.sum())
    working = working[~negatives]

    extremes = working["rainfall_mm"] > clip_max_mm
    report.dropped_extremes = int(extremes.sum())
    working = working[~extremes]

    before = len(working)
    working = working.drop_duplicates(subset=DUPLICATE_KEY, keep="last")
    report.dropped_duplicates = before - len(working)

    working = _flag_outliers(working, report)

    if impute_missing_days and not working.empty:
        before = len(working)
        working = _fill_daily_gaps(working)
        report.imputed_values = (len(working) - before) + int(working.attrs.get("imputed_rows", 0))

    working = working.sort_values(["district_id", "observed_at"]).reset_index(drop=True)
    report.output_rows = len(working)
    return working, report


def _flag_outliers(frame: pd.DataFrame, report: CleaningReport) -> pd.DataFrame:
    if len(frame) < 8:
        return frame
    values = frame["rainfall_mm"].to_numpy(dtype=float)
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    if mad == 0:
        return frame
    modified_z = 0.6745 * (values - median) / mad
    frame = frame.assign(is_outlier=modified_z > 6.0)
    report.flagged_outliers = int(frame["is_outlier"].sum())
    return frame


def _fill_daily_gaps(frame: pd.DataFrame) -> pd.DataFrame:
    """Insert zero-rainfall rows for missing calendar days.

    A day with no reading is treated as zero accumulation: a gap in a daily
    gauge series means no measurable rain, and imputing anything else would bias
    the rolling windows upward.
    """
    pieces: list[pd.DataFrame] = []
    for district_id, group in frame.groupby("district_id", sort=False):
        group = group.sort_values("observed_at")
        normalised = group["observed_at"].dt.tz_localize(None).dt.normalize()
        full = pd.date_range(normalised.min(), normalised.max(), freq="D")
        if len(full) == len(normalised.unique()):
            pieces.append(group.drop(columns=["observed_at"]).assign(observed_at=normalised))
            continue

        indexed = group.drop(columns=["observed_at"]).assign(observed_at=normalised)
        indexed = indexed.groupby("observed_at", as_index=False).first()
        reindexed = (
            indexed.set_index("observed_at").reindex(full).rename_axis("observed_at").reset_index()
        )
        reindexed["district_id"] = district_id
        reindexed["rainfall_mm"] = reindexed["rainfall_mm"].fillna(0.0)
        for column in ("lat", "lon"):
            if column in reindexed.columns:
                reindexed[column] = reindexed[column].ffill().bfill()
        pieces.append(reindexed)

    result = pd.concat(pieces, ignore_index=True)
    result.attrs["imputed_rows"] = int(result["rainfall_mm"].isna().sum())
    return result
