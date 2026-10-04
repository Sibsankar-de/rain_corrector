"""Forecast and forecast run persistence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import ForecastStatus
from app.models.forecast import Forecast, ForecastRun, ForecastValue
from app.models.location import District
from app.models.model_version import ModelVersion
from app.schemas.forecast import ForecastQueryFilters
from app.utils.geo import BoundingBox


class ForecastRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _filtered(self, filters: ForecastQueryFilters) -> Select:
        stmt = (
            select(Forecast)
            .join(District, District.id == Forecast.district_id)
            .join(ForecastRun, ForecastRun.id == Forecast.run_id)
            .join(ModelVersion, ModelVersion.id == ForecastRun.model_version_id)
        )

        if filters.district_id:
            stmt = stmt.where(Forecast.district_id.in_(filters.district_id))
        if filters.region_id is not None:
            stmt = stmt.where(District.region_id == filters.region_id)
        if filters.model_version:
            stmt = stmt.where(ModelVersion.version == filters.model_version)
        if filters.min_rainfall_mm is not None:
            stmt = stmt.where(Forecast.predicted_rainfall_mm >= filters.min_rainfall_mm)
        if filters.severity:
            stmt = stmt.where(Forecast.severity == filters.severity)
        if filters.target_from:
            stmt = stmt.where(Forecast.target_time >= filters.target_from)
        if filters.target_to:
            stmt = stmt.where(Forecast.target_time <= filters.target_to)
        if filters.issued_from:
            stmt = stmt.where(ForecastRun.issued_at >= filters.issued_from)
        if filters.issued_to:
            stmt = stmt.where(ForecastRun.issued_at <= filters.issued_to)
        return stmt

    def _bbox(self, filters: ForecastQueryFilters) -> BoundingBox:
        return BoundingBox(filters.min_lat, filters.min_lon, filters.max_lat, filters.max_lon)

    async def list_forecasts(
        self, filters: ForecastQueryFilters, offset: int = 0, limit: int = 50
    ) -> tuple[list[Forecast], int]:
        base = self._filtered(filters)
        bbox_stmt = self._bbox(filters).apply(base)
        total = (
            await self.session.scalar(
                select(func.count()).select_from(bbox_stmt.order_by(None).subquery())
            )
            or 0
        )
        result = await self.session.execute(
            bbox_stmt.options(
                selectinload(Forecast.district),
                selectinload(Forecast.run).selectinload(ForecastRun.model_version),
            )
            .order_by(Forecast.target_time.desc(), Forecast.district_id)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_forecast(self, forecast_id: int) -> Forecast | None:
        return await self.session.scalar(
            select(Forecast)
            .where(Forecast.id == forecast_id)
            .options(
                selectinload(Forecast.district),
                selectinload(Forecast.values),
                selectinload(Forecast.run).selectinload(ForecastRun.model_version),
            )
        )

    async def list_map_forecasts(
        self,
        run_id: int,
        bbox: BoundingBox,
        min_rainfall_mm: float | None = None,
    ) -> list[Forecast]:
        """Forecasts for a map overlay: one run, optionally bounded, highest first.

        The bounding box is applied to district centroids. Renderers need the
        district relationship loaded, otherwise every marker would trigger a
        lazy load.
        """
        stmt = (
            select(Forecast)
            .join(District, District.id == Forecast.district_id)
            .where(Forecast.run_id == run_id)
            .options(
                selectinload(Forecast.district),
                selectinload(Forecast.run).selectinload(ForecastRun.model_version),
            )
        )
        stmt = bbox.apply(stmt)
        if min_rainfall_mm is not None:
            stmt = stmt.where(Forecast.predicted_rainfall_mm >= min_rainfall_mm)

        result = await self.session.execute(stmt.order_by(Forecast.predicted_rainfall_mm.desc()))
        return list(result.unique().scalars().all())

    async def list_forecasts_by_run(self, run_id: int, options: tuple = ()) -> list[Forecast]:
        result = await self.session.execute(
            select(Forecast).where(Forecast.run_id == run_id).options(*options)
        )
        return list(result.unique().scalars().all())

    async def get_run(self, run_uid: str) -> ForecastRun | None:
        return await self.session.scalar(
            select(ForecastRun)
            .where(ForecastRun.run_uid == run_uid)
            .options(selectinload(ForecastRun.model_version), selectinload(ForecastRun.forecasts))
        )

    async def latest_run(self, model_version: str | None = None) -> ForecastRun | None:
        stmt = select(ForecastRun).join(
            ModelVersion, ModelVersion.id == ForecastRun.model_version_id
        )
        if model_version:
            stmt = stmt.where(ModelVersion.version == model_version)
        return await self.session.scalar(stmt.order_by(ForecastRun.issued_at.desc()).limit(1))

    async def latest_issued_at(self, model_version: str | None = None) -> datetime | None:
        stmt = select(ForecastRun.issued_at).join(
            ModelVersion, ModelVersion.id == ForecastRun.model_version_id
        )
        if model_version:
            stmt = stmt.where(ModelVersion.version == model_version)
        return await self.session.scalar(stmt.order_by(ForecastRun.issued_at.desc()).limit(1))

    async def list_runs(
        self,
        model_version: str | None = None,
        issued_from: datetime | None = None,
        issued_to: datetime | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[ForecastRun], int]:
        stmt = select(ForecastRun).join(
            ModelVersion, ModelVersion.id == ForecastRun.model_version_id
        )
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        if model_version:
            stmt = stmt.where(ModelVersion.version == model_version)
            count_stmt = count_stmt.where(ModelVersion.version == model_version)
        if issued_from:
            stmt = stmt.where(ForecastRun.issued_at >= issued_from)
            count_stmt = count_stmt.where(ForecastRun.issued_at >= issued_from)
        if issued_to:
            stmt = stmt.where(ForecastRun.issued_at <= issued_to)
            count_stmt = count_stmt.where(ForecastRun.issued_at <= issued_to)

        total = await self.session.scalar(count_stmt) or 0
        result = await self.session.execute(
            stmt.options(selectinload(ForecastRun.model_version))
            .order_by(ForecastRun.issued_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def add_run(self, run: ForecastRun) -> ForecastRun:
        self.session.add(run)
        await self.session.flush()
        return run

    async def add_forecasts(self, forecasts: list[Forecast]) -> None:
        self.session.add_all(forecasts)
        await self.session.flush()

    async def add_values(self, values: list[ForecastValue]) -> None:
        self.session.add_all(values)
        await self.session.flush()

    async def run_forecast_count(self, run_id: int) -> int:
        return (
            await self.session.scalar(
                select(func.count()).select_from(Forecast).where(Forecast.run_id == run_id)
            )
            or 0
        )

    async def eligible_for_verification(
        self,
        grace_period_hours: int,
        lookback_days: int,
        model_version: str | None = None,
        district_ids: list[int] | None = None,
    ) -> list[Forecast]:
        from datetime import timedelta

        from app.utils.time import utcnow

        cutoff = utcnow() - timedelta(hours=grace_period_hours)
        horizon_start = cutoff - timedelta(days=lookback_days)

        stmt = (
            select(Forecast)
            .join(ForecastRun, ForecastRun.id == Forecast.run_id)
            .join(ModelVersion, ModelVersion.id == ForecastRun.model_version_id)
            .where(
                Forecast.status.in_([ForecastStatus.ISSUED, ForecastStatus.VERIFIED]),
                Forecast.target_time <= cutoff,
                Forecast.target_time >= horizon_start,
            )
        )
        if model_version:
            stmt = stmt.where(ModelVersion.version == model_version)
        if district_ids:
            stmt = stmt.where(Forecast.district_id.in_(district_ids))
        result = await self.session.execute(stmt.order_by(Forecast.target_time))
        return list(result.scalars().all())

    async def set_status(self, forecast: Forecast, status: ForecastStatus) -> None:
        forecast.status = status
        await self.session.flush()
