"""Model artifact registry on disk.

Layout, one directory per version:

    ml/artifacts/<version>/
        model.joblib             fitted pipeline (preprocessor + regressor)
        lower_model.joblib       10th percentile pipeline
        upper_model.joblib       90th percentile pipeline
        preprocessor.joblib      fitted ColumnTransformer, exported separately
        feature_columns.json     exact training-time feature order
        metadata.json            model card
        metrics.json             split metrics for every baseline and candidate
        checksum.txt             sha256 of model.joblib

Versions are immutable. A retraining run writes a new directory and never
overwrites an existing one, so a promotion can always be rolled back by pointing
the API at the previous version.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MODEL_FILENAME = "model.joblib"
LOWER_FILENAME = "lower_model.joblib"
UPPER_FILENAME = "upper_model.joblib"
PREPROCESSOR_FILENAME = "preprocessor.joblib"
FEATURE_COLUMNS_FILENAME = "feature_columns.json"
METADATA_FILENAME = "metadata.json"
METRICS_FILENAME = "metrics.json"
CHECKSUM_FILENAME = "checksum.txt"


def next_version(root: Path, prefix: str = "v") -> str:
    existing = list_versions(root)
    if not existing:
        return f"{prefix}001"
    latest = max(existing)
    digits = "".join(ch for ch in latest if ch.isdigit()) or "0"
    return f"{prefix}{int(digits) + 1:03d}"


def list_versions(root: Path) -> list[str]:
    if not root.exists():
        return []
    return sorted(
        entry.name
        for entry in root.iterdir()
        if entry.is_dir() and (entry / METADATA_FILENAME).exists()
    )


def save_artifact(
    root: Path,
    version: str,
    pipeline: Any,
    features: list[str],
    metadata: dict[str, Any],
    metrics: dict[str, Any],
    lower_pipeline: Any = None,
    upper_pipeline: Any = None,
    overwrite: bool = False,
) -> Path:
    import joblib

    directory = Path(root) / version
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()) and not overwrite:
        raise FileExistsError(
            f"Artifact directory {directory} already exists. Versions are immutable; "
            "train a new version instead of overwriting."
        )

    joblib.dump(pipeline, directory / MODEL_FILENAME)
    if lower_pipeline is not None:
        joblib.dump(lower_pipeline, directory / LOWER_FILENAME)
    if upper_pipeline is not None:
        joblib.dump(upper_pipeline, directory / UPPER_FILENAME)

    preprocessor = pipeline.named_steps.get("preprocessor")
    if preprocessor is not None:
        joblib.dump(preprocessor, directory / PREPROCESSOR_FILENAME)

    (directory / FEATURE_COLUMNS_FILENAME).write_text(json.dumps(features, indent=2))
    (directory / METRICS_FILENAME).write_text(json.dumps(metrics, indent=2, default=str))
    (directory / METADATA_FILENAME).write_text(json.dumps(metadata, indent=2, default=str))

    digest = hashlib.sha256((directory / MODEL_FILENAME).read_bytes()).hexdigest()
    (directory / CHECKSUM_FILENAME).write_text(f"{digest}  {MODEL_FILENAME}\n")
    return directory


def load_metadata(root: Path, version: str) -> dict[str, Any]:
    path = Path(root) / version / METADATA_FILENAME
    if not path.exists():
        raise FileNotFoundError(f"No metadata for version '{version}' at {path}")
    return json.loads(path.read_text())


def load_metrics(root: Path, version: str) -> dict[str, Any]:
    path = Path(root) / version / METRICS_FILENAME
    return json.loads(path.read_text()) if path.exists() else {}


def verify_checksum(root: Path, version: str) -> bool:
    directory = Path(root) / version
    checksum_file = directory / CHECKSUM_FILENAME
    model_file = directory / MODEL_FILENAME
    if not checksum_file.exists() or not model_file.exists():
        return False
    expected = checksum_file.read_text().split()[0]
    return hashlib.sha256(model_file.read_bytes()).hexdigest() == expected


def promote_symlink(root: Path, version: str) -> Path:
    """Point an `active` symlink at `version` for single-artifact deployments."""
    link = Path(root) / "active"
    target = Path(root) / version
    if not target.exists():
        raise FileNotFoundError(f"Version '{version}' does not exist under {root}")
    if link.is_symlink() or link.exists():
        if link.is_dir() and not link.is_symlink():
            shutil.rmtree(link)
        else:
            link.unlink()
    link.symlink_to(target.name, target_is_directory=True)
    return link


def build_metadata(
    model_name: str,
    version: str,
    features: list[str],
    target_column: str,
    hyperparameters: dict[str, Any],
    metrics: dict[str, Any],
    training_data_start: datetime,
    training_data_end: datetime,
    dataset_path: str,
    dataset_rows: int,
    status: str = "candidate",
    notes: str | None = None,
    selected_model: str | None = None,
) -> dict[str, Any]:
    import sklearn

    metadata: dict[str, Any] = {
        "model_name": model_name,
        "version": version,
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "training_data_start": training_data_start.isoformat(),
        "training_data_end": training_data_end.isoformat(),
        "training_data_range": f"{training_data_start.date()} .. {training_data_end.date()}",
        "features": features,
        "target_column": target_column,
        "hyperparameters": hyperparameters,
        "metrics": metrics,
        "framework_version": f"scikit-learn=={sklearn.__version__}",
        "framework": "scikit-learn",
        "dataset_path": dataset_path,
        "dataset_rows": dataset_rows,
        "event_threshold_mm": 15.0,
        "status": status,
        "selected_model": selected_model,
    }
    if notes:
        metadata["notes"] = notes
    return metadata
