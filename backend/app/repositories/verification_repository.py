"""Verification result persistence and metric aggregation queries."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import VerificationStatus
from app.models.forecast import Forecast, ForecastRun
from app.models.location import District
from app.models.model_version import ModelVersion
from app.models.verification import VerificationBatch, VerificationResult


class VerificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_forecast(self, forecast_id: int) -> VerificationResult | None:
        return await self.session.scalar(
            select(VerificationResult).where(VerificationResult.forecast_id == forecast_id)
        )

    async def upsert(
        self,
        forecast_id: int,
        aggregate_id: int | None,
        status: VerificationStatus,
        values: dict,
        observed_at: datetime | None,
        verified_at: datetime | None,
    ) -> VerificationResult:
        existing = await self.get_for_forecast(forecast_id)
        if existing is None:
            existing = VerificationResult(forecast_id=forecast_id)
            self.session.add(existing)
        for key, value in values.items():
            setattr(existing, key, value)
        existing.aggregate_id = aggregate_id
        existing.status = status
        existing.observed_at = observed_at
        existing.verified_at = verified_at
        await self.session.flush()
        return existing

    def _scored_query(self) -> Select:
        """Result+forecast pairs for verified rows, joined through the model chain.

        Selecting both entities here keeps the join order identical between the
        row query and the count query, so a filter added to one cannot silently
        diverge from the other.
        """
        return (
            select(VerificationResult, Forecast)
            .join(Forecast, Forecast.id == VerificationResult.forecast_id)
            .join(District, District.id == Forecast.district_id)
            .where(VerificationResult.status == VerificationStatus.VERIFIED)
        )

    async def scored_rows(
        self,
        model_version: str | None = None,
        district_ids: list[int] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 10000,
    ) -> list[tuple[VerificationResult, Forecast]]:
        stmt = self._scored_query().options(selectinload(VerificationResult.forecast))
        if model_version:
            stmt = (
                stmt.join(ForecastRun, ForecastRun.id == Forecast.run_id)
                .join(ModelVersion, ModelVersion.id == ForecastRun.model_version_id)
                .where(ModelVersion.version == model_version)
            )
        if district_ids:
            stmt = stmt.where(Forecast.district_id.in_(district_ids))
        if start:
            stmt = stmt.where(VerificationResult.observed_at >= start)
        if end:
            stmt = stmt.where(VerificationResult.observed_at <= end)
        result = await self.session.execute(stmt.limit(limit))
        return [(row[0], row[1]) for row in result.all()]

    async def count_scored(
        self, model_version: str | None = None, district_ids: list[int] | None = None
    ) -> int:
        stmt = self._scored_query()
        if model_version:
            stmt = (
                stmt.join(ForecastRun, ForecastRun.id == Forecast.run_id)
                .join(ModelVersion, ModelVersion.id == ForecastRun.model_version_id)
                .where(ModelVersion.version == model_version)
            )
        if district_ids:
            stmt = stmt.where(Forecast.district_id.in_(district_ids))
        return await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    async def list_results(
        self,
        model_version: str | None = None,
        district_ids: list[int] | None = None,
        status: VerificationStatus | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[VerificationResult], int]:
        stmt = select(VerificationResult).join(
            Forecast, Forecast.id == VerificationResult.forecast_id
        )
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        if model_version:
            stmt = (
                stmt.join(ForecastRun, ForecastRun.id == Forecast.run_id)
                .join(ModelVersion, ModelVersion.id == ForecastRun.model_version_id)
                .where(ModelVersion.version == model_version)
            )
            count_stmt = (
                count_stmt.join(ForecastRun, ForecastRun.id == Forecast.run_id)
                .join(ModelVersion, ModelVersion.id == ForecastRun.model_version_id)
                .where(ModelVersion.version == model_version)
            )
        if district_ids:
            stmt = stmt.where(Forecast.district_id.in_(district_ids))
            count_stmt = count_stmt.where(Forecast.district_id.in_(district_ids))
        if status:
            stmt = stmt.where(VerificationResult.status == status)
            count_stmt = count_stmt.where(VerificationResult.status == status)

        total = await self.session.scalar(count_stmt) or 0
        result = await self.session.execute(
            stmt.options(selectinload(VerificationResult.forecast))
            .order_by(VerificationResult.observed_at.desc().nullslast())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def add_batch(self, batch: VerificationBatch) -> VerificationBatch:
        self.session.add(batch)
        await self.session.flush()
        return batch

    async def list_batches(self, limit: int = 20) -> list[VerificationBatch]:
        result = await self.session.execute(
            select(VerificationBatch).order_by(VerificationBatch.started_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def forecast_status_counts(self, model_version: str | None = None) -> dict[str, int]:
        stmt = (
            select(Forecast.status, func.count())
            .join(ForecastRun, ForecastRun.id == Forecast.run_id)
            .join(ModelVersion, ModelVersion.id == ForecastRun.model_version_id)
            .group_by(Forecast.status)
        )
        if model_version:
            stmt = stmt.where(ModelVersion.version == model_version)
        result = await self.session.execute(stmt)
        return {
            str(status.value if hasattr(status, "value") else status): count
            for status, count in result.all()
        }
