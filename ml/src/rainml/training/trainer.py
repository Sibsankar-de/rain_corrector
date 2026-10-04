"""The reproducible training pipeline.

Stages: load -> validate -> clean -> engineer -> split -> fit baselines ->
fit candidates -> evaluate -> select -> persist artifact -> record run.

The whole pipeline is driven from one `run_training` call. Notebooks call it and
then inspect the returned report; they never reimplement a stage. Nothing is
fitted before the chronological split, so no stage can see future rainfall.
"""

from __future__ import annotations

import platform
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import sklearn

from rainml.data.cleaning import CleaningReport, clean_observations
from rainml.data.loaders import attach_coordinates, load_districts, load_observations
from rainml.data.validation import (
    ValidationReport,
    chronological_split,
    validate_observations,
    validate_split,
    validate_training_frame,
)
from rainml.evaluation.evaluator import ComparisonResult, compare, score_predictions
from rainml.evaluation.metrics import DEFAULT_EVENT_THRESHOLD_MM, add_target_month
from rainml.features.engineering import (
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    assert_no_leakage,
    build_training_frame,
)
from rainml.features.selection import analyse_features
from rainml.models.baseline import make_baseline
from rainml.models.forecasting import (
    CANDIDATES,
    CandidateSpec,
    build_pipeline,
    make_quantile_pipeline,
)
from rainml.models.registry import build_metadata, next_version, save_artifact
from rainml.training.configuration import TrainingConfig, set_global_seed

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class TrainingReport:
    run_id: str
    status: str
    dataset_path: str
    dataset_rows: int
    config: dict[str, Any]
    cleaning: dict[str, Any]
    validation: dict[str, Any]
    feature_selection: dict[str, Any]
    split_sizes: dict[str, int]
    split_dates: dict[str, str]
    comparison: dict[str, Any]
    selected_model: str | None
    version: str | None
    artifact_path: str | None
    metrics: dict[str, Any]
    duration_seconds: float
    error: str | None = None
    training_data_start: str | None = None
    training_data_end: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class _Artifacts:
    pipeline: Any = None
    lower: Any = None
    upper: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)


