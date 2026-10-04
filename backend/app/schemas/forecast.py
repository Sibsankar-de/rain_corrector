"""Forecast and verification schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.core.enums import (
    AlertSeverity,
    AlertStatus,
    ForecastStatus,
    ModelStatus,
    VerificationStatus,
)
from app.schemas.common import ORMModel
from app.schemas.location import DistrictSummary


class ForecastValueRead(ORMModel):
    id: int
    step_index: int
    step_start: datetime
    step_end: datetime
    lead_hours: float
    predicted_rainfall_mm: float
    lower_bound_mm: float | None = None
    upper_bound_mm: float | None = None


class ForecastRead(ORMModel):
    id: int
    run_id: int
    district_id: int
    target_time: datetime
    lead_time_hours: float
    predicted_rainfall_mm: float
    predicted_probability: float | None = None
    lower_bound_mm: float | None = None
    upper_bound_mm: float | None = None
    severity: str
    status: ForecastStatus
    issued_at: datetime
    model_version: str
    district: DistrictSummary | None = None


class ForecastDetail(ForecastRead):
    feature_inputs: dict = Field(default_factory=dict)
    values: list[ForecastValueRead] = Field(default_factory=list)


class ForecastRunRead(ORMModel):
    id: int
    run_uid: str
    model_version: str
    issued_at: datetime
    horizon_hours: int
    step_hours: int
    valid_from: datetime
    valid_to: datetime
    generator: str
    forecast_count: int | None = None


class ForecastQueryFilters(ORMModel):
    district_id: list[int] = Field(default_factory=list)
    region_id: int | None = None
    model_version: str | None = None
    min_rainfall_mm: float | None = Field(default=None, ge=0)
    severity: str | None = None
    issued_from: datetime | None = None
    issued_to: datetime | None = None
    target_from: datetime | None = None
    target_to: datetime | None = None
    min_lat: float | None = Field(default=None, ge=-90, le=90)
    min_lon: float | None = Field(default=None, ge=-180, le=180)
    max_lat: float | None = Field(default=None, ge=-90, le=90)
    max_lon: float | None = Field(default=None, ge=-180, le=180)


class ForecastGenerateRequest(ORMModel):
    model_version: str | None = Field(
        default=None, description="Version to generate with. Defaults to the active model."
    )
    issued_at: datetime | None = Field(
        default=None, description="Forecast base time. Defaults to now. Must not be in the future."
    )
    horizon_hours: int | None = Field(default=None, ge=1, le=168)
    step_hours: int = Field(6, ge=1, le=24)
    district_ids: list[int] | None = Field(
        default=None,
        description="Restrict generation to these districts. Defaults to all active districts.",
    )

    def resolved_horizon(self, default: int) -> int:
        return self.horizon_hours or default


class GenerateForecastResponse(ORMModel):
    run_uid: str
    model_version: str
    issued_at: datetime
    forecasts_created: int = Field(
        ..., description="Zero when the issuance already existed and nothing was written."
    )
    valid_from: datetime
    valid_to: datetime


class VerificationResultRead(ORMModel):
    id: int
    forecast_id: int
    status: VerificationStatus
    observed_rainfall_mm: float | None = None
    forecast_rainfall_mm: float
    error_mm: float | None = None
    absolute_error_mm: float | None = None
    bias_mm: float | None = None
    rmse_mm: float | None = None
    nash_sutcliffe: float | None = None
    brier_score: float | None = None
    hit: bool | None = None
    false_alarm: bool | None = None
    missed: bool | None = None
    correct_negatives: bool | None = None
    observed_at: datetime | None = None
    verified_at: datetime | None = None


class VerificationMetricsSummary(ORMModel):
    sample_size: int
    mean_error_mm: float
    mean_absolute_error_mm: float
    rmse_mm: float
    bias_mm: float
    nash_sutcliffe: float | None = None
    brier_score: float | None = None
    hit_rate: float | None = None
    false_alarm_ratio: float | None = None
    detection_score: float | None = None
    critical_success_index: float | None = None
    by_lead_bucket: dict[str, dict[str, float]] = Field(default_factory=dict)
    by_severity: dict[str, dict[str, float]] = Field(default_factory=dict)
    computed_at: datetime


class VerificationRunRequest(ORMModel):
    model_version: str | None = None
    district_ids: list[int] | None = None
    lookback_days: int = Field(14, ge=1, le=365)
    force: bool = Field(
        default=False, description="Re-score forecasts that already have a verification result."
    )


class VerificationRunResponse(ORMModel):
    batch_uid: str
    candidates_considered: int
    forecasts_verified: int
    forecasts_pending: int
    metrics: VerificationMetricsSummary | None = None
    started_at: datetime
    finished_at: datetime | None = None


class ModelVersionRead(ORMModel):
    id: int
    model_name: str
    version: str
    status: ModelStatus
    framework_version: str
    features: list[str]
    metrics: dict
    hyperparameters: dict
    training_data_start: datetime | None = None
    training_data_end: datetime | None = None
    trained_at: datetime = Field(validation_alias="created_at")
    activated_at: datetime | None = None
    notes: str | None = None


class ModelVersionDetail(ModelVersionRead):
    artifact_path: str
    training_run_id: int | None = None
    archived_at: datetime | None = None


class TrainingRunRead(ORMModel):
    id: int
    run_id: str
    status: str
    best_model_name: str | None = None
    best_metrics: dict
    baseline_metrics: dict
    candidate_results: dict
    dataset_rows: int | None = None
    created_model_version: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    error_message: str | None = None


class ModelPromotionRequest(ORMModel):
    target_version: str
    policy: str | None = Field(
        default=None, description="Promotion policy override. Defaults to the configured policy."
    )
    notes: str | None = None


class ModelPromotionResponse(ORMModel):
    activated_version: str
    previous_version: str | None = None
    reloaded: bool
    policy: str


class AlertRead(ORMModel):
    id: int
    district_id: int
    district_name: str | None = None
    forecast_id: int | None = None
    severity: AlertSeverity
    status: AlertStatus
    alert_type: str
    title: str
    message: str
    threshold_mm: float
    observed_value_mm: float | None = None
    valid_from: datetime
    valid_to: datetime
    created_at: datetime


class AlertStatusUpdate(ORMModel):
    status: AlertStatus
    note: str | None = Field(default=None, max_length=500)
