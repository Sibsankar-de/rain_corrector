"""Alert generation and lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AlertSeverity, AlertStatus
from app.core.exceptions import NotFoundError
from app.core.logging_config import get_logger
from app.models.forecast import Forecast
from app.repositories.alert_repository import AlertRepository
from app.schemas.forecast import AlertRead, AlertStatusUpdate
from app.services.severity import SEVERITY_TO_ALERT
from app.utils.time import utcnow

logger = get_logger(__name__)

MIN_SEVERITY_FOR_ALERT = "heavy"
ALERT_COOLDOWN_HOURS = 6


class AlertService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AlertRepository(session)

    async def evaluate_forecasts(self, forecasts: list[Forecast]) -> int:
        created = 0
        for forecast in forecasts:
            if not _should_alert(forecast.severity, forecast.predicted_rainfall_mm):
                continue
            if await self._within_cooldown(forecast.district_id):
                continue
            severity = SEVERITY_TO_ALERT.get(forecast.severity, AlertSeverity.INFO)
            await self.repo.create(
                {
                    "district_id": forecast.district_id,
                    "forecast_id": forecast.id,
                    "severity": severity,
                    "status": AlertStatus.OPEN,
                    "alert_type": "heavy_rainfall",
                    "title": f"Heavy rainfall predicted: {forecast.severity.replace('_', ' ')}",
                    "message": (
                        f"{forecast.predicted_rainfall_mm:.1f} mm of rain predicted for the "
                        f"{forecast.lead_time_hours:.0f}h horizon. District under watch for "
                        "heavy rainfall."
                    ),
                    "threshold_mm": _threshold_for(forecast.severity),
                    "observed_value_mm": forecast.predicted_rainfall_mm,
                    "valid_from": forecast.target_time - timedelta(hours=forecast.lead_time_hours),
                    "valid_to": forecast.target_time + timedelta(hours=6),
                }
            )
            created += 1
        if created:
            await self.session.commit()
            logger.info("alerts_created", count=created, threshold_severity=MIN_SEVERITY_FOR_ALERT)
        return created

    async def _within_cooldown(self, district_id: int) -> bool:
        since = utcnow() - timedelta(hours=ALERT_COOLDOWN_HOURS)
        return await self.repo.has_recent_alert(district_id, since)

    async def list_alerts(
        self,
        status: AlertStatus | None,
        severity: AlertSeverity | None,
        district_ids: list[int] | None,
        valid_at: datetime | None,
        offset: int,
        limit: int,
    ) -> tuple[list[AlertRead], int]:
        records, total = await self.repo.list_alerts(
            status=status,
            severity=severity,
            district_ids=district_ids,
            valid_at=valid_at,
            offset=offset,
            limit=limit,
        )
        return [to_schema(a) for a in records], total

    async def summary(self) -> dict[str, int]:
        return await self.repo.summary()

    async def update_status(
        self, alert_id: int, payload: AlertStatusUpdate, user_id: int | None
    ) -> AlertRead:
        alert = await self.repo.get(alert_id)
        if alert is None:
            raise NotFoundError(f"Alert {alert_id} does not exist.")
        alert.status = payload.status
        if payload.status in (AlertStatus.ACKNOWLEDGED, AlertStatus.RESOLVED):
            alert.acknowledged_at = utcnow()
            alert.acknowledged_by_id = user_id
        await self.session.commit()
        logger.info("alert_status_changed", alert_id=alert_id, status=payload.status.value)
        return to_schema(alert)


def to_schema(alert) -> AlertRead:
    schema = AlertRead.model_validate(alert)
    schema.district_name = alert.district.name if alert.district else None
    return schema


def _should_alert(severity: str, rainfall_mm: float) -> bool:
    order = ["none", "light", "moderate", "heavy", "very_heavy", "extreme"]
    minimum = order.index(MIN_SEVERITY_FOR_ALERT)
    if severity in order:
        return order.index(severity) >= minimum
    return rainfall_mm >= 15.6


def _threshold_for(severity: str) -> float:
    thresholds = {
        "heavy": 15.6,
        "very_heavy": 31.8,
        "extreme": 51.2,
    }
    return thresholds.get(severity, 15.6)
