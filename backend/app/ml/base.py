"""Loaded model handle and typed prediction output."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np

from app.core.exceptions import PredictionError


@dataclass(frozen=True)
class ModelArtifact:
    """Everything needed to serve one model version.

    `pipeline` is the fitted sklearn Pipeline (preprocessor + regressor),
    `metadata` the JSON produced by the training run, and `feature_columns`
    the exact training-time feature order. `lower_pipeline` and
    `upper_pipeline` are fitted quantile regressors; they are optional because
    older artifacts may predate interval support.
    """

    model_name: str
    version: str
    pipeline: Any
    metadata: dict[str, Any]
    feature_columns: list[str]
    event_threshold_mm: float = 15.0
    loaded_at: datetime | None = None
    artifact_dir: str | None = None
    lower_pipeline: Any = None
    upper_pipeline: Any = None

    @property
    def supports_intervals(self) -> bool:
        return self.lower_pipeline is not None and self.upper_pipeline is not None

    def validate_features(self, frame) -> None:
        """Fail fast when the request frame does not match the training contract."""
        missing = [c for c in self.feature_columns if c not in frame.columns]
        if missing:
            raise PredictionError(
                f"Model {self.version} expects features missing from the input: {missing}"
            )

    def predict(self, frame) -> np.ndarray:
        self.validate_features(frame)
        return np.asarray(self.pipeline.predict(frame), dtype=float)

    def predict_interval(self, frame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return (point, lower, upper) with the ordering of the bounds enforced.

        Independent quantile fits can cross on small samples, so the lower bound
        is clamped to the point forecast and the upper bound to at least it.
        """
        point = self.predict(frame)
        if not self.supports_intervals:
            return point, point, point
        lower = np.asarray(self.lower_pipeline.predict(frame), dtype=float)
        upper = np.asarray(self.upper_pipeline.predict(frame), dtype=float)
        return point, np.minimum(lower, point), np.maximum(upper, point)


@dataclass(frozen=True)
class PredictionOutput:
    district_id: int
    target_time: datetime
    lead_time_hours: float
    predicted_rainfall_mm: float
    lower_bound_mm: float
    upper_bound_mm: float
    predicted_probability: float | None
    severity: str
    model_version: str
