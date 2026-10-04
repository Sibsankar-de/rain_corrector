"""Forecast verification results and their per-step detail."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import VerificationStatus


class VerificationResult(Base):
    """Outcome of scoring one forecast against the observation it targeted.

    `verified_at` and `observation_observed_at` are both stored so it can be
    proven that scoring only used data available after the target time.
    """

    __tablename__ = "verification_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    forecast_id: Mapped[int] = mapped_column(
        ForeignKey("forecasts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    aggregate_id: Mapped[int | None] = mapped_column(
        ForeignKey("district_aggregates.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verification_status"),
        default=VerificationStatus.PENDING_OBSERVATION,
        nullable=False,
        index=True,
    )
    observed_rainfall_mm: Mapped[float | None] = mapped_column(Float)
    forecast_rainfall_mm: Mapped[float] = mapped_column(Float)
    error_mm: Mapped[float | None] = mapped_column(Float)
    absolute_error_mm: Mapped[float | None] = mapped_column(Float)
    bias_mm: Mapped[float | None] = mapped_column(Float)
    rmse_mm: Mapped[float | None] = mapped_column(Float)
    nash_sutcliffe: Mapped[float | None] = mapped_column(Float)
    brier_score: Mapped[float | None] = mapped_column(Float)
    hit: Mapped[bool | None] = mapped_column()
    false_alarm: Mapped[bool | None] = mapped_column()
    missed: Mapped[bool | None] = mapped_column()
    correct_negatives: Mapped[bool | None] = mapped_column()
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    verification_method: Mapped[str] = mapped_column(
        String(32), default="district_aggregate", nullable=False
    )
    verification_windows: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    forecast = relationship("Forecast", lazy="joined")

    __table_args__ = (
        UniqueConstraint("forecast_id", name="uq_verification_forecast"),
        Index("ix_verification_status_observed", "status", "observed_at"),
    )


class VerificationBatch(Base):
    """Audit record of one verification job invocation."""

    __tablename__ = "verification_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_uid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    model_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL"), index=True
    )
    triggered_by: Mapped[str] = mapped_column(String(64), default="scheduled_job", nullable=False)
    candidates_considered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    forecasts_verified: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    forecasts_pending: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metrics_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="completed", nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(512))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
