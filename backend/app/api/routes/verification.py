"""Forecast verification endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import VerificationStatus
from app.core.exceptions import NotFoundError
from app.repositories.forecast_repository import ForecastRepository
from app.repositories.verification_repository import VerificationRepository
from app.schemas.common import PaginatedResponse, PaginationParams
from app.schemas.forecast import (
    VerificationMetricsSummary,
    VerificationResultRead,
    VerificationRunRequest,
    VerificationRunResponse,
)
from app.services.verification_service import VerificationService

router = APIRouter()


@router.get(
    "/results",
    response_model=PaginatedResponse[VerificationResultRead],
    summary="List verification results",
)
async def list_results(
    pagination: PaginationParams = Depends(),
    model_version: str | None = Query(default=None),
    district_id: list[int] = Query(default_factory=list),
    result_status: VerificationStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[VerificationResultRead]:
    rows, total = await VerificationRepository(db).list_results(
        model_version=model_version,
        district_ids=list(district_id) or None,
        status=result_status,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return PaginatedResponse.build(
        [VerificationResultRead.model_validate(r) for r in rows],
        total,
        pagination.page,
        pagination.page_size,
    )


@router.get(
    "/metrics",
    response_model=VerificationMetricsSummary,
    summary="Aggregated verification metrics",
    description=(
        "Continuous (MAE, RMSE, bias, NSE) and categorical (POD, FAR, CSI, "
        "Brier) scores computed over verified forecasts only, with breakdowns by "
        "lead-time bucket and forecast severity."
    ),
)
async def metrics(
    model_version: str | None = Query(default=None),
    district_id: list[int] = Query(default_factory=list),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> VerificationMetricsSummary:
    return await VerificationService(db).metrics_summary(
        model_version=model_version,
        district_ids=list(district_id) or None,
        start=start,
        end=end,
    )


@router.get(
    "/batches",
    response_model=list[dict],
    summary="Recent verification job runs",
)
async def list_batches(
    limit: int = Query(default=20, ge=1, le=100), db: AsyncSession = Depends(get_db)
) -> list[dict]:
    return [b.as_dict() for b in await VerificationRepository(db).list_batches(limit=limit)]


@router.get(
    "/forecast/{forecast_id}",
    response_model=VerificationResultRead,
    summary="Verification result for one forecast",
)
async def for_forecast(
    forecast_id: int, db: AsyncSession = Depends(get_db)
) -> VerificationResultRead:
    if await ForecastRepository(db).get_forecast(forecast_id) is None:
        raise NotFoundError(f"Forecast {forecast_id} does not exist.")
    result = await VerificationRepository(db).get_for_forecast(forecast_id)
    if result is None:
        raise NotFoundError(f"Forecast {forecast_id} has not been verified yet.")
    return VerificationResultRead.model_validate(result)


@router.post(
    "/run",
    response_model=VerificationRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Run verification for matured forecasts",
    description=(
        "Scores forecasts whose target time has passed the configured grace "
        "period. Forecasts without a matching observation stay pending and are "
        "not scored."
    ),
)
async def run_verification(
    payload: VerificationRunRequest, db: AsyncSession = Depends(get_db)
) -> VerificationRunResponse:
    service = VerificationService(db)
    batch = await service.run_verification(
        model_version=payload.model_version,
        district_ids=payload.district_ids,
        lookback_days=payload.lookback_days,
        force=payload.force,
        triggered_by="api",
    )
    await db.commit()
    summary = (
        await service.metrics_summary(
            model_version=payload.model_version, district_ids=payload.district_ids
        )
        if batch.forecasts_verified
        else None
    )
    return VerificationRunResponse(
        batch_uid=batch.batch_uid,
        candidates_considered=batch.candidates_considered,
        forecasts_verified=batch.forecasts_verified,
        forecasts_pending=batch.forecasts_pending,
        metrics=summary,
        started_at=batch.started_at,
        finished_at=batch.finished_at,
    )
