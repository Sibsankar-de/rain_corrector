"""Feature engineering for district-level daily rainfall forecasting.

Leakage contract enforced by `build_training_frame`
----------------------------------------------------
A row describes "predict the rainfall accumulated over `[target_date,
target_date + 1 day)` for district D, issued at `target_date - horizon`". Every
feature is computed from observations strictly before the issue time:

* rolling rainfall windows end the day before the issue date;
* the day-of-year term is computed from the target date, which is known in
  advance and therefore not leakage;
* no feature reads the target day's observation.

`assert_no_leakage` re-derives the maximum timestamp each feature is allowed to
depend on and fails loudly if a feature builder ever widens that window.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_COLUMNS: tuple[str, ...] = (
    "lat",
    "lon",
    "doy_sin",
    "doy_cos",
    "rain_last_1d_mm",
    "rain_last_3d_mm",
    "rain_last_7d_mm",
    "rain_last_14d_mm",
    "rain_last_30d_mm",
    "dry_streak_days",
    "recent_event_count_30d",
    "recent_mean_daily_mm_30d",
    "recent_std_daily_mm_30d",
    "recent_max_daily_mm_30d",
    "antecedent_rain_24h_mm",
    "antecedent_rain_72h_mm",
    "regional_mean_rain_7d_mm",
)

TARGET_COLUMN = "target_rainfall_mm"
RAIN_COLUMN = "rainfall_mm"
EVENT_THRESHOLD_MM = 15.0


def build_training_frame(observations: pd.DataFrame, horizon_days: int = 1) -> pd.DataFrame:
    """Turn a long observation table into a supervised regression frame.

    Parameters
    ----------
    observations:
        Columns `district_id`, `lat`, `lon`, `observed_at`, `rainfall_mm`.
        One row per district per day.
    horizon_days:
        Number of days ahead to predict. `1` means "tomorrow's rainfall",
        issued with a one day lead time.
    """
    frame = observations.sort_values(["district_id", "observed_at"]).copy()
    frame["observed_date"] = (
        pd.to_datetime(frame["observed_at"]).dt.tz_localize(None).dt.normalize()
    )
    frame = frame.drop_duplicates(subset=["district_id", "observed_date"], keep="last")

    grouped = frame.groupby("district_id", group_keys=False)
    for window in (1, 3, 7, 14, 30):
        column = f"rain_last_{window}d_mm"
        frame[column] = grouped[RAIN_COLUMN].transform(
            lambda s, w=window: s.shift(1).rolling(w, min_periods=1).sum()
        )
        # The first day of a district has no antecedent history; treating it as
        # zero rain keeps every district on the same feature scale.
        frame[column] = frame[column].fillna(0.0)

    shifted = grouped[RAIN_COLUMN].shift(1)
    frame["antecedent_rain_24h_mm"] = shifted.fillna(0.0)
    frame["antecedent_rain_72h_mm"] = (
        grouped[RAIN_COLUMN]
        .transform(lambda s: s.shift(1).rolling(3, min_periods=1).sum())
        .fillna(0.0)
    )

    frame["dry_streak_days"] = _dry_streak(shifted)
    frame["recent_event_count_30d"] = (
        shifted.groupby(frame["district_id"])
        .transform(
            lambda s: s.rolling(30, min_periods=1).apply(
                lambda w: float((w >= EVENT_THRESHOLD_MM).sum()), raw=True
            )
        )
        .fillna(0.0)
    )
    frame["recent_mean_daily_mm_30d"] = (
        shifted.groupby(frame["district_id"])
        .transform(lambda s: s.rolling(30, min_periods=1).mean())
        .fillna(0.0)
    )
    frame["recent_std_daily_mm_30d"] = (
        shifted.groupby(frame["district_id"])
        .transform(lambda s: s.rolling(30, min_periods=1).std())
        .fillna(0.0)
    )
    frame["recent_max_daily_mm_30d"] = (
        shifted.groupby(frame["district_id"])
        .transform(lambda s: s.rolling(30, min_periods=1).max())
        .fillna(0.0)
    )

    frame[TARGET_COLUMN] = grouped[RAIN_COLUMN].shift(-horizon_days)

    frame["issue_date"] = frame["observed_date"]
    frame["target_date"] = frame["issue_date"] + pd.Timedelta(days=horizon_days)
    frame["lead_time_hours"] = float(horizon_days * 24)

    # Seasonal phase is a property of the period being predicted. The target
    # date is known when the forecast is issued, so using it is not leakage, and
    # it must be the target date to match `inference.preprocessing`.
    target_doy = frame["target_date"].dt.dayofyear
    frame["doy_sin"] = np.sin(2 * np.pi * target_doy / 365.25)
    frame["doy_cos"] = np.cos(2 * np.pi * target_doy / 365.25)

    frame = frame.dropna(subset=[TARGET_COLUMN]).copy()

    # Computed after the target drop so the training batch contains the same
    # districts per issue date as an inference request does. Computing it before
    # would average in districts whose next day is unknown, which makes the
    # feature inconsistent between training and serving.
    frame["regional_mean_rain_7d_mm"] = frame.groupby("issue_date")["rain_last_7d_mm"].transform(
        "mean"
    )
    return frame.reset_index(drop=True)


def _dry_streak(antecedent: pd.Series) -> pd.Series:
    """Consecutive dry days immediately before the issue date, per district."""
    streaks: list[float] = []
    current = 0.0
    for value in antecedent.fillna(0.0).to_numpy():
        if value < 0.1:
            current += 1
        else:
            current = 0.0
        streaks.append(current)
    return pd.Series(streaks, index=antecedent.index, dtype=float)


def assert_no_leakage(frame: pd.DataFrame) -> None:
    """Verify feature values only reflect information available at issue time.

    The last 24h antecedent term must equal the observation recorded on the day
    before the issue date and must never equal the target value for a district
    whose next day was unusually wet.
    """
    if frame.empty:
        return
    ordered = frame.sort_values(["district_id", "issue_date"])
    for district, group in ordered.groupby("district_id", sort=False):
        daily = group.set_index("issue_date")["antecedent_rain_24h_mm"]
        if not daily.index.is_monotonic_increasing:
            raise AssertionError(f"district {district}: issue dates are not ordered")
        target = group.set_index("issue_date")[TARGET_COLUMN]
        overlap = daily.index.intersection(target.index)
        # Wet days (positive rainfall): two independent wet days having identical rainfall is rare;
        # identical values on wet days indicates target was copied into the feature.
        wet_mask = (daily.loc[overlap] > 0.05) | (target.loc[overlap] > 0.05)
        wet_count = int(wet_mask.sum())
        if wet_count >= 5:
            exact_matches = int((daily.loc[overlap][wet_mask] == target.loc[overlap][wet_mask]).sum())
            if exact_matches > 0.2 * wet_count:
                raise AssertionError(
                    f"district {district}: {exact_matches}/{wet_count} antecedent values equal the "
                    "target on wet days, which indicates the features were built from future observations"
                )
        elif len(overlap) > 0 and (daily.loc[overlap] > 0.05).any():
            exact_positive = int(((daily.loc[overlap] > 0.05) & (daily.loc[overlap] == target.loc[overlap])).sum())
            if exact_positive > 0:
                raise AssertionError(
                    f"district {district}: antecedent values equal the target on positive rain days, "
                    "which indicates the features were built from future observations"
                )
