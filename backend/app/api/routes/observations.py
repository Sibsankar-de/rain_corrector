"""Observation ingestion and read endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.observation_repository import ObservationRepository
from app.schemas.location import (
    DistrictAggregateRead,
    IngestionResult,
    ObservationBatchCreate,
    ObservationRead,
)
from app.services.location_service import ObservationService

router = APIRouter()


@router.post(
    "/ingest",
    response_model=IngestionResult,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest station observations",
    description=(
        "Accepts a batch of station readings. Records already present for the same "
        "station/timestamp/window are treated as duplicates and skipped. When "
        "`recompute_aggregates` is set, daily district aggregates are recalculated "
        "for the affected districts."
    ),
)
async def ingest_observations(
    payload: ObservationBatchCreate, db: AsyncSession = Depends(get_db)
) -> IngestionResult:
    return await ObservationService(db).ingest(payload)


@router.get(
    "/district/{district_id}",
    response_model=list[ObservationRead],
    summary="Station observations for a district",
)
async def district_observations(
    district_id: int,
    start: datetime = Query(..., description="Inclusive lower bound (ISO 8601)"),
    end: datetime = Query(..., description="Inclusive upper bound (ISO 8601)"),
    limit: int = Query(default=1000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
) -> list[ObservationRead]:
    rows = await ObservationService(db).list_for_district(
        district_id, start=start, end=end, limit=limit
    )
    return [ObservationRead.model_validate(r) for r in rows]


@router.get(
    "/aggregates",
    response_model=list[DistrictAggregateRead],
    summary="Daily district rainfall aggregates",
)
async def list_aggregates(
    district_id: int = Query(..., description="District id"),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    limit: int = Query(default=365, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
) -> list[DistrictAggregateRead]:
    rows = await ObservationRepository(db).list_daily_aggregates(
        district_id=district_id, start=start, end=end, limit=limit
    )
    return [DistrictAggregateRead.model_validate(row) for row in rows]