def run_training(
    observations_path: str | Path,
    districts_path: str | Path,
    artifact_root: str | Path | None = None,
    config: TrainingConfig | None = None,
    register_run: Any = None,
    version: str | None = None,
    progress: Any = None,
) -> TrainingReport:
    """Execute one training run and return the full report.

    `register_run` is an optional callable invoked with keyword arguments
    (run_id, status, ...). The API passes a coroutine-free recorder that writes
    `training_runs`; scripts pass one that logs. Keeping it injectable avoids a
    dependency from the ML package onto the backend.
    """
    config = config or TrainingConfig()
    artifact_root = Path(artifact_root or REPO_ROOT / "ml" / "artifacts")
    run_id = f"run_{datetime.now(UTC):%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}"
    started = time.perf_counter()
    say = progress or (lambda message: None)

    _notify(
        register_run,
        run_id=run_id,
        status="running",
        config=config.to_dict(),
        started_at=datetime.now(UTC),
    )

    try:
        set_global_seed(config.random_seed)
        say(f"run {run_id}: loading {observations_path}")

        raw = load_observations(observations_path)
        districts = load_districts(districts_path)
        observations = attach_coordinates(raw, districts)

        validation = validate_observations(observations)
        validation.raise_for_errors()
        say(f"validation passed: {validation.summary}")

        cleaned, cleaning = clean_observations(observations)
        say(f"cleaning: {cleaning.output_rows} rows ({cleaning.dropped_rows} dropped)")

        frame = add_target_month(build_training_frame(cleaned, horizon_days=config.horizon_days))
        assert_no_leakage(frame)
        frame_validation = validate_training_frame(frame, target=config.target_column)
        frame_validation.raise_for_errors()

        train, valid, test = chronological_split(
            frame,
            valid_fraction=config.valid_fraction,
            test_fraction=config.test_fraction,
        )
        split_validation = validate_split(train, valid, test, date_column="issue_date")
        split_validation.raise_for_errors()
        say(f"split: train={len(train)} valid={len(valid)} test={len(test)}")

        selection = analyse_features(
            frame, target=config.target_column, max_features=config.max_features
        )
        features = selection.selected or list(FEATURE_COLUMNS)
        say(f"features: {len(features)} selected, dropped {selection.dropped}")

        artifacts, comparison, metrics = _fit_and_compare(train, valid, test, features, config, say)

        chosen_version = version or next_version(artifact_root)
        metadata = build_metadata(
            model_name=config.model_name,
            version=chosen_version,
            features=features,
            target_column=config.target_column,
            hyperparameters=artifacts.metadata.get("hyperparameters", {}),
            metrics=metrics,
            training_data_start=pd.to_datetime(frame["issue_date"]).min().to_pydatetime(),
            training_data_end=pd.to_datetime(frame["issue_date"]).max().to_pydatetime(),
            dataset_path=str(observations_path),
            dataset_rows=len(frame),
            status="candidate",
            notes=config.notes,
            selected_model=artifacts.metadata.get("selected_model"),
        )
        directory = save_artifact(
            root=artifact_root,
            version=chosen_version,
            pipeline=artifacts.pipeline,
            lower_pipeline=artifacts.lower,
            upper_pipeline=artifacts.upper,
            features=features,
            metadata=metadata,
            metrics=metrics,
        )
        say(f"artifact written to {directory}")

        duration = time.perf_counter() - started
        report = TrainingReport(
            run_id=run_id,
            status="succeeded",
            dataset_path=str(observations_path),
            dataset_rows=len(frame),
            config=config.to_dict(),
            cleaning=_cleaning_dict(cleaning),
            validation={
                "observations": validation.summary,
                "warnings": validation.warnings,
                "frame_warnings": frame_validation.warnings,
            },
            feature_selection={
                "selected": features,
                "dropped": selection.dropped,
                "constant": selection.constant,
                "scores": {k: round(v, 4) for k, v in selection.scores.items()},
            },
            split_sizes={"train": len(train), "valid": len(valid), "test": len(test)},
            split_dates={
                "train_end": str(pd.to_datetime(train["issue_date"]).max().date()),
                "valid_start": str(pd.to_datetime(valid["issue_date"]).min().date()),
                "valid_end": str(pd.to_datetime(valid["issue_date"]).max().date()),
                "test_start": str(pd.to_datetime(test["issue_date"]).min().date()),
                "test_end": str(pd.to_datetime(test["issue_date"]).max().date()),
            },
            comparison=comparison.to_dict(),
            selected_model=artifacts.metadata.get("selected_model"),
            version=chosen_version,
            artifact_path=str(directory),
            metrics=metrics,
            duration_seconds=round(duration, 3),
            training_data_start=metadata["training_data_start"],
            training_data_end=metadata["training_data_end"],
        )

        _notify(
            register_run,
            run_id=run_id,
            status="succeeded",
            config=config.to_dict(),
            dataset_path=str(observations_path),
            dataset_rows=len(frame),
            candidate_results=comparison.to_dict(),
            best_model_name=report.selected_model,
            best_metrics=metrics,
            baseline_metrics=comparison.baselines,
            created_model_version=chosen_version,
            finished_at=datetime.now(UTC),
            duration_seconds=duration,
        )
        return report

    except Exception as exc:
        duration = time.perf_counter() - started
        _notify(
            register_run,
            run_id=run_id,
            status="failed",
            config=config.to_dict(),
            error_message=str(exc)[:2000],
            finished_at=datetime.now(UTC),
            duration_seconds=duration,
        )
        return TrainingReport(
            run_id=run_id,
            status="failed",
            dataset_path=str(observations_path),
            dataset_rows=0,
            config=config.to_dict(),
            cleaning={},
            validation={},
            feature_selection={},
            split_sizes={},
            split_dates={},
            comparison={},
            selected_model=None,
            version=None,
            artifact_path=None,
            metrics={},
            duration_seconds=round(duration, 3),
            error=str(exc)[:2000],
        )


