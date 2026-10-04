"""Factories for integration tests: geography, observations, models, forecasts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import DataOrigin, ModelStatus
from app.ml.registry import model_registry
from app.models import (
    District,
    DistrictAggregate,
    Forecast,
    ForecastRun,
    ForecastValue,
    ModelVersion,
    Region,
    Station,
    StationObservation,
    User,
)

BASE_TIME = datetime(2026, 9, 28, 0, 0, tzinfo=UTC)


async def make_region(
    session: AsyncSession, code: str = "MH-R", name: str = "Maharashtra"
) -> Region:
    region = Region(code=code, name=name, level="state")
    session.add(region)
    await session.flush()
    return region


async def make_district(
    session: AsyncSession,
    region: Region,
    code: str = "MH-MUM",
    name: str = "Mumbai Suburban",
    lat: float = 19.2183,
    lon: float = 72.9781,
) -> District:
    district = District(
        code=code,
        name=name,
        region_id=region.id,
        centroid_lat=lat,
        centroid_lon=lon,
        population=2_335_000,
    )
    session.add(district)
    await session.flush()
    return district


async def make_station(
    session: AsyncSession, district: District, code: str = "MH-MUM-ST01"
) -> Station:
    station = Station(
        code=code,
        name=f"{district.name} gauge",
        district_id=district.id,
        latitude=district.centroid_lat,
        longitude=district.centroid_lon,
        is_active=True,
    )
    session.add(station)
    await session.flush()
    return station


async def make_daily_aggregates(
    session: AsyncSession,
    district: District,
    values: list[float],
    start: datetime = BASE_TIME - timedelta(days=10),
) -> list[DistrictAggregate]:
    rows = [
        DistrictAggregate(
            district_id=district.id,
            observed_at=start + timedelta(days=index),
            window_minutes=1440,
            rainfall_mm=value,
            station_count=1,
            coverage_ratio=1.0,
            origin=DataOrigin.OBSERVED,
        )
        for index, value in enumerate(values)
    ]
    session.add_all(rows)
    await session.flush()
    return rows


async def make_station_observations(
    session: AsyncSession, station: Station, values: list[float], start: datetime
) -> list[StationObservation]:
    rows = [
        StationObservation(
            station_id=station.id,
            observed_at=start + timedelta(days=index),
            window_minutes=1440,
            rainfall_mm=value,
            origin=DataOrigin.OBSERVED,
            source="test",
        )
        for index, value in enumerate(values)
    ]
    session.add_all(rows)
    await session.flush()
    return rows


async def make_active_model(
    session: AsyncSession, trained_artifact, version: str | None = None
) -> ModelVersion:
    """Register a real on-disk artifact as the active model version."""
    import json

    metadata = json.loads((trained_artifact / "metadata.json").read_text())
    resolved = version or trained_artifact.name

    record = ModelVersion(
        model_name=metadata["model_name"],
        version=resolved,
        status=ModelStatus.ACTIVE,
        artifact_path=str(trained_artifact),
        framework_version=metadata.get("framework_version", "unknown"),
        hyperparameters=metadata.get("hyperparameters", {}),
        features=metadata.get("features", []),
        metrics=metadata.get("metrics", {}),
    )
    session.add(record)
    await session.flush()
    return record


async def make_forecast_run(
    session: AsyncSession,
    model: ModelVersion,
    district: District,
    target_time: datetime,
    issued_at: datetime,
    predicted_mm: float = 5.0,
    lower_mm: float = 0.0,
    upper_mm: float = 10.0,
    severity: str = "moderate",
    with_values: bool = True,
) -> Forecast:
    # One issuance covers many districts, so an existing run for this model and
    # base time is reused rather than colliding on the unique run_uid.
    run_uid = f"fr_{model.version}_{issued_at:%Y%m%dT%H%M%SZ}"
    run = await session.scalar(select(ForecastRun).where(ForecastRun.run_uid == run_uid))
    if run is None:
        run = ForecastRun(
            run_uid=run_uid,
            model_version_id=model.id,
            issued_at=issued_at,
            horizon_hours=24,
            step_hours=24,
            valid_from=issued_at,
            valid_to=target_time,
            generator="test",
        )
        session.add(run)
        await session.flush()

    forecast = Forecast(
        run_id=run.id,
        district_id=district.id,
        target_time=target_time,
        lead_time_hours=24.0,
        predicted_rainfall_mm=predicted_mm,
        lower_bound_mm=lower_mm,
        upper_bound_mm=upper_mm,
        severity=severity,
        feature_inputs={},
    )
    session.add(forecast)
    await session.flush()

    if with_values:
        session.add(
            ForecastValue(
                forecast_id=forecast.id,
                step_index=0,
                step_start=issued_at,
                step_end=target_time,
                lead_hours=24.0,
                predicted_rainfall_mm=predicted_mm,
                lower_bound_mm=lower_mm,
                upper_bound_mm=upper_mm,
            )
        )
        await session.flush()
    return forecast


async def make_user(session: AsyncSession, username: str = "tester") -> User:
    user = User(username=username, email=f"{username}@test.local", is_active=True)
    session.add(user)
    await session.flush()
    return user


def load_artifact(trained_artifact):
    """Load a real artifact through the registry used by the app."""
    return model_registry.set_active(trained_artifact.name)
