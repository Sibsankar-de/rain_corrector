"""ORM model registry.

Importing this package registers every mapped class on `Base.metadata`, which
is what Alembic autogenerate and `create_all` rely on.
"""

from app.models.alert import Alert
from app.models.forecast import Forecast, ForecastRun, ForecastValue
from app.models.location import District, Region, Station
from app.models.model_version import ModelVersion, TrainingRun
from app.models.observation import DistrictAggregate, StationObservation
from app.models.user import APIKey, User
from app.models.verification import VerificationBatch, VerificationResult

__all__ = [
    "APIKey",
    "Alert",
    "District",
    "DistrictAggregate",
    "Forecast",
    "ForecastRun",
    "ForecastValue",
    "ModelVersion",
    "Region",
    "Station",
    "StationObservation",
    "TrainingRun",
    "User",
    "VerificationBatch",
    "VerificationResult",
]
