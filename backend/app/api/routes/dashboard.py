"""Dashboard aggregation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.dashboard import DashboardOverview
from app.services.dashboard_service import DashboardService

router = APIRouter()


@router.get(
    "/overview",
    response_model=DashboardOverview,
    summary="Dashboard overview",
    description=(
        "Single aggregated payload backing the dashboard: status counters, "
        "verification skill, severity distribution, top risk districts, observed "
        "and forecast series, active alerts, model health and the severity legend."
    ),
)
async def overview(
    lookback_days: int = Query(default=7, ge=1, le=90, description="Window for the time series"),
    db: AsyncSession = Depends(get_db),
) -> DashboardOverview:
    return await DashboardService(db).overview(lookback_days=lookback_days)
