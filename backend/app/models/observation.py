"""Observed precipitation and derived weather measurements.

`observed_at` is the start of the accumulation window; `recorded_at` is when the
system ingested the value. Verification only accepts observations whose
window ended strictly before the forecast was verified, and both timestamps are
kept so the temporal ordering is auditable.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
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
from app.core.enums import DataOrigin


class StationObservation(Base):
    """Station-reported rainfall accumulation over a fixed window."""

    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    station_id: Mapped[int] = mapped_column(
        ForeignKey("stations.id", ondelete="CASCADE"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    rainfall_mm: Mapped[float] = mapped_column(Float, nullable=False)
    temperature_c: Mapped[float | None] = mapped_column(Float)
    relative_humidity: Mapped[float | None] = mapped_column(Float)
    wind_speed_kmph: Mapped[float | None] = mapped_column(Float)
    pressure_hpa: Mapped[float | None] = mapped_column(Float)
    origin: Mapped[DataOrigin] = mapped_column(
        Enum(DataOrigin, name="data_origin"), default=DataOrigin.OBSERVED, nullable=False
    )
    source: Mapped[str] = mapped_column(String(64), default="seed", nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    station = relationship("Station", lazy="joined")

    __table_args__ = (
        UniqueConstraint(
            "station_id", "observed_at", "window_minutes", name="uq_obs_station_time_window"
        ),
        Index("ix_observations_observed_at", "observed_at"),
        Index("ix_observations_station_observed", "station_id", "observed_at"),
    )


class DistrictAggregate(Base):
    """Area-weighted district rainfall derived from station observations.

    Kept as a separate fact table so verification and the API never have to
    re-aggregate raw station rows, and so the aggregation window is explicit.
    """

    __tablename__ = "district_aggregates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    district_id: Mapped[int] = mapped_column(
        ForeignKey("districts.id", ondelete="CASCADE"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=1440)
    rainfall_mm: Mapped[float] = mapped_column(Float, nullable=False)
    station_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    coverage_ratio: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    origin: Mapped[DataOrigin] = mapped_column(
        Enum(DataOrigin, name="data_origin"), default=DataOrigin.OBSERVED, nullable=False
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    district = relationship("District", lazy="joined")

    __table_args__ = (
        UniqueConstraint(
            "district_id", "observed_at", "window_minutes", name="uq_agg_district_time_window"
        ),
        Index("ix_district_aggregates_district_time", "district_id", "observed_at"),
    )
