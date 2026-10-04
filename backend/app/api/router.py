"""FastAPI router aggregation for the v1 API."""

from fastapi import APIRouter

from app.api.routes import (
    alerts,
    dashboard,
    forecasts,
    health,
    locations,
    models,
    observations,
    verification,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(locations.router, prefix="/locations", tags=["locations"])
api_router.include_router(observations.router, prefix="/observations", tags=["observations"])
api_router.include_router(forecasts.router, prefix="/forecasts", tags=["forecasts"])
api_router.include_router(verification.router, prefix="/verification", tags=["verification"])
api_router.include_router(models.router, prefix="/models", tags=["models"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
