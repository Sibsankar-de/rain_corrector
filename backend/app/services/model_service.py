"""Model registry service: metadata queries and promotion policy."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import ModelStatus, TrainingStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging_config import get_logger
from app.ml.registry import model_registry
from app.repositories.model_repository import ModelRepository
from app.schemas.forecast import (
    ModelPromotionRequest,
    ModelPromotionResponse,
    ModelVersionDetail,
    ModelVersionRead,
    TrainingRunRead,
)
from app.utils.time import utcnow

logger = get_logger(__name__)

PROMOTION_POLICIES = ("auto_promote_if_better", "manual_only", "force")


class ModelService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ModelRepository(session)

    async def list_versions(
        self, status: ModelStatus | None, offset: int, limit: int
    ) -> tuple[list[ModelVersionRead], int]:
        records, total = await self.repo.list_versions(status=status, offset=offset, limit=limit)
        return [ModelVersionRead.model_validate(r) for r in records], total

    async def get_version(self, version: str) -> ModelVersionDetail:
        record = await self.repo.get_by_version(version)
        if record is None:
            raise NotFoundError(f"Model version '{version}' does not exist.")
        return ModelVersionDetail.model_validate(record)

    async def get_active(self) -> ModelVersionRead | None:
        record = await self.repo.get_active()
        return ModelVersionRead.model_validate(record) if record else None

    async def list_training_runs(self, limit: int = 50) -> list[TrainingRunRead]:
        runs = await self.repo.list_training_runs(limit=limit)
        return [TrainingRunRead.model_validate(r) for r in runs]

    async def serve_active_model(self) -> str | None:
        """Load the database-active model into the process cache, if needed."""
        if settings.model_version:
            artifact = model_registry.reload_if_needed(settings.model_version)
            return artifact.version if artifact else None
        record = await self.repo.get_active()
        if record is None:
            return model_registry.active_version
        artifact = model_registry.reload_if_needed(record.version)
        return artifact.version if artifact else None

    async def promote(self, request: ModelPromotionRequest) -> ModelPromotionResponse:
        policy = request.policy or settings.default_promotion_policy
        if policy not in PROMOTION_POLICIES:
            raise ValidationError(
                f"Unknown promotion policy '{policy}'. Expected one of {PROMOTION_POLICIES}."
            )

        candidate = await self.repo.get_by_version(request.target_version)
        if candidate is None:
            raise NotFoundError(f"Model version '{request.target_version}' does not exist.")
        retired = candidate.status in (ModelStatus.ARCHIVED, ModelStatus.REJECTED)
        if retired and policy != "force":
            raise ConflictError(
                f"Model version '{candidate.version}' is {candidate.status.value} and cannot be "
                f"promoted under policy '{policy}'."
            )

        current = await self.repo.get_active()
        candidate_perf = await self.repo.performance_snapshot(candidate.version)
        current_perf = await self.repo.performance_snapshot(current.version) if current else {}

        competes = current is not None and current.version != candidate.version
        gated = policy == "auto_promote_if_better" and competes
        if gated and not _is_better(candidate_perf, current_perf):
            active_version = current.version if current else None
            logger.info(
                "promotion_rejected_candidate_not_better",
                candidate=candidate.version,
                current=active_version,
                candidate_metrics=candidate_perf,
                current_metrics=current_perf,
            )
            raise ConflictError(
                f"Candidate '{candidate.version}' is not better than active "
                f"'{active_version}' (candidate MAE={candidate_perf.get('mae_mm')}, "
                f"active MAE={current_perf.get('mae_mm')})."
            )

        previous_version = current.version if current else None
        if candidate.status != ModelStatus.VALIDATED:
            candidate.status = ModelStatus.VALIDATED
        await self.repo.set_status(candidate, ModelStatus.ACTIVE)
        if request.notes:
            candidate.notes = request.notes
        await self.session.commit()

        reloaded = False
        try:
            model_registry.set_active(candidate.version)
            reloaded = True
        except Exception as exc:
            logger.error(
                "model_reload_after_promotion_failed", version=candidate.version, error=str(exc)
            )

        logger.info(
            "model_promoted",
            version=candidate.version,
            previous_version=previous_version,
            policy=policy,
            reloaded=reloaded,
        )
        return ModelPromotionResponse(
            activated_version=candidate.version,
            previous_version=previous_version,
            reloaded=reloaded,
            policy=policy,
        )

    async def register_training_run(self, payload: dict) -> int:
        run = await self.repo.create_training_run(payload)
        await self.session.commit()
        return run.id

    async def mark_run_status(
        self, run_uid: str, status: TrainingStatus, error_message: str | None = None
    ) -> None:
        run = await self.repo.get_training_run(run_uid)
        if run is None:
            return
        run.status = status
        run.error_message = error_message
        if status in (TrainingStatus.SUCCEEDED, TrainingStatus.FAILED):
            run.finished_at = utcnow()
            if run.started_at:
                run.duration_seconds = (run.finished_at - run.started_at).total_seconds()
        await self.session.commit()


def _is_better(candidate: dict, current: dict) -> bool:
    """MAE is the promotion criterion; sample size guards against noise.

    A candidate needs at least as many scored forecasts as the incumbent and a
    strictly lower mean absolute error. Comparing on a different metric than the
    one used at selection time would make promotion non-reproducible.
    """
    candidate_mae = candidate.get("mae_mm")
    current_mae = current.get("mae_mm")
    if candidate_mae is None or current_mae is None:
        return True
    if candidate.get("sample_size", 0) < current.get("sample_size", 0):
        return False
    return candidate_mae < current_mae
