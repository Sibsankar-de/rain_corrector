"""FastAPI application factory and lifespan wiring."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging_config import configure_logging, get_logger
from app.utils.serialization import jsonable
from app.utils.time import utcnow

configure_logging(settings)
logger = get_logger("app")

DESCRIPTION = """
Rain Corrector API.

The platform forecasts district-level daily rainfall, persists each issuance for
later verification, and scores matured forecasts against observations.

**Conventions**

* All endpoints are versioned under `/api/{api_version}`.
* Timestamps are ISO 8601 in UTC.
* Collection endpoints use `page` and `page_size` and return a `meta` block.
* Errors return `{"error": {"code", "message", "details"}, "request_id", "timestamp"}`.
"""

TAGS_METADATA = [
    {"name": "health", "description": "Liveness and readiness probes."},
    {"name": "locations", "description": "Regions, districts and rain gauge stations."},
    {"name": "observations", "description": "Station observation ingestion and aggregates."},
    {"name": "forecasts", "description": "Forecast query, issuance and per-lead-time detail."},
    {"name": "verification", "description": "Forecast versus observation scoring."},
    {"name": "models", "description": "Model registry, training history and promotion."},
    {"name": "alerts", "description": "Heavy rainfall alerts."},
    {"name": "dashboard", "description": "Aggregated dashboard payload."},
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Warm the model registry on startup so the first request is not slow.

    A failure here is logged and the app still starts: `/health/ready` reports
    the degradation, which lets orchestration decide, rather than the process
    crash-looping on a missing artifact.
    """
    logger.info(
        "application_starting",
        environment=settings.environment,
        api_version=settings.api_version,
        model_artifact_path=str(settings.model_artifact_path),
    )
    if settings.model_load_on_startup:
        await _warm_model()
    yield
    logger.info("application_stopping")


async def _warm_model() -> None:
    from app.core.database import async_session_factory
    from app.ml.registry import model_registry
    from app.services.model_service import ModelService

    try:
        async with async_session_factory() as session:
            version = await ModelService(session).serve_active_model()
            if version:
                logger.info("model_ready", version=version)
            else:
                logger.warning(
                    "model_not_loaded",
                    available_versions=model_registry.available_versions(),
                    hint="Train a model (scripts/run_training.py) or promote an existing version.",
                )
    except Exception as exc:
        logger.error("model_warmup_failed", error=str(exc))


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version=os_version(),
        openapi_tags=TAGS_METADATA,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Process-Time"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        structlog.contextvars.bind_contextvars(request_id=request_id, path=request.url.path)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{(time.perf_counter() - started) * 1000:.2f}ms"
        return response

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.warning("app_error", code=exc.code, status=exc.status_code, detail=exc.message)
        return _error_response(
            exc.status_code,
            exc.code,
            exc.message,
            exc.details,
            getattr(request.state, "request_id", None),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {"field": ".".join(str(p) for p in err["loc"][1:]) or "body", "message": err["msg"]}
            for err in exc.errors()
        ]
        logger.info("request_validation_failed", count=len(details))
        return _error_response(
            422,
            "validation_error",
            "Request validation failed.",
            details,
            getattr(request.state, "request_id", None),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            405: "method_not_allowed",
        }.get(exc.status_code, "http_error")
        return _error_response(
            exc.status_code, code, str(exc.detail), None, getattr(request.state, "request_id", None)
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Detail stays in the log; clients only see a correlation id.
        logger.error("unhandled_exception", error=str(exc), exc_info=True)
        return _error_response(
            500,
            "internal_error",
            "An unexpected error occurred. Quote the request id when reporting this.",
            None,
            getattr(request.state, "request_id", None),
        )

    app.include_router(api_router, prefix=f"/api/{settings.api_version}")

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "docs": "/docs",
            "api": f"/api/{settings.api_version}",
        }

    return app


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: object = None,
    request_id: str | None = None,
) -> JSONResponse:
    payload = {
        "error": {"code": code, "message": message, "details": details},
        "request_id": request_id,
        "timestamp": utcnow(),
    }
    return JSONResponse(status_code=status_code, content=jsonable(payload))


def os_version() -> str:
    from app import __version__

    return __version__


app = create_app()
