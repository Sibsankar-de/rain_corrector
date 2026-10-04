"""Pydantic schemas for locations, observations and aggregates."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.core.enums import DataOrigin
from app.schemas.common import ORMModel


class RegionRead(ORMModel):
    id: int
    code: str
    name: str
    level: str


class DistrictSummary(ORMModel):
    id: int
    code: str
    name: str
    region_id: int
    centroid_lat: float = Field(..., ge=-90, le=90)
    centroid_lon: float = Field(..., ge=-180, le=180)
    population: int | None = None


class DistrictDetail(DistrictSummary):
    bbox_min_lat: float | None = None
    bbox_min_lon: float | None = None
    bbox_max_lat: float | None = None
    bbox_max_lon: float | None = None
    area_sq_km: float | None = None
    geometry_geojson: str | None = None
    region: RegionRead | None = None
    station_count: int | None = None


class StationRead(ORMModel):
    id: int
    code: str
    name: str
    district_id: int
    latitude: float
    longitude: float
    elevation_m: float | None = None
    is_active: bool


class StationCreate(ORMModel):
    code: str = Field(..., min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(..., min_length=2, max_length=160)
    district_id: int
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    elevation_m: float | None = Field(default=None, ge=-500, le=9000)
    installed_at: datetime | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must not be blank")
        return cleaned


class ObservationCreate(ORMModel):
    station_id: int
    observed_at: datetime
    window_minutes: int = Field(60, ge=5, le=1440)
    rainfall_mm: float = Field(..., ge=0, le=2000)
    temperature_c: float | None = Field(default=None, ge=-90, le=60)
    relative_humidity: float | None = Field(default=None, ge=0, le=100)
    wind_speed_kmph: float | None = Field(default=None, ge=0, le=300)
    pressure_hpa: float | None = Field(default=None, ge=800, le=1100)
    origin: DataOrigin = DataOrigin.OBSERVED
    source: str = Field("api", max_length=64)

    @field_validator("observed_at")
    @classmethod
    def _not_in_future(cls, value: datetime) -> datetime:
        from app.utils.time import utcnow

        if value > utcnow():
            raise ValueError("observed_at cannot be in the future")
        return value


class ObservationRead(ORMModel):
    id: int
    station_id: int
    observed_at: datetime
    window_minutes: int
    rainfall_mm: float
    temperature_c: float | None = None
    relative_humidity: float | None = None
    wind_speed_kmph: float | None = None
    pressure_hpa: float | None = None
    origin: DataOrigin
    source: str
    recorded_at: datetime


class ObservationBatchCreate(ORMModel):
    observations: list[ObservationCreate] = Field(..., min_length=1, max_length=5000)
    recompute_aggregates: bool = True


class IngestionResult(ORMModel):
    """Outcome of one ingest call.

    Validation happens on the whole batch, so a request is either fully
    accepted or fully rejected: there is no per-row `rejected` count to report.
    """

    accepted: int
    duplicates: int
    aggregates_updated: int = 0


class DistrictAggregateRead(ORMModel):
    id: int
    district_id: int
    observed_at: datetime
    window_minutes: int
    rainfall_mm: float
    station_count: int
    coverage_ratio: float
    origin: DataOrigin
    computed_at: datetime
