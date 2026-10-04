"""External observation providers, selected by the DATA_PROVIDER setting."""

from app.data.providers.base import (
    LocalCsvProvider,
    ObservationProvider,
    OpenMeteoProvider,
    ProviderObservation,
    get_provider,
)

__all__ = [
    "LocalCsvProvider",
    "ObservationProvider",
    "OpenMeteoProvider",
    "ProviderObservation",
    "get_provider",
]
