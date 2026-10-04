"""Serving-side preprocessing.

Mirrors `rainml.features.engineering.build_training_frame` but takes already
aggregated daily rainfall per district rather than a long observation table.
The backend calls this from `app/ml/features.py`; the two implementations must
produce identical column names, order and semantics, which the shared
`FEATURE_COLUMNS` contract and the ML test suite enforce.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from rainml.features.engineering import EVENT_THRESHOLD_MM, FEATURE_COLUMNS, TARGET_COLUMN

DRY_RAINFALL_MM = 0.1


@dataclass
class DistrictHistory:
    district_id: int | str
    latitude: float
    longitude: float
    daily_rainfall_mm: dict[date, float] = field(default_factory=dict)


def build_feature_frame(
    histories: list[DistrictHistory],
    issue_date: date,
) -> pd.DataFrame:
    """Features for predicting rainfall on `issue_date + horizon`."""
    rows = [_row_features(h, issue_date) for h in histories]
    frame = pd.DataFrame(rows, columns=list(FEATURE_COLUMNS))
    if not frame.empty:
        frame["regional_mean_rain_7d_mm"] = float(frame["rain_last_7d_mm"].mean())
    return frame.astype(float)


def _row_features(history: DistrictHistory, issue_date: date) -> dict[str, float]:
    series = {k: float(v) for k, v in history.daily_rainfall_mm.items() if k < issue_date}
    ordered = sorted(series.items())

    def window(days: int) -> float:
        start = issue_date - timedelta(days=days)
        return float(sum(v for k, v in series.items() if start <= k < issue_date))

    def window_values(days: int) -> list[float]:
        start = issue_date - timedelta(days=days)
        return [v for k, v in ordered if start <= k < issue_date]

    recent = window_values(30)
    dry_streak = 0
    cursor = issue_date
    while (cursor - timedelta(days=1)) in series and series[
        cursor - timedelta(days=1)
    ] < DRY_RAINFALL_MM:
        dry_streak += 1
        cursor -= timedelta(days=1)

    target_date = issue_date + timedelta(days=1)
    doy = target_date.timetuple().tm_yday

    return {
        "lat": history.latitude,
        "lon": history.longitude,
        "doy_sin": float(np.sin(2 * np.pi * doy / 365.25)),
        "doy_cos": float(np.cos(2 * np.pi * doy / 365.25)),
        "rain_last_1d_mm": window(1),
        "rain_last_3d_mm": window(3),
        "rain_last_7d_mm": window(7),
        "rain_last_14d_mm": window(14),
        "rain_last_30d_mm": window(30),
        "dry_streak_days": float(dry_streak),
        "recent_event_count_30d": float(sum(1 for v in recent if v >= EVENT_THRESHOLD_MM)),
        "recent_mean_daily_mm_30d": float(np.mean(recent)) if recent else 0.0,
        # ddof=1 matches pandas' rolling std, which the training frame uses.
        "recent_std_daily_mm_30d": float(np.std(recent, ddof=1)) if len(recent) > 1 else 0.0,
        "recent_max_daily_mm_30d": float(np.max(recent)) if recent else 0.0,
        "antecedent_rain_24h_mm": ordered[-1][1] if ordered else 0.0,
        "antecedent_rain_72h_mm": float(sum(v for _, v in ordered[-3:])),
        "regional_mean_rain_7d_mm": 0.0,
    }


def to_feature_frame(record: dict, issue_time: datetime) -> pd.DataFrame:
    """Convenience wrapper for single-district ad hoc scoring."""
    history = DistrictHistory(
        district_id=int(record["district_id"]),
        latitude=float(record["lat"]),
        longitude=float(record["lon"]),
        daily_rainfall_mm={
            (pd.Timestamp(k).date() if not isinstance(k, date) else k): float(v)
            for k, v in (record.get("daily_rainfall_mm") or {}).items()
        },
    )
    return build_feature_frame([history], issue_time.date())


__all__ = [
    "DistrictHistory",
    "FEATURE_COLUMNS",
    "TARGET_COLUMN",
    "build_feature_frame",
    "to_feature_frame",
]
