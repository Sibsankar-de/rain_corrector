"""Verification metric computation.

Continuous scores use rainfall in millimetres; categorical scores use the
standard "heavy rain" event definition (forecast and observed both >= event
threshold). Definitions follow WWRP/WGNE verification practice so the numbers
are comparable with published work.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

DEFAULT_EVENT_THRESHOLD_MM = 15.0


@dataclass
class ContinuousMetrics:
    sample_size: int
    mean_error_mm: float
    mean_absolute_error_mm: float
    rmse_mm: float
    bias_mm: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "sample_size": self.sample_size,
            "mean_error_mm": round(self.mean_error_mm, 4),
            "mean_absolute_error_mm": round(self.mean_absolute_error_mm, 4),
            "rmse_mm": round(self.rmse_mm, 4),
            "bias_mm": round(self.bias_mm, 4),
        }


@dataclass
class CategoricalCounts:
    hits: int = 0
    false_alarms: int = 0
    misses: int = 0
    correct_negatives: int = 0

    @property
    def total(self) -> int:
        return self.hits + self.false_alarms + self.misses + self.correct_negatives

    def to_dict(self) -> dict[str, float | int]:
        return {
            "hits": self.hits,
            "false_alarms": self.false_alarms,
            "misses": self.misses,
            "correct_negatives": self.correct_negatives,
            "event_base_rate": (
                round((self.hits + self.misses) / self.total, 4) if self.total else 0.0
            ),
        }


@dataclass
class CategoricalMetrics:
    """Categorical scores. Each is None when its denominator is empty.

    Reporting 0.0 for an undefined ratio would be a claim about skill that the
    sample cannot support, so undefined scores stay None.
    """

    pod: float | None
    far: float | None
    csi: float | None
    hit_rate: float | None
    brier_score: float | None
    base_rate: float | None
    counts: CategoricalCounts = field(default_factory=CategoricalCounts)

    def to_dict(self) -> dict[str, float | int | None]:
        return {
            "pod": _round(self.pod),
            "far": _round(self.far),
            "csi": _round(self.csi),
            "hit_rate": _round(self.hit_rate),
            "brier_score": _round(self.brier_score, 6),
            "base_rate": _round(self.base_rate),
            **self.counts.to_dict(),
        }


def continuous_metrics(forecast: np.ndarray, observed: np.ndarray) -> ContinuousMetrics:
    f = np.asarray(forecast, dtype=float)
    o = np.asarray(observed, dtype=float)
    if f.size == 0:
        return ContinuousMetrics(0, 0.0, 0.0, 0.0, 0.0)
    error = o - f
    return ContinuousMetrics(
        sample_size=int(f.size),
        mean_error_mm=float(np.mean(error)),
        mean_absolute_error_mm=float(np.mean(np.abs(error))),
        rmse_mm=float(np.sqrt(np.mean(np.square(error)))),
        bias_mm=float(np.mean(f - o)),
    )


def nash_sutcliffe_efficiency(forecast: np.ndarray, observed: np.ndarray) -> float | None:
    """NSE against a climatological (observed mean) reference.

    Returns None when the denominator degenerates (no variance in observations),
    which is the correct handling rather than reporting 0.0.
    """
    f = np.asarray(forecast, dtype=float)
    o = np.asarray(observed, dtype=float)
    if f.size < 2:
        return None
    denominator = float(np.sum(np.square(o - np.mean(o))))
    if denominator == 0:
        return None
    return float(1.0 - np.sum(np.square(o - f)) / denominator)


def categorical_counts(
    forecast: np.ndarray,
    observed: np.ndarray,
    threshold_mm: float = DEFAULT_EVENT_THRESHOLD_MM,
) -> CategoricalCounts:
    f = np.asarray(forecast, dtype=float) >= threshold_mm
    o = np.asarray(observed, dtype=float) >= threshold_mm
    return CategoricalCounts(
        hits=int(np.sum(f & o)),
        false_alarms=int(np.sum(f & ~o)),
        misses=int(np.sum(~f & o)),
        correct_negatives=int(np.sum(~f & ~o)),
    )


def _ratio(numerator: float, denominator: float) -> float | None:
    return None if denominator == 0 else numerator / denominator


def _round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def categorical_metrics(
    forecast: np.ndarray,
    observed: np.ndarray,
    threshold_mm: float = DEFAULT_EVENT_THRESHOLD_MM,
) -> CategoricalMetrics:
    f = np.asarray(forecast, dtype=float)
    o = np.asarray(observed, dtype=float)
    counts = categorical_counts(f, o, threshold_mm)
    if f.size == 0:
        return CategoricalMetrics(None, None, None, None, None, None, counts)

    brier = float(np.mean(np.square((f - o) / max(threshold_mm, 1e-6))))
    return CategoricalMetrics(
        pod=_ratio(counts.hits, counts.hits + counts.misses),
        far=_ratio(counts.false_alarms, counts.hits + counts.false_alarms),
        csi=_ratio(counts.hits, counts.total),
        hit_rate=_ratio(counts.hits + counts.correct_negatives, counts.total),
        brier_score=brier,
        base_rate=_ratio(counts.hits + counts.misses, counts.total),
        counts=counts,
    )


def lead_time_bucket(lead_hours: float) -> str:
    if lead_hours <= 6:
        return "0-6h"
    if lead_hours <= 12:
        return "6-12h"
    if lead_hours <= 24:
        return "12-24h"
    if lead_hours <= 48:
        return "24-48h"
    return ">48h"


def skill_score(value: float, baseline: float) -> float | None:
    if math.isclose(baseline, 0.0, abs_tol=1e-9):
        return None
    return 1.0 - value / baseline
