"""Forecast issuance and forecast value entities.

A `ForecastRun` is one issuance of one model over a set of districts at a single
`issued_at`. Each `Forecast` row is the district-level prediction; the
`ForecastValue` rows hold the individual lead-time steps so downstream code can
reason about horizons instead of a single opaque number.
"""

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
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import ForecastStatus


class ForecastRun(Base):
    """A single model issuance shared by many district forecasts."""

    __tablename__ = "forecast_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_uid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("model_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    horizon_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    step_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generator: Mapped[str] = mapped_column(String(64), default="scheduled_job", nullable=False)
    feature_snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    model_version = relationship("ModelVersion", lazy="joined")
    forecasts = relationship(
        "Forecast", back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (Index("ix_forecast_runs_model_issued", "model_version_id", "issued_at"),)


class Forecast(Base):
    """District-level forecast produced by a run."""

    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("forecast_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    district_id: Mapped[int] = mapped_column(
        ForeignKey("districts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    lead_time_hours: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_rainfall_mm: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_probability: Mapped[float | None] = mapped_column(Float)
    lower_bound_mm: Mapped[float | None] = mapped_column(Float)
    upper_bound_mm: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(32), default="none", nullable=False, index=True)
    status: Mapped[ForecastStatus] = mapped_column(
        Enum(ForecastStatus, name="forecast_status"),
        default=ForecastStatus.ISSUED,
        nullable=False,
        index=True,
    )
    feature_inputs: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run = relationship("ForecastRun", back_populates="forecasts")
    district = relationship("District", lazy="joined")
    values = relationship(
        "ForecastValue",
        back_populates="forecast",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_forecasts_district_target_status", "district_id", "target_time", "status"),
        Index("ix_forecasts_run_district", "run_id", "district_id", unique=True),
    )


class ForecastValue(Base):
    """One lead-time step of a forecast (e.g. +6h accumulated rainfall)."""

    __tablename__ = "forecast_values"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    forecast_id: Mapped[int] = mapped_column(
        ForeignKey("forecasts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    step_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    step_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lead_hours: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_rainfall_mm: Mapped[float] = mapped_column(Float, nullable=False)
    lower_bound_mm: Mapped[float | None] = mapped_column(Float)
    upper_bound_mm: Mapped[float | None] = mapped_column(Float)

    forecast = relationship("Forecast", back_populates="values")

    __table_args__ = (
        UniqueConstraint("forecast_id", "step_index", name="uq_forecast_values_step"),
        Index("ix_forecast_values_forecast_lead", "forecast_id", "lead_hours"),
    )
