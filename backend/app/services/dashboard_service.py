"""Dashboard aggregation.

Composes one payload from several tables so the numbers on screen come from a
single consistent snapshot. All SQL lives in `DashboardRepository`; this service
only shapes the result.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.core.enums import AlertStatus
from app.ml.registry import model_registry
from app.repositories.alert_repository import AlertRepository
from app.repositories.dashboard_repository import DashboardRepository
from app.repositories.forecast_repository import ForecastRepository
from app.schemas.dashboard import (
    ActiveAlertItem,
    DashboardOverview,
    DistrictRiskItem,
    LegendEntry,
    ModelHealthItem,
    ObservedRainfallItem,
    PlatformSummary,
    SeverityDistribution,
    StatusSnapshot,
    TimeseriesPoint,
)
from app.services.severity import legend as severity_legend
from app.services.verification_service import VerificationService
from app.utils.time import utcnow


class DashboardService:
    def __init__(self, session) -> None:
        self.session = session
        self.repo = DashboardRepository(session)
        self.forecast_repo = ForecastRepository(session)
        self.alert_repo = AlertRepository(session)
        self.verification_service = VerificationService(session)

    async def overview(self, lookback_days: int = 7) -> DashboardOverview:
        now = utcnow()
        window_start = now - timedelta(days=lookback_days)

        latest_run = await self.forecast_repo.latest_run()
        active_model = await self.repo.get_active_model()
        verification = await self.verification_service.metrics_summary()

        return DashboardOverview(
            generated_at=now,
            active_model_version=active_model.version if active_model else None,
            model_loaded_version=model_registry.active_version,
            latest_forecast_run=latest_run.run_uid if latest_run else None,
            latest_forecast_issued_at=latest_run.issued_at if latest_run else None,
            status=await self._status_snapshot(now),
            summary=PlatformSummary(
                forecasts_last_7d=await self.repo.count_forecasts_since(window_start),
                districts_at_risk=await self.repo.count_districts_at_risk(),
                open_alerts=await self.repo.count_open_alerts(),
                observed_rainfall_mm_7d=await self.repo.sum_observed_since(window_start),
            ),
            verification=verification,
            severity_distribution=await self._severity_distribution(),
            top_risk_districts=await self._top_risk_districts(limit=8),
            observed_rainfall_series=await self._observed_series(window_start),
            forecast_vs_observed_series=await self._forecast_series(window_start),
            alerts=await self._active_alerts(limit=6),
            legend=[LegendEntry.model_validate(entry) for entry in severity_legend()],
            models=await self._model_health(),
        )

    async def _status_snapshot(self, now: datetime) -> StatusSnapshot:
        counts = await self.repo.forecast_status_counts()
        return StatusSnapshot(
            forecasts_issued=counts.get("issued", 0) + counts.get("verified", 0),
            forecasts_verified=counts.get("verified", 0),
            forecasts_pending=await self.repo.count_pending_verifications(),
            latest_observation=await self.repo.latest_observation_at(),
            evaluated_at=now,
        )

    async def _severity_distribution(self) -> list[SeverityDistribution]:
        return [
            SeverityDistribution(severity=severity, count=count, mean_rainfall_mm=round(mean, 2))
            for severity, count, mean in await self.repo.severity_distribution()
        ]

    async def _top_risk_districts(self, limit: int) -> list[DistrictRiskItem]:
        latest_run = await self.forecast_repo.latest_run()
        if latest_run is None:
            return []
        return [
            DistrictRiskItem(
                district_id=row[0],
                code=row[1],
                name=row[2],
                latitude=row[3],
                longitude=row[4],
                predicted_rainfall_mm=round(float(row[5]), 2),
                upper_bound_mm=round(float(row[6]), 2) if row[6] is not None else None,
                severity=row[7],
                target_time=row[8],
            )
            for row in await self.repo.top_districts_for_run(latest_run.id, limit)
        ]

    async def _observed_series(self, since: datetime) -> list[ObservedRainfallItem]:
        return [
            ObservedRainfallItem(
                observed_at=observed_at,
                mean_rainfall_mm=round(mean, 2),
                total_rainfall_mm=round(total, 2),
            )
            for observed_at, mean, total in await self.repo.observed_rainfall_series(since)
        ]

    async def _forecast_series(self, since: datetime) -> list[TimeseriesPoint]:
        return [
            TimeseriesPoint(
                timestamp=issued_at,
                value=round(float(value or 0.0), 2),
                lower=round(float(lower), 2) if lower is not None else None,
                upper=round(float(upper), 2) if upper is not None else None,
            )
            for issued_at, value, lower, upper in await self.repo.forecast_series(since)
        ]

    async def _active_alerts(self, limit: int) -> list[ActiveAlertItem]:
        """Unresolved alerts, most recent first.

        Alerts are not auto-resolved on expiry: an unacknowledged alert for a
        window that has passed is still an outstanding operational item, so the
        dashboard lists it rather than silently dropping it.
        """
        alerts, _ = await self.alert_repo.list_alerts(
            status=AlertStatus.OPEN, offset=0, limit=limit
        )
        return [
            ActiveAlertItem(
                id=alert.id,
                district_id=alert.district_id,
                district_name=alert.district.name if alert.district else None,
                severity=alert.severity.value,
                title=alert.title,
                message=alert.message,
                valid_from=alert.valid_from,
                valid_to=alert.valid_to,
            )
            for alert in alerts
        ]

    async def _model_health(self) -> list[ModelHealthItem]:
        items: list[ModelHealthItem] = []
        for record in await self.repo.recent_models():
            snapshot = await self.repo.verification_for_model(record.id)
            items.append(
                ModelHealthItem(
                    model_name=record.model_name,
                    version=record.version,
                    status=record.status.value,
                    trained_at=record.created_at,
                    mae_mm=snapshot["mae"],
                    rmse_mm=snapshot["rmse"],
                    sample_size=int(snapshot["count"] or 0),
                    is_loaded=model_registry.active_version == record.version,
                )
            )
        return items
