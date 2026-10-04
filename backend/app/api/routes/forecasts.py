"""Forecast query, generation and map endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AppError, NotFoundError
from app.ml.predictor import ForecastGenerator
from app.models.forecast import Forecast, ForecastRun
from app.repositories.forecast_repository import ForecastRepository
from app.schemas.common import PaginatedResponse, PaginationParams
from app.schemas.forecast import (
    ForecastDetail,
    ForecastGenerateRequest,
    ForecastQueryFilters,
    ForecastRead,
    ForecastRunRead,
    ForecastValueRead,
    GenerateForecastResponse,
)
from app.services.alert_service import AlertService
from app.services.severity import legend
from app.utils.geo import BoundingBox
from app.utils.serialization import jsonable

router = APIRouter()

ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    404: {"description": "Resource not found"},
    422: {"description": "Invalid query parameters"},
}


def _to_read(forecast: Forecast) -> ForecastRead:
    return ForecastRead(
        id=forecast.id,
        run_id=forecast.run_id,
        district_id=forecast.district_id,
        target_time=forecast.target_time,
        lead_time_hours=forecast.lead_time_hours,
        predicted_rainfall_mm=forecast.predicted_rainfall_mm,
        predicted_probability=forecast.predicted_probability,
        lower_bound_mm=forecast.lower_bound_mm,
        upper_bound_mm=forecast.upper_bound_mm,
        severity=forecast.severity,
        status=forecast.status,
        issued_at=forecast.run.issued_at,
        model_version=forecast.run.model_version.version,
        district=forecast.district,
    )


@router.get(
    "",
    response_model=PaginatedResponse[ForecastRead],
    summary="List forecasts",
    description=(
        "Filter forecasts by district, region, bounding box, model version, "
        "issue time or target time."
    ),
)
async def list_forecasts(
    pagination: PaginationParams = Depends(),
    district_id: list[int] = Query(default_factory=list),
    region_id: int | None = Query(default=None),
    model_version: str | None = Query(default=None),
    min_rainfall_mm: float | None = Query(default=None, ge=0),
    severity: str | None = Query(default=None),
    issued_from: datetime | None = Query(default=None),
    issued_to: datetime | None = Query(default=None),
    target_from: datetime | None = Query(default=None),
    target_to: datetime | None = Query(default=None),
    min_lat: float | None = Query(default=None, ge=-90, le=90),
    min_lon: float | None = Query(default=None, ge=-180, le=180),
    max_lat: float | None = Query(default=None, ge=-90, le=90),
    max_lon: float | None = Query(default=None, ge=-180, le=180),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[ForecastRead]:
    filters = ForecastQueryFilters(
        district_id=list(district_id),
        region_id=region_id,
        model_version=model_version,
        min_rainfall_mm=min_rainfall_mm,
        severity=severity,
        issued_from=issued_from,
        issued_to=issued_to,
        target_from=target_from,
        target_to=target_to,
        min_lat=min_lat,
        min_lon=min_lon,
        max_lat=max_lat,
        max_lon=max_lon,
    )
    rows, total = await ForecastRepository(db).list_forecasts(
        filters, offset=pagination.offset, limit=pagination.limit
    )
    return PaginatedResponse.build(
        [_to_read(f) for f in rows], total, pagination.page, pagination.page_size
    )


FORECAST_LOADERS = (
    selectinload(Forecast.district),
    selectinload(Forecast.run).selectinload(ForecastRun.model_version),
)


@router.get(
    "/map",
    response_model=list[ForecastRead],
    summary="Forecasts for map rendering",
    description=(
        "Returns the most recent forecast per district within an optional bounding "
        "box. Designed for marker overlays, so it is not paginated and is bounded "
        "to the latest run."
    ),
)
async def map_forecasts(
    run_uid: str | None = Query(
        default=None, description="Specific run. Defaults to the latest run."
    ),
    min_lat: float | None = Query(default=None, ge=-90, le=90),
    min_lon: float | None = Query(default=None, ge=-180, le=180),
    max_lat: float | None = Query(default=None, ge=-90, le=90),
    max_lon: float | None = Query(default=None, ge=-180, le=180),
    min_rainfall_mm: float | None = Query(default=None, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[ForecastRead]:
    repo = ForecastRepository(db)
    if run_uid:
        run = await repo.get_run(run_uid)
        if run is None:
            raise NotFoundError(f"Forecast run '{run_uid}' does not exist.")
        run_id = run.id
    else:
        run = await repo.latest_run()
        if run is None:
            return []
        run_id = run.id

    rows = await repo.list_map_forecasts(
        run_id=run_id,
        bbox=BoundingBox(min_lat, min_lon, max_lat, max_lon),
        min_rainfall_mm=min_rainfall_mm,
    )
    return [_to_read(row) for row in rows]


@router.get(
    "/legend",
    response_model=list[dict],
    summary="Rainfall severity legend",
)
async def severity_legend() -> list[dict]:
    return legend()


@router.get(
    "/runs", response_model=PaginatedResponse[ForecastRunRead], summary="List forecast runs"
)
async def list_runs(
    pagination: PaginationParams = Depends(),
    model_version: str | None = Query(default=None),
    issued_from: datetime | None = Query(default=None),
    issued_to: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[ForecastRunRead]:
    repo = ForecastRepository(db)
    runs, total = await repo.list_runs(
        model_version=model_version,
        issued_from=issued_from,
        issued_to=issued_to,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    items = []
    for run in runs:
        count = await repo.run_forecast_count(run.id)
        items.append(
            ForecastRunRead.model_validate(
                {
                    **run.as_dict(),
                    "model_version": run.model_version.version,
                    "forecast_count": count,
                }
            )
        )
    return PaginatedResponse.build(items, total, pagination.page, pagination.page_size)


@router.get("/runs/{run_uid}", response_model=ForecastRunRead, summary="Forecast run detail")
async def get_run(run_uid: str, db: AsyncSession = Depends(get_db)) -> ForecastRunRead:
    repo = ForecastRepository(db)
    run = await repo.get_run(run_uid)
    if run is None:
        raise NotFoundError(f"Forecast run '{run_uid}' does not exist.")
    count = await repo.run_forecast_count(run.id)
    return ForecastRunRead.model_validate(
        {**run.as_dict(), "model_version": run.model_version.version, "forecast_count": count}
    )


@router.get(
    "/{forecast_id}",
    response_model=ForecastDetail,
    responses=ERROR_RESPONSES,
    summary="Forecast detail",
)
async def get_forecast(forecast_id: int, db: AsyncSession = Depends(get_db)) -> ForecastDetail:
    forecast = await ForecastRepository(db).get_forecast(forecast_id)
    if forecast is None:
        raise NotFoundError(f"Forecast {forecast_id} does not exist.")
    base = _to_read(forecast)
    return ForecastDetail(
        **base.model_dump(),
        feature_inputs=forecast.feature_inputs,
        values=[ForecastValueRead.model_validate(v) for v in forecast.values],
    )


@router.post(
    "/generate",
    response_model=GenerateForecastResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate and persist a forecast run",
    description=(
        "Runs the active model over the requested districts and stores the result. "
        "Heavy-rain alerts are derived from the generated forecasts.\n\n"
        "A run is identified by (model version, base time), so repeating the request "
        "for an issuance that already exists returns 200 with `forecasts_created: 0` "
        "instead of creating a duplicate. That makes a retried scheduler tick safe."
    ),
    responses={200: {"description": "The issuance already exists; nothing was created"}},
)
async def generate_forecasts(
    payload: ForecastGenerateRequest, db: AsyncSession = Depends(get_db)
) -> GenerateForecastResponse | JSONResponse:
    generator = ForecastGenerator(db)
    try:
        run, _predictions, created = await generator.generate_for_request(
            model_version=payload.model_version,
            issued_at=payload.issued_at,
            horizon_hours=payload.resolved_horizon(settings.default_forecast_horizon_hours),
            step_hours=payload.step_hours,
            district_ids=payload.district_ids,
        )
    except ValueError as exc:
        raise AppError(str(exc), code="invalid_issue_time", status_code=422) from exc

    await db.commit()

    stored = await ForecastRepository(db).list_forecasts_by_run(run.id, options=FORECAST_LOADERS)
    await AlertService(db).evaluate_forecasts(stored)

    response = GenerateForecastResponse(
        run_uid=run.run_uid,
        model_version=run.model_version.version,
        issued_at=run.issued_at,
        forecasts_created=created,
        valid_from=run.valid_from,
        valid_to=run.valid_to,
    )
    if created == 0:
        # The issuance already exists, so this is a read rather than a creation.
        return JSONResponse(
            status_code=status.HTTP_200_OK, content=jsonable(response.model_dump(mode="json"))
        )
    return response
