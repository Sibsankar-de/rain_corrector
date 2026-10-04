"""Verification metrics for rainfall forecasts.

Two families are computed because they answer different questions:

* continuous scores (MAE, RMSE, bias, NSE) measure millimetre error, which is
  what a drainage or crop advisor needs;
* categorical scores (POD, FAR, CSI, Brier) measure event detection against a
  heavy-rain threshold, which is what an alert consumer needs.

Rainfall is intermittent, so aggregate continuous scores alone are dominated by
dry days; the categorical breakdown is reported alongside them rather than
instead of them.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

DEFAULT_EVENT_THRESHOLD_MM = 15.0
EPS = 1e-9


def mae(forecast: np.ndarray, observed: np.ndarray) -> float:
    return float(np.mean(np.abs(_as_array(observed) - _as_array(forecast))))


def rmse(forecast: np.ndarray, observed: np.ndarray) -> float:
    error = _as_array(observed) - _as_array(forecast)
    return float(np.sqrt(np.mean(np.square(error))))


def bias(forecast: np.ndarray, observed: np.ndarray) -> float:
    """Mean signed forecast error.

    Positive bias means the model over-forecast, which is the convention used by
    the WWRP verification guidance.
    """
    return float(np.mean(_as_array(forecast) - _as_array(observed)))


def nash_sutcliffe_efficiency(forecast: np.ndarray, observed: np.ndarray) -> float | None:
    f, o = _as_array(forecast), _as_array(observed)
    if f.size < 2:
        return None
    denominator = float(np.sum(np.square(o - np.mean(o))))
    if denominator <= EPS:
        return None
    return float(1.0 - np.sum(np.square(o - f)) / denominator)


def event_counts(
    forecast: np.ndarray, observed: np.ndarray, threshold_mm: float = DEFAULT_EVENT_THRESHOLD_MM
) -> dict[str, int]:
    f = _as_array(forecast) >= threshold_mm
    o = _as_array(observed) >= threshold_mm
    return {
        "hits": int(np.sum(f & o)),
        "false_alarms": int(np.sum(f & ~o)),
        "misses": int(np.sum(~f & o)),
        "correct_negatives": int(np.sum(~f & ~o)),
    }


def categorical_scores(
    forecast: np.ndarray, observed: np.ndarray, threshold_mm: float = DEFAULT_EVENT_THRESHOLD_MM
) -> dict[str, float | int | None]:
    counts = event_counts(forecast, observed, threshold_mm)
    hits, fa, misses, cn = (
        counts["hits"],
        counts["false_alarms"],
        counts["misses"],
        counts["correct_negatives"],
    )
    total = hits + fa + misses + cn
    if total == 0:
        return {
            "pod": None,
            "far": None,
            "csi": None,
            "hit_rate": None,
            "base_rate": None,
            **counts,
        }
    return {
        "pod": _safe_ratio(hits, hits + misses),
        "far": _safe_ratio(fa, hits + fa),
        "csi": _safe_ratio(hits, total),
        "hit_rate": _safe_ratio(hits + cn, total),
        "base_rate": _safe_ratio(hits + misses, total),
        **counts,
    }


def brier_score(
    forecast: np.ndarray, observed: np.ndarray, threshold_mm: float = DEFAULT_EVENT_THRESHOLD_MM
) -> float:
    """Mean squared error of the implied event probability.

    The regressor predicts millimetres, so the event probability is derived by
    clipping the rainfall ratio to [0, 1]. This keeps the pipeline a single
    regressor while still producing a probabilistic score.
    """
    f = np.clip(_as_array(forecast) / max(threshold_mm, EPS), 0.0, 1.0)
    o = (_as_array(observed) >= threshold_mm).astype(float)
    return float(np.mean(np.square(f - o)))


def skill_score(value: float, reference: float) -> float | None:
    """1 - value/reference, the standard skill score against a reference forecast."""
    if reference is None or math.isclose(reference, 0.0, abs_tol=EPS):
        return None
    return float(1.0 - value / reference)


def evaluate(
    forecast: np.ndarray,
    observed: np.ndarray,
    threshold_mm: float = DEFAULT_EVENT_THRESHOLD_MM,
) -> dict[str, float | int | None]:
    f, o = _as_array(forecast), _as_array(observed)
    mean_absolute = mae(f, o)
    scores: dict[str, float | int | None] = {
        "sample_size": int(f.size),
        "mae_mm": round(mean_absolute, 4),
        "rmse_mm": round(rmse(f, o), 4),
        "bias_mm": round(bias(f, o), 4),
        "nash_sutcliffe": _round_or_none(nash_sutcliffe_efficiency(f, o)),
        "brier_score": round(brier_score(f, o, threshold_mm), 6),
    }
    scores.update(
        {
            k: _round_or_none(v) if isinstance(v, float) else v
            for k, v in categorical_scores(f, o, threshold_mm).items()
        }
    )
    return scores


def evaluate_by_group(
    frame: pd.DataFrame,
    forecast_column: str = "prediction",
    observed_column: str = "target_rainfall_mm",
    group_column: str = "group",
    threshold_mm: float = DEFAULT_EVENT_THRESHOLD_MM,
) -> dict[str, dict[str, float | int | None]]:
    out: dict[str, dict[str, float | int | None]] = {}
    for group, subset in frame.groupby(group_column, sort=True):
        out[str(group)] = evaluate(
            subset[forecast_column].to_numpy(dtype=float),
            subset[observed_column].to_numpy(dtype=float),
            threshold_mm,
        )
    return out


def add_target_month(frame: pd.DataFrame, date_column: str = "target_date") -> pd.DataFrame:
    """Month of the target period, required by the seasonal-climatology baseline."""
    result = frame.copy()
    result["target_month"] = pd.to_datetime(result[date_column]).dt.month
    return result


def _as_array(values) -> np.ndarray:
    if isinstance(values, pd.Series):
        return values.to_numpy(dtype=float)
    return np.asarray(values, dtype=float)


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= EPS:
        return None
    return float(numerator / denominator)


def _round_or_none(value):
    return None if value is None else round(float(value), 6)