def _fit_and_compare(
    train: pd.DataFrame,
    valid: pd.DataFrame,
    test: pd.DataFrame,
    features: list[str],
    config: TrainingConfig,
    say,
) -> tuple[_Artifacts, ComparisonResult, dict[str, Any]]:
    target = config.target_column
    threshold = config.event_threshold_mm or DEFAULT_EVENT_THRESHOLD_MM

    train_x = train[features]
    valid_x = valid[features]
    test_x = test[features]
    train_y = train[target].to_numpy(dtype=float)
    valid_y = valid[target].to_numpy(dtype=float)
    test_y = test[target].to_numpy(dtype=float)

    validation_scores: dict[str, dict] = {}
    test_predictions: dict[str, np.ndarray] = {}
    baseline_names = {"persistence", "rolling_mean_7d", "seasonal_climatology", "global_mean"}

    for name in sorted(baseline_names):
        estimator = make_baseline(name)
        needs = ["district_id", "target_month"] if name == "seasonal_climatology" else []
        estimator.fit(train[features + needs] if needs else train_x, train_y)
        valid_pred = _safe_predict(estimator, valid[features + needs] if needs else valid_x)
        test_pred = _safe_predict(estimator, test[features + needs] if needs else test_x)
        validation_scores[name] = score_predictions(valid_pred, valid_y, threshold)
        test_predictions[name] = test_pred
        say(f"baseline {name}: MAE={validation_scores[name]['mae_mm']}")

    fitted: dict[str, Any] = {}
    for spec in _selected_specs(config):
        pipeline = build_pipeline(spec, features, max_features=config.max_features)
        pipeline.fit(train_x, train_y)
        valid_pred = pipeline.predict(valid_x)
        validation_scores[spec.name] = score_predictions(valid_pred, valid_y, threshold)
        test_predictions[spec.name] = pipeline.predict(test_x)
        fitted[spec.name] = pipeline
        say(f"candidate {spec.name}: MAE={validation_scores[spec.name]['mae_mm']}")

    test_scores = {
        name: score_predictions(test_predictions[name], test_y, threshold)
        for name in test_predictions
    }
    comparison = compare(validation_scores, test_scores, baseline_names, threshold)
    selected = comparison.best_candidate or comparison.best_baseline
    if selected is None:
        raise RuntimeError("no model produced usable validation scores")

    artifacts = _Artifacts()
    if selected in fitted:
        artifacts.pipeline = fitted[selected]
        spec = next(s for s in _selected_specs(config) if s.name == selected)
        artifacts.metadata = {
            "selected_model": selected,
            "family": spec.family,
            "hyperparameters": {
                **spec.params,
                "features": features,
                "max_features": config.max_features,
            },
        }
        if config.fit_interval_models:
            lower_alpha, upper_alpha = config.quantile_alphas
            artifacts.lower = make_quantile_pipeline(spec, features, lower_alpha)
            artifacts.upper = make_quantile_pipeline(spec, features, upper_alpha)
            artifacts.lower.fit(train_x, train_y)
            artifacts.upper.fit(train_x, train_y)
            say("quantile models fitted for the forecast interval")
    else:
        artifacts.pipeline = make_baseline(selected)
        needs = ["district_id", "target_month"] if selected == "seasonal_climatology" else []
        artifacts.pipeline.fit(train[features + needs] if needs else train_x, train_y)
        artifacts.metadata = {
            "selected_model": selected,
            "family": "baseline",
            "hyperparameters": {"features": features, "baseline": selected},
        }

    metrics = {
        "selected_model": selected,
        "validation": validation_scores,
        "test": test_scores,
        "best_baseline": comparison.best_baseline,
        "skill_vs_best_baseline": comparison.skill_vs_baseline,
        "beats_baseline": comparison.beats_baseline,
        "event_threshold_mm": threshold,
        "split_sizes": {"train": len(train), "valid": len(valid), "test": len(test)},
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "scikit_learn": sklearn.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
    }
    return artifacts, comparison, metrics


def _selected_specs(config: TrainingConfig) -> list[CandidateSpec]:
    specs = [s for s in CANDIDATES if s.name in set(config.candidate_names)]
    unknown = set(config.candidate_names) - {s.name for s in CANDIDATES}
    if unknown:
        raise ValueError(f"Unknown candidate models: {sorted(unknown)}")
    if not specs:
        raise ValueError("No candidate models selected in the configuration")
    return specs


def _safe_predict(estimator, frame: pd.DataFrame) -> np.ndarray:
    try:
        return np.asarray(estimator.predict(frame), dtype=float)
    except Exception:
        return np.zeros(len(frame), dtype=float)


def _cleaning_dict(cleaning: CleaningReport) -> dict[str, Any]:
    return {
        "input_rows": cleaning.input_rows,
        "output_rows": cleaning.output_rows,
        "dropped_rows": cleaning.dropped_rows,
        "dropped_negatives": cleaning.dropped_negatives,
        "dropped_extremes": cleaning.dropped_extremes,
        "dropped_duplicates": cleaning.dropped_duplicates,
        "imputed_values": cleaning.imputed_values,
        "flagged_outliers": cleaning.flagged_outliers,
        "notes": cleaning.notes,
    }


def _validation_dict(validation: ValidationReport) -> dict[str, Any]:
    return {
        "summary": validation.summary,
        "errors": validation.errors,
        "warnings": validation.warnings,
    }


def _notify(register_run, **payload) -> None:
    if register_run is None:
        return
    payload = {k: v for k, v in payload.items() if v is not None}
    try:
        register_run(**payload)
    except TypeError:
        register_run(payload)


__all__ = ["TrainingReport", "run_training", "FEATURE_COLUMNS", "TARGET_COLUMN"]
