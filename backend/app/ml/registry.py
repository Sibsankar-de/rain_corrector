"""Versioned model artifact loader.

Artifacts live at ``<MODEL_ARTIFACT_PATH>/<version>/`` and contain:

    model.joblib          fitted sklearn Pipeline
    preprocessor.joblib   fitted ColumnTransformer (also embedded in the pipeline)
    metadata.json         model card: features, metrics, training window, versions
    feature_columns.json  exact training-time feature order

The active model is cached in the process and swapped only when the database
says the active version changed, so requests never pay deserialisation cost.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.exceptions import ModelUnavailableError
from app.core.logging_config import get_logger
from app.ml.base import ModelArtifact

logger = get_logger(__name__)

METADATA_FILE = "metadata.json"
MODEL_FILE = "model.joblib"
PREPROCESSOR_FILE = "preprocessor.joblib"
FEATURE_COLUMNS_FILE = "feature_columns.json"


class ModelRegistry:
    """Thread-safe single-active-model cache."""

    def __init__(self, artifact_root: Path | None = None) -> None:
        self.artifact_root = Path(artifact_root or settings.model_artifact_path)
        self._artifact: ModelArtifact | None = None
        self._lock = threading.Lock()

    def version_dir(self, version: str) -> Path:
        return self.artifact_root / version

    def available_versions(self) -> list[str]:
        if not self.artifact_root.exists():
            return []
        return sorted(
            entry.name
            for entry in self.artifact_root.iterdir()
            if entry.is_dir() and (entry / METADATA_FILE).exists()
        )

    def load_version(self, version: str) -> ModelArtifact:
        import joblib

        directory = self.version_dir(version)
        metadata_path = directory / METADATA_FILE
        if not metadata_path.exists():
            raise ModelUnavailableError(
                f"Artifact for version '{version}' was not found at {directory}."
            )

        model_path = directory / MODEL_FILE
        if not model_path.exists():
            model_path = directory / "pipeline.joblib"
        if not model_path.exists():
            raise ModelUnavailableError(
                f"Model bundle missing for version '{version}'; expected {MODEL_FILE}."
            )

        metadata: dict[str, Any] = json.loads(metadata_path.read_text())
        pipeline = joblib.load(model_path)

        lower_path = directory / "lower_model.joblib"
        upper_path = directory / "upper_model.joblib"
        lower = joblib.load(lower_path) if lower_path.exists() else None
        upper = joblib.load(upper_path) if upper_path.exists() else None

        feature_columns: list[str] = []
        feature_path = directory / FEATURE_COLUMNS_FILE
        if feature_path.exists():
            feature_columns = json.loads(feature_path.read_text())
        if not feature_columns:
            feature_columns = list(metadata.get("features", []))

        artifact = ModelArtifact(
            model_name=metadata.get("model_name", "rainfall_forecast"),
            version=metadata.get("version", version),
            pipeline=pipeline,
            metadata=metadata,
            feature_columns=feature_columns,
            event_threshold_mm=float(metadata.get("event_threshold_mm", 15.0)),
            loaded_at=datetime.now(),
            artifact_dir=str(directory),
            lower_pipeline=lower,
            upper_pipeline=upper,
        )
        logger.info(
            "model_artifact_loaded",
            version=artifact.version,
            model_name=artifact.model_name,
            features=len(artifact.feature_columns),
            artifact_dir=str(directory),
        )
        return artifact

    def set_active(self, version: str | None) -> ModelArtifact | None:
        """Atomically replace the cached model. Passing None clears the cache."""
        artifact = self.load_version(version) if version else None
        with self._lock:
            self._artifact = artifact
        return artifact

    def get_active(self) -> ModelArtifact:
        if self._artifact is None:
            raise ModelUnavailableError(
                "No model is loaded. Start the API with a deployed model artifact "
                "or call the model promotion endpoint."
            )
        return self._artifact

    @property
    def active_version(self) -> str | None:
        return self._artifact.version if self._artifact else None

    def is_loaded(self, version: str) -> bool:
        return self._artifact is not None and self._artifact.version == version

    def reload_if_needed(self, version: str | None) -> ModelArtifact | None:
        """Load only when the requested version differs from the cached one."""
        if version is None or self.is_loaded(version):
            return self._artifact
        return self.set_active(version)


model_registry = ModelRegistry()
