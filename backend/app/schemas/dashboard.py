"""Dashboard aggregate response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import ORMModel
from app.schemas.forecast import VerificationMetricsSummary


class StatusSnapshot(ORMModel):
    """Pipeline state: how far forecasts have progressed through verification.

    Counters describing the current situation rather than the pipeline
    (districts at risk, open alerts, observed totals) live in `PlatformSummary`,
    so no figure appears in two places.
    """

    forecasts_issued: int = 0
    forecasts_verified: int = 0
    forecasts_pending: int = 0
    latest_observation: datetime | None = None
    evaluated_at: datetime


class PlatformSummary(ORMModel):
    """Headline counters shown as KPI cards on the dashboard."""

    forecasts_last_7d: int = 0
    districts_at_risk: int = 0
    open_alerts: int = 0
    observed_rainfall_mm_7d: float = 0.0


class SeverityDistribution(ORMModel):
    severity: str
    count: int
    mean_rainfall_mm: float


class DistrictRiskItem(ORMModel):
    district_id: int
    code: str
    name: str
    latitude: float
    longitude: float
    predicted_rainfall_mm: float
    upper_bound_mm: float | None = None
    severity: str
    target_time: datetime


class ObservedRainfallItem(ORMModel):
    observed_at: datetime
    mean_rainfall_mm: float
    total_rainfall_mm: float


class TimeseriesPoint(ORMModel):
    timestamp: datetime
    value: float
    lower: float | None = None
    upper: float | None = None


class ActiveAlertItem(ORMModel):
    id: int
    district_id: int
    district_name: str | None = None
    severity: str
    title: str
    message: str
    valid_from: datetime
    valid_to: datetime


class ModelHealthItem(ORMModel):
    model_name: str
    version: str
    status: str
    trained_at: datetime
    mae_mm: float | None = None
    rmse_mm: float | None = None
    sample_size: int = 0
    is_loaded: bool = False


class LegendEntry(ORMModel):
    label: str
    severity: str
    color: str
    min_mm: float
    max_mm: float | None = None


class DashboardOverview(ORMModel):
    generated_at: datetime
    active_model_version: str | None = None
    model_loaded_version: str | None = None
    latest_forecast_run: str | None = None
    latest_forecast_issued_at: datetime | None = None
    status: StatusSnapshot
    summary: PlatformSummary
    verification: VerificationMetricsSummary
    severity_distribution: list[SeverityDistribution] = Field(default_factory=list)
    top_risk_districts: list[DistrictRiskItem] = Field(default_factory=list)
    observed_rainfall_series: list[ObservedRainfallItem] = Field(default_factory=list)
    forecast_vs_observed_series: list[TimeseriesPoint] = Field(default_factory=list)
    alerts: list[ActiveAlertItem] = Field(default_factory=list)
    legend: list[LegendEntry] = Field(default_factory=list)
    models: list[ModelHealthItem] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
