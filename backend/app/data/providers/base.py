"""External data provider interface.

The application never imports a vendor SDK outside this package. Routes and
services depend on `ObservationProvider`, so swapping or adding a source is a
change confined here plus one entry in `PROVIDERS`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import ProviderError
from app.core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ProviderObservation:
    """Provider-neutral observation record.

    `observed_at` is the start of the accumulation window; the window length is
    carried explicitly so a provider with different conventions needs no
    reshaping downstream.
    """

    station_code: str
    observed_at: datetime
    window_minutes: int
    rainfall_mm: float
    temperature_c: float | None = None
    relative_humidity: float | None = None
    wind_speed_kmph: float | None = None
    pressure_hpa: float | None = None
    source: str = "external"


class ObservationProvider(ABC):
    """Contract every external data source implements."""

    name: str = "abstract"

    @abstractmethod
    async def fetch(
        self, station_code: str, start: datetime, end: datetime
    ) -> list[ProviderObservation]:
        """Return observations in `[start, end]`.

        Implementations must raise `ProviderError` on failure rather than
        returning an empty list, so a broken source is distinguishable from a
        period with no rain.
        """

    # Not abstract: most providers hold no resources, and forcing every
    # implementation to define a no-op makes the interface noisier, not safer.
    async def close(self) -> None:  # noqa: B027
        """Release any held connections. Safe to call more than once."""


class LocalCsvProvider(ObservationProvider):
    """Default provider: reads the local dataset, performs no network calls.

    Keeps the deployment independent of any external service, which is why it is
    the default.
    """

    name = "local_csv"

    async def fetch(
        self, station_code: str, start: datetime, end: datetime
    ) -> list[ProviderObservation]:
        from pathlib import Path

        import pandas as pd

        path = Path(settings.ml_training_data_path) / "observations.csv"
        if not path.exists():
            raise ProviderError(f"Local dataset not found at {path}.")

        frame = pd.read_csv(path)
        if "district_id" not in frame.columns or "observed_at" not in frame.columns:
            raise ProviderError(f"{path} does not match the expected observation schema.")

        timestamps = pd.to_datetime(frame["observed_at"], utc=True)
        selected = frame[(timestamps >= start) & (timestamps <= end)]
        return [
            ProviderObservation(
                station_code=str(row["district_id"]),
                observed_at=row["observed_at"].to_pydatetime(),
                window_minutes=1440,
                rainfall_mm=float(row["rainfall_mm"]),
                source="local_csv",
            )
            for _, row in selected.iterrows()
        ]


class OpenMeteoProvider(ObservationProvider):
    """Archive and forecast API from Open-Meteo (free, no key required).

    Documentation: https://open-meteo.com/en/docs. Respect the provider's terms
    and keep request volume low; this provider is meant for a scheduled job, not
    a request path.
    """

    name = "open_meteo"

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.base_url = base_url or settings.open_meteo_base_url
        self.timeout_seconds = timeout_seconds or settings.open_meteo_timeout_seconds

    async def fetch(
        self, station_code: str, start: datetime, end: datetime
    ) -> list[ProviderObservation]:
        if not settings.enable_external_ingestion:
            raise ProviderError(
                "External ingestion is disabled. Set ENABLE_EXTERNAL_INGESTION=true to use it."
            )

        params: dict[str, Any] = {
            "latitude": settings.default_ingest_latitude,
            "longitude": settings.default_ingest_longitude,
            "start_date": start.date().isoformat(),
            "end_date": end.date().isoformat(),
            "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min",
            "timezone": "UTC",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "external_provider_http_error",
                provider=self.name,
                status=exc.response.status_code,
            )
            raise ProviderError(f"{self.name} returned HTTP {exc.response.status_code}.") from exc
        except httpx.HTTPError as exc:
            logger.error("external_provider_unreachable", provider=self.name, error=str(exc))
            raise ProviderError(f"Could not reach {self.name}: {exc}") from exc

        return self._parse(payload, station_code)

    def _parse(self, payload: dict[str, Any], station_code: str) -> list[ProviderObservation]:
        daily = payload.get("daily") or {}
        dates = daily.get("time")
        if not dates:
            logger.warning("external_provider_empty_response", provider=self.name)
            return []

        precipitation = daily.get("precipitation_sum") or []
        t_max = daily.get("temperature_2m_max") or []
        t_min = daily.get("temperature_2m_min") or []

        observations: list[ProviderObservation] = []
        for index, day in enumerate(dates):
            rainfall = _value_at(precipitation, index)
            if rainfall is None:
                continue
            high = _value_at(t_max, index)
            low = _value_at(t_min, index)
            temperature = (high + low) / 2 if high is not None and low is not None else None
            observations.append(
                ProviderObservation(
                    station_code=station_code,
                    observed_at=datetime.fromisoformat(day).replace(tzinfo=None),
                    window_minutes=1440,
                    rainfall_mm=float(rainfall),
                    temperature_c=temperature,
                    source=self.name,
                )
            )
        return observations


def _value_at(values: list[Any], index: int) -> float | None:
    if index >= len(values):
        return None
    value = values[index]
    return None if value is None else float(value)


PROVIDERS: dict[str, type[ObservationProvider]] = {
    LocalCsvProvider.name: LocalCsvProvider,
    OpenMeteoProvider.name: OpenMeteoProvider,
}


def get_provider(name: str | None = None) -> ObservationProvider:
    resolved = name or settings.data_provider
    factory = PROVIDERS.get(resolved)
    if factory is None:
        raise ProviderError(f"Unknown data provider '{resolved}'. Available: {sorted(PROVIDERS)}.")
    return factory()
