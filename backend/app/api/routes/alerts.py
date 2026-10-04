"""Alert query and lifecycle endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import AlertSeverity, AlertStatus
from app.core.exceptions import NotFoundError
from app.core.security import require_api_key
from app.schemas.common import PaginatedResponse, PaginationParams
from app.schemas.forecast import AlertRead, AlertStatusUpdate
from app.services.alert_service import AlertService, to_schema

router = APIRouter()


@router.get("", response_model=PaginatedResponse[AlertRead], summary="List alerts")
async def list_alerts(
    pagination: PaginationParams = Depends(),
    alert_status: AlertStatus | None = Query(default=None, alias="status"),
    severity: AlertSeverity | None = Query(default=None),
    district_id: list[int] = Query(default_factory=list),
    valid_at: datetime | None = Query(
        default=None, description="Only alerts valid at this instant"
    ),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[AlertRead]:
    items, total = await AlertService(db).list_alerts(
        status=alert_status,
        severity=severity,
        district_ids=list(district_id) or None,
        valid_at=valid_at,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return PaginatedResponse.build(items, total, pagination.page, pagination.page_size)


@router.get("/summary", response_model=dict[str, int], summary="Open alert counts by severity")
async def alert_summary(db: AsyncSession = Depends(get_db)) -> dict[str, int]:
    return await AlertService(db).summary()


@router.get("/{alert_id}", response_model=AlertRead, summary="Alert detail")
async def get_alert(alert_id: int, db: AsyncSession = Depends(get_db)) -> AlertRead:

    alert = await AlertService(db).repo.get(alert_id)
    if alert is None:
        raise NotFoundError(f"Alert {alert_id} does not exist.")
    return to_schema(alert)


@router.patch(
    "/{alert_id}",
    response_model=AlertRead,
    summary="Acknowledge or resolve an alert",
)
async def update_alert(
    alert_id: int,
    payload: AlertStatusUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_api_key),
) -> AlertRead:
    return await AlertService(db).update_status(alert_id, payload, user.id)
