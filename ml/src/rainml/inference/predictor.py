"""Serving-side predictor.

Loads a versioned artifact once and reuses it. The backend's
`app.ml.registry.ModelRegistry` performs the loading; this module provides the
framework-level contract (input validation, severity, intervals) shared by
notebooks, batch scoring jobs and the API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from rainml.evaluation.metrics import DEFAULT_EVENT_THRESHOLD_MM
from rainml.features.engineering import FEATURE_COLUMNS
from rainml.inference.preprocessing import DistrictHistory, build_feature_frame
from rainml.models.registry import METADATA_FILENAME, load_metadata, verify_checksum

SEVERITY_BANDS: tuple[tuple[float, str], ...] = (
    (0.1, "none"),
    (2.5, "light"),
    (7.6, "moderate"),
    (15.6, "heavy"),
    (31.8, "very_heavy"),
    (float("inf"), "extreme"),
)


class ModelInferenceError(RuntimeError):
    pass


def classify_severity(rainfall_mm: float) -> str:
    value = max(float(rainfall_mm), 0.0)
    for upper, label in SEVERITY_BANDS:
        if value < upper:
            return label
    return "extreme"


@dataclass(frozen=True)
class Prediction:
    district_id: int | str
    target_date: date
    predicted_rainfall_mm: float
    lower_bound_mm: float
    upper_bound_mm: float
    severity: str
    model_version: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "district_id": self.district_id,
            "target_date": self.target_date.isoformat(),
            "predicted_rainfall_mm": round(self.predicted_rainfall_mm, 4),
            "lower_bound_mm": round(self.lower_bound_mm, 4),
            "upper_bound_mm": round(self.upper_bound_mm, 4),
            "severity": self.severity,
            "model_version": self.model_version,
        }


class RainfallPredictor:
    """Wraps one artifact directory."""

    def __init__(
        self,
        artifact_dir: str | Path,
        pipeline: Any | None = None,
        lower_pipeline: Any | None = None,
        upper_pipeline: Any | None = None,
    ) -> None:
        self.artifact_dir = Path(artifact_dir)
        if pipeline is None:
            pipeline, lower_pipeline, upper_pipeline = self._load()
        self.pipeline = pipeline
        self.lower_pipeline = lower_pipeline
        self.upper_pipeline = upper_pipeline
        self.metadata = load_metadata(self.artifact_dir.parent, self.artifact_dir.name)
        self.version = self.metadata.get("version", self.artifact_dir.name)
        self.features: list[str] = self.metadata.get("features", list(FEATURE_COLUMNS))
        self.event_threshold_mm = float(
            self.metadata.get("event_threshold_mm", DEFAULT_EVENT_THRESHOLD_MM)
        )

    @classmethod
    def from_artifact_root(cls, artifact_root: str | Path, version: str) -> RainfallPredictor:
        directory = Path(artifact_root) / version
        if not (directory / METADATA_FILENAME).exists():
            raise ModelInferenceError(
                f"Version '{version}' is not a valid artifact directory "
                f"(missing {METADATA_FILENAME})."
            )
        return cls(directory)

    def _load(self):
        import joblib

        model_path = self.artifact_dir / "model.joblib"
        if not model_path.exists():
            raise ModelInferenceError(f"model.joblib not found in {self.artifact_dir}")
        if not verify_checksum(self.artifact_dir.parent, self.artifact_dir.name):
            raise ModelInferenceError(
                f"Checksum mismatch for {self.artifact_dir.name}; "
                "the artifact was modified after training."
            )
        lower_path = self.artifact_dir / "lower_model.joblib"
        upper_path = self.artifact_dir / "upper_model.joblib"
        return (
            joblib.load(model_path),
            joblib.load(lower_path) if lower_path.exists() else None,
            joblib.load(upper_path) if upper_path.exists() else None,
        )

    def predict_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        missing = [c for c in self.features if c not in frame.columns]
        if missing:
            raise ModelInferenceError(f"input frame is missing features: {missing}")
        point = np.clip(np.asarray(self.pipeline.predict(frame), dtype=float), 0.0, None)
        if self.lower_pipeline is not None and self.upper_pipeline is not None:
            lower = np.clip(np.asarray(self.lower_pipeline.predict(frame), dtype=float), 0.0, None)
            upper = np.clip(np.asarray(self.upper_pipeline.predict(frame), dtype=float), 0.0, None)
        else:
            lower = upper = point
        return pd.DataFrame(
            {
                "predicted_rainfall_mm": np.round(point, 4),
                "lower_bound_mm": np.round(np.minimum(lower, point), 4),
                "upper_bound_mm": np.round(np.maximum(upper, point), 4),
            },
            index=frame.index,
        )

    def predict_districts(
        self,
        histories: list[DistrictHistory],
        issue_date: date,
        horizon_days: int = 1,
    ) -> list[Prediction]:
        from datetime import timedelta

        features = build_feature_frame(histories, issue_date)
        output = self.predict_frame(features)
        target_date = issue_date + timedelta(days=horizon_days)
        return [
            Prediction(
                district_id=history.district_id,
                target_date=target_date,
                predicted_rainfall_mm=float(output["predicted_rainfall_mm"].iloc[index]),
                lower_bound_mm=float(output["lower_bound_mm"].iloc[index]),
                upper_bound_mm=float(output["upper_bound_mm"].iloc[index]),
                severity=classify_severity(float(output["predicted_rainfall_mm"].iloc[index])),
                model_version=self.version,
            )
            for index, history in enumerate(histories)
        ]
