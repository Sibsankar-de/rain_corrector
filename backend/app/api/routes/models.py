"""Model registry, training history and promotion endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import ModelStatus
from app.core.security import require_api_key
from app.ml.registry import model_registry
from app.schemas.common import PaginatedResponse, PaginationParams
from app.schemas.forecast import (
    ModelPromotionRequest,
    ModelPromotionResponse,
    ModelVersionDetail,
    ModelVersionRead,
    TrainingRunRead,
)
from app.services.model_service import PROMOTION_POLICIES, ModelService

router = APIRouter()


@router.get(
    "/versions",
    response_model=PaginatedResponse[ModelVersionRead],
    summary="List model versions",
)
async def list_versions(
    pagination: PaginationParams = Depends(),
    model_status: ModelStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[ModelVersionRead]:
    items, total = await ModelService(db).list_versions(
        status=model_status, offset=pagination.offset, limit=pagination.limit
    )
    return PaginatedResponse.build(items, total, pagination.page, pagination.page_size)


@router.get("/active", response_model=ModelVersionRead | None, summary="Active model version")
async def active_model(db: AsyncSession = Depends(get_db)) -> ModelVersionRead | None:
    return await ModelService(db).get_active()


@router.get("/policies", response_model=list[str], summary="Supported promotion policies")
async def promotion_policies() -> list[str]:
    return list(PROMOTION_POLICIES)


@router.get("/training-runs", response_model=list[TrainingRunRead], summary="Training run history")
async def training_runs(
    limit: int = Query(default=50, ge=1, le=200), db: AsyncSession = Depends(get_db)
) -> list[TrainingRunRead]:
    return await ModelService(db).list_training_runs(limit=limit)


@router.get(
    "/versions/{version}",
    response_model=ModelVersionDetail,
    summary="Model version detail",
)
async def get_version(version: str, db: AsyncSession = Depends(get_db)) -> ModelVersionDetail:
    return await ModelService(db).get_version(version)


@router.post(
    "/promote",
    response_model=ModelPromotionResponse,
    status_code=status.HTTP_200_OK,
    summary="Promote a model version to active",
    description=(
        "Swaps the in-process model registry to the requested version. With the "
        "`auto_promote_if_better` policy the request is rejected when the candidate "
        "does not beat the active model on verified MAE."
    ),
)
async def promote(
    payload: ModelPromotionRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_api_key),
) -> ModelPromotionResponse:
    return await ModelService(db).promote(payload)


@router.post("/reload", response_model=dict, summary="Reload the model serving process")
async def reload_active(db: AsyncSession = Depends(get_db)) -> dict:
    version = await ModelService(db).serve_active_model()
    return {"loaded_version": version, "available": model_registry.available_versions()}
