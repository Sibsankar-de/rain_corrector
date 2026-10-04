"""Model registry and training run persistence.

Alerts have their own repository, and users are only reachable through the
security dependency, so neither lives here.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ModelStatus, TrainingStatus
from app.models.forecast import Forecast, ForecastRun
from app.models.model_version import ModelVersion, TrainingRun
from app.models.verification import VerificationResult
from app.utils.time import utcnow


class ModelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active(self) -> ModelVersion | None:
        return await self.session.scalar(
            select(ModelVersion)
            .where(ModelVersion.status == ModelStatus.ACTIVE)
            .order_by(ModelVersion.activated_at.desc().nullslast())
            .limit(1)
        )

    async def get_by_version(self, version: str) -> ModelVersion | None:
        return await self.session.scalar(
            select(ModelVersion).where(ModelVersion.version == version)
        )

    async def get(self, model_id: int) -> ModelVersion:
        record = await self.session.get(ModelVersion, model_id)
        if record is None:
            from app.core.exceptions import NotFoundError

            raise NotFoundError(f"Model version {model_id} does not exist.")
        return record

    async def list_versions(
        self, status: ModelStatus | None = None, offset: int = 0, limit: int = 50
    ) -> tuple[list[ModelVersion], int]:
        from sqlalchemy import func

        stmt = select(ModelVersion)
        count_stmt = select(func.count()).select_from(ModelVersion)
        if status is not None:
            stmt = stmt.where(ModelVersion.status == status)
            count_stmt = count_stmt.where(ModelVersion.status == status)
        total = await self.session.scalar(count_stmt) or 0
        result = await self.session.execute(
            stmt.order_by(ModelVersion.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total

    async def next_version(self, model_name: str) -> str:
        result = await self.session.execute(
            select(ModelVersion.version)
            .where(ModelVersion.model_name == model_name)
            .order_by(ModelVersion.version.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        if latest is None:
            return "v001"
        digits = "".join(ch for ch in latest if ch.isdigit())
        return f"v{int(digits or 0) + 1:03d}"

    async def create_version(self, payload: dict) -> ModelVersion:
        record = ModelVersion(**payload)
        self.session.add(record)
        await self.session.flush()
        return record

    async def set_status(self, record: ModelVersion, status: ModelStatus) -> None:
        if status == ModelStatus.ACTIVE:
            await self.session.execute(
                update(ModelVersion)
                .where(ModelVersion.id != record.id, ModelVersion.status == ModelStatus.ACTIVE)
                .values(status=ModelStatus.ARCHIVED, archived_at=utcnow())
            )
            record.activated_at = utcnow()
            record.archived_at = None
        elif status == ModelStatus.ARCHIVED:
            record.archived_at = utcnow()
        record.status = status
        await self.session.flush()

    async def create_training_run(self, payload: dict) -> TrainingRun:
        run = TrainingRun(**payload)
        self.session.add(run)
        await self.session.flush()
        return run

    async def get_training_run(self, run_id: str) -> TrainingRun | None:
        return await self.session.scalar(select(TrainingRun).where(TrainingRun.run_id == run_id))

    async def list_training_runs(self, limit: int = 50) -> list[TrainingRun]:
        result = await self.session.execute(
            select(TrainingRun).order_by(TrainingRun.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def last_successful_run_at(self) -> datetime | None:
        return await self.session.scalar(
            select(TrainingRun.finished_at)
            .where(TrainingRun.status == TrainingStatus.SUCCEEDED)
            .order_by(TrainingRun.finished_at.desc())
            .limit(1)
        )

    async def performance_snapshot(self, model_version: str, limit: int = 20000) -> dict:
        """Aggregate verification numbers for a model version, used for promotion."""
        from sqlalchemy import func

        stmt = (
            select(
                func.avg(func.abs(VerificationResult.error_mm)),
                func.sqrt(func.avg(func.pow(VerificationResult.error_mm, 2))),
                func.count(),
            )
            .select_from(VerificationResult)
            .join(Forecast, Forecast.id == VerificationResult.forecast_id)
            .join(ForecastRun, ForecastRun.id == Forecast.run_id)
            .join(ModelVersion, ModelVersion.id == ForecastRun.model_version_id)
            .where(
                ModelVersion.version == model_version,
                VerificationResult.status == "verified",
            )
        )
        mae, rmse, count = (await self.session.execute(stmt)).one()
        return {
            "mae_mm": float(mae) if mae is not None else None,
            "rmse_mm": float(rmse) if rmse is not None else None,
            "sample_size": int(count or 0),
        }
