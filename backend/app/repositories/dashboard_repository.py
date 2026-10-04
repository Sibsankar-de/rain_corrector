"""Read-only aggregate queries backing the dashboard payload.

The dashboard needs counters from several tables at once. Collecting them in one
repository keeps the SQL in the data layer while the service stays pure
composition, and gives every figure a single consistent snapshot.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.forecast import Forecast, ForecastRun
from app.models.location import District
from app.models.model_version import ModelVersion
from app.models.observation import DistrictAggregate
from app.models.verification import VerificationResult


class DashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active_model(self) -> ModelVersion | None:
        return await self.session.scalar(
            select(ModelVersion)
            .where(ModelVersion.status == "active")
            .order_by(ModelVersion.activated_at.desc().nullslast())
            .limit(1)
        )

    async def count_forecasts_since(self, since: datetime) -> int:
        return (
            await self.session.scalar(
                select(func.count())
                .select_from(Forecast)
                .join(ForecastRun, ForecastRun.id == Forecast.run_id)
                .where(ForecastRun.issued_at >= since)
            )
            or 0
        )

    async def count_districts_at_risk(self) -> int:
        return (
            await self.session.scalar(
                select(func.count(func.distinct(Forecast.district_id))).where(
                    Forecast.severity.in_(["heavy", "very_heavy", "extreme"])
                )
            )
            or 0
        )

    async def count_open_alerts(self) -> int:
        return (
            await self.session.scalar(
                select(func.count()).select_from(Alert).where(Alert.status != "resolved")
            )
            or 0
        )

    async def sum_observed_since(self, since: datetime) -> float:
        value = await self.session.scalar(
            select(func.sum(DistrictAggregate.rainfall_mm)).where(
                DistrictAggregate.observed_at >= since
            )
        )
        return round(float(value or 0.0), 2)

    async def forecast_status_counts(self) -> dict[str, int]:
        rows = (
            await self.session.execute(
                select(Forecast.status, func.count()).group_by(Forecast.status)
            )
        ).all()
        return {
            str(status.value if hasattr(status, "value") else status): count
            for status, count in rows
        }

    async def count_pending_verifications(self) -> int:
        return (
            await self.session.scalar(
                select(func.count())
                .select_from(VerificationResult)
                .where(VerificationResult.status == "pending_observation")
            )
            or 0
        )

    async def latest_observation_at(self) -> datetime | None:
        return await self.session.scalar(select(func.max(DistrictAggregate.observed_at)))

    async def severity_distribution(self) -> list[tuple[str, int, float]]:
        rows = (
            await self.session.execute(
                select(
                    Forecast.severity,
                    func.count(),
                    func.avg(Forecast.predicted_rainfall_mm),
                ).group_by(Forecast.severity)
            )
        ).all()
        return [(row[0], row[1], float(row[2] or 0.0)) for row in rows]

    async def top_districts_for_run(self, run_id: int, limit: int) -> list[tuple[Any, ...]]:
        """Highest predicted rainfall in a run, with the district coordinates.

        Not filtered to heavy forecasts: on a dry day the correct report is
        "nothing at risk", and an empty list is honest where a filtered list
        would imply the districts were never assessed.
        """
        stmt = (
            select(
                District.id,
                District.code,
                District.name,
                District.centroid_lat,
                District.centroid_lon,
                Forecast.predicted_rainfall_mm,
                Forecast.upper_bound_mm,
                Forecast.severity,
                Forecast.target_time,
            )
            .join(Forecast, Forecast.district_id == District.id)
            .where(Forecast.run_id == run_id)
            .order_by(Forecast.predicted_rainfall_mm.desc())
            .limit(limit)
        )
        return [tuple(row) for row in (await self.session.execute(stmt)).all()]

    async def observed_rainfall_series(self, since: datetime) -> list[tuple[Any, ...]]:
        stmt = (
            select(
                DistrictAggregate.observed_at,
                func.avg(DistrictAggregate.rainfall_mm),
                func.sum(DistrictAggregate.rainfall_mm),
            )
            .where(DistrictAggregate.observed_at >= since)
            .group_by(DistrictAggregate.observed_at)
            .order_by(DistrictAggregate.observed_at)
        )
        return [
            (row[0], float(row[1] or 0.0), float(row[2] or 0.0))
            for row in (await self.session.execute(stmt)).all()
        ]

    async def forecast_series(self, since: datetime) -> list[tuple[Any, ...]]:
        stmt = (
            select(
                ForecastRun.issued_at,
                func.avg(Forecast.predicted_rainfall_mm),
                func.avg(Forecast.lower_bound_mm),
                func.avg(Forecast.upper_bound_mm),
            )
            .join(Forecast, Forecast.run_id == ForecastRun.id)
            .where(ForecastRun.issued_at >= since)
            .group_by(ForecastRun.issued_at)
            .order_by(ForecastRun.issued_at)
        )
        return [tuple(row) for row in (await self.session.execute(stmt)).all()]

    async def recent_models(self, limit: int = 6) -> list[ModelVersion]:
        result = await self.session.execute(
            select(ModelVersion).order_by(ModelVersion.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def verification_for_model(self, model_version_id: int) -> dict[str, Any]:
        """MAE, RMSE and sample size over verified rows for one model version."""
        stmt = self._verification_for_model_query().where(
            ForecastRun.model_version_id == model_version_id,
            VerificationResult.status == "verified",
        )
        mae, rmse, count = (await self.session.execute(stmt)).one()
        return {
            "mae": round(float(mae), 3) if mae is not None else None,
            "rmse": round(float(rmse), 3) if rmse is not None else None,
            "count": int(count or 0),
        }

    @staticmethod
    def _verification_for_model_query() -> Select:
        return (
            select(
                func.avg(func.abs(VerificationResult.error_mm)),
                func.sqrt(func.avg(func.pow(VerificationResult.error_mm, 2))),
                func.count(),
            )
            .select_from(VerificationResult)
            .join(Forecast, Forecast.id == VerificationResult.forecast_id)
            .join(ForecastRun, ForecastRun.id == Forecast.run_id)
        )
