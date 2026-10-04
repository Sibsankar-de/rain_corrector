"""Baseline models.

A candidate model is only worth its complexity if it beats these. All baselines
are fitted on the same chronological split as the candidates.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin, clone
from sklearn.dummy import DummyRegressor


@dataclass
class BaselineSpec:
    name: str
    description: str
    factory: object


class PersistenceRegressor(RegressorMixin, BaseEstimator):
    """Predicts the previous day's rainfall for the next day.

    Persistence is a strong benchmark for 24h rainfall because monsoon rainfall
    is close to temporally persistent, so models that cannot beat it are not
    adding value.
    """

    def __init__(self) -> None:
        self._mean = 0.0

    def fit(self, x, y=None):
        self._mean = float(np.mean(y)) if y is not None and len(y) else 0.0
        return self

    def predict(self, x):
        if isinstance(x, pd.DataFrame) and "antecedent_rain_24h_mm" in x.columns:
            return x["antecedent_rain_24h_mm"].to_numpy(dtype=float)
        return np.zeros(len(x), dtype=float)


class RollingMeanRegressor(RegressorMixin, BaseEstimator):
    """Predicts the 7-day antecedent mean.

    Smooths persistence; a 7-day mean is a stronger baseline than a single day
    for districts with intermittent but clustered rainfall.
    """

    COLUMN = "rain_last_7d_mm"

    def __init__(self, divisor: float = 7.0) -> None:
        self.divisor = divisor

    def fit(self, x, y=None):
        return self

    def predict(self, x):
        if isinstance(x, pd.DataFrame) and self.COLUMN in x.columns:
            return x[self.COLUMN].to_numpy(dtype=float) / self.divisor
        return np.zeros(len(x), dtype=float)


class DistrictSeasonalRegressor(RegressorMixin, BaseEstimator):
    """District x month climatology computed from the training partition only.

    Fitting the climatology inside `fit` (rather than beforehand) guarantees the
    lookup table never sees validation or test rainfall.
    """

    def __init__(self, month_column: str = "target_month") -> None:
        self.month_column = month_column

    def fit(self, x, y):
        frame = pd.DataFrame(
            {
                "district_id": np.asarray(x["district_id"]),
                "month": np.asarray(x[self.month_column]),
                "y": np.asarray(y, dtype=float),
            }
        )
        self.table_ = frame.groupby(["district_id", "month"])["y"].mean()
        self.global_mean_ = float(frame["y"].mean())
        return self

    def predict(self, x):
        keys = pd.MultiIndex.from_arrays(
            [np.asarray(x["district_id"]), np.asarray(x[self.month_column])]
        )
        values = self.table_.reindex(keys).to_numpy(dtype=float)
        return np.nan_to_num(values, nan=self.global_mean_)


def baseline_estimators() -> dict[str, object]:
    return {
        "persistence": PersistenceRegressor(),
        "rolling_mean_7d": RollingMeanRegressor(),
        "seasonal_climatology": DistrictSeasonalRegressor(),
        "global_mean": DummyRegressor(strategy="mean"),
    }


def baseline_requirements() -> dict[str, list[str]]:
    """Extra columns each baseline needs, beyond the engineered features."""
    return {
        "persistence": [],
        "rolling_mean_7d": [],
        "seasonal_climatology": ["target_month"],
        "global_mean": [],
    }


def make_baseline(name: str) -> BaseEstimator:
    estimators = baseline_estimators()
    if name not in estimators:
        raise KeyError(f"Unknown baseline '{name}'. Available: {sorted(estimators)}")
    return clone(estimators[name])
