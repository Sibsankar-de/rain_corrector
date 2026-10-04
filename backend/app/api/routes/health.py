"""Liveness and readiness endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.ml.registry import model_registry
from app.schemas.common import ORMModel
from app.utils.time import utcnow

router = APIRouter()


class HealthResponse(ORMModel):
    status: str
    app: str
    environment: str
    version: str
    checked_at: datetime


class ReadinessResponse(HealthResponse):
    database: str
    model_loaded: bool
    model_version: str | None
    available_model_versions: list[str]


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        environment=settings.environment,
        version=settings.api_version,
        checked_at=utcnow(),
    )


@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def readiness(response: Response, db: AsyncSession = Depends(get_db)) -> ReadinessResponse:
    database_status = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        database_status = "unavailable"

    model_loaded = model_registry.active_version is not None
    if database_status != "ok" or not model_loaded:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ready" if database_status == "ok" and model_loaded else "degraded",
        app=settings.app_name,
        environment=settings.environment,
        version=settings.api_version,
        checked_at=utcnow(),
        database=database_status,
        model_loaded=model_loaded,
        model_version=model_registry.active_version,
        available_model_versions=model_registry.available_versions(),
    )
