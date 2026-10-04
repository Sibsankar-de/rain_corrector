"""Data access layer.

Every SQL statement in the application lives in this package. Services depend
on these classes; repositories never call back into services.
"""

from app.repositories.alert_repository import AlertRepository
from app.repositories.dashboard_repository import DashboardRepository
from app.repositories.forecast_repository import ForecastRepository
from app.repositories.location_repository import LocationRepository
from app.repositories.model_repository import ModelRepository
from app.repositories.observation_repository import ObservationRepository
from app.repositories.verification_repository import VerificationRepository

__all__ = [
    "AlertRepository",
    "DashboardRepository",
    "ForecastRepository",
    "LocationRepository",
    "ModelRepository",
    "ObservationRepository",
    "VerificationRepository",
]
