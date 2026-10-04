"""Alert persistence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import AlertSeverity, AlertStatus
from app.models.alert import Alert


class AlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, payload: dict) -> Alert:
        alert = Alert(**payload)
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def get(self, alert_id: int) -> Alert | None:
        return await self.session.scalar(
            select(Alert).options(selectinload(Alert.district)).where(Alert.id == alert_id)
        )

    async def list_alerts(
        self,
        status: AlertStatus | None = None,
        severity: AlertSeverity | None = None,
        district_ids: list[int] | None = None,
        valid_at: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Alert], int]:
        stmt = select(Alert).options(selectinload(Alert.district))
        count_stmt = select(func.count()).select_from(Alert)
        conditions = []

        if status is not None:
            conditions.append(Alert.status == status)
        if severity is not None:
            conditions.append(Alert.severity == severity)
        if district_ids:
            conditions.append(Alert.district_id.in_(district_ids))
        if valid_at is not None:
            conditions.extend([Alert.valid_from <= valid_at, Alert.valid_to >= valid_at])

        for condition in conditions:
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        total = await self.session.scalar(count_stmt) or 0
        result = await self.session.execute(
            stmt.order_by(Alert.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total

    async def summary(self) -> dict[str, int]:
        rows = (
            await self.session.execute(
                select(Alert.severity, func.count())
                .where(Alert.status != AlertStatus.RESOLVED)
                .group_by(Alert.severity)
            )
        ).all()
        return {
            str(severity.value if hasattr(severity, "value") else severity): count
            for severity, count in rows
        }

    async def has_recent_alert(self, district_id: int, since: datetime) -> bool:
        """True when the district already has an alert inside the window.

        Alert deduplication is a query, so it belongs here rather than in the
        service that decides whether to raise one.
        """
        recent = await self.session.scalar(
            select(Alert.id)
            .where(Alert.district_id == district_id, Alert.created_at >= since)
            .limit(1)
        )
        return recent is not None
