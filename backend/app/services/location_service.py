"""Location, observation ingestion and aggregation services."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.core.logging_config import get_logger
from app.repositories.location_repository import LocationRepository
from app.repositories.observation_repository import ObservationRepository
from app.schemas.location import (
    DistrictDetail,
    DistrictSummary,
    IngestionResult,
    ObservationBatchCreate,
    StationCreate,
)

logger = get_logger(__name__)


class LocationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = LocationRepository(session)

    async def list_districts(
        self,
        bbox,
        region_id: int | None,
        search: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[DistrictSummary], int]:
        districts, total = await self.repo.list_districts(
            bbox=bbox, region_id=region_id, search=search, offset=offset, limit=limit
        )
        return [DistrictSummary.model_validate(d) for d in districts], total

    async def get_district(self, district_id: int) -> DistrictDetail:
        district = await self.repo.get_district(district_id)
        detail = DistrictDetail.model_validate(district)
        detail.station_count = await self.repo.station_count_for_district(district_id)
        return detail

    async def list_stations(self, district_id: int | None, limit: int = 500):
        return await self.repo.list_stations(district_id=district_id, limit=limit)

    async def create_station(self, payload: StationCreate):
        station = await self.repo.create_station(payload)
        logger.info("station_created", station_code=station.code, district_id=payload.district_id)
        return station

    async def list_regions(self):
        return await self.repo.list_regions()


class ObservationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ObservationRepository(session)
        self.location_repo = LocationRepository(session)
        self.location_repo = LocationRepository(session)

    async def ingest(self, payload: ObservationBatchCreate) -> IngestionResult:
        keys = [
            (obs.station_id, obs.observed_at, obs.window_minutes) for obs in payload.observations
        ]
        existing = await self.repo.existing_keys(keys)
        fresh = [
            obs
            for obs in payload.observations
            if (obs.station_id, obs.observed_at, obs.window_minutes) not in existing
        ]

        if not fresh:
            return IngestionResult(accepted=0, duplicates=len(payload.observations))

        try:
            accepted = await self.repo.bulk_insert(fresh)
        except Exception as exc:
            await self.session.rollback()
            logger.error("observation_ingest_failed", error=str(exc))
            raise ValidationError(f"Observation batch could not be persisted: {exc}") from exc

        aggregates_updated = 0
        if payload.recompute_aggregates:
            # Aggregates are per district, so the station ids of the accepted
            # rows must be mapped to their districts before recomputing.
            district_ids = await self.repo.district_ids_for_stations(
                {obs.station_id for obs in fresh}
            )
            if district_ids:
                aggregates_updated = await self.repo.compute_daily_aggregates(sorted(district_ids))

        await self.session.commit()
        result = IngestionResult(
            accepted=accepted,
            duplicates=len(payload.observations) - len(fresh),
            aggregates_updated=aggregates_updated,
        )
        logger.info(
            "observations_ingested",
            accepted=result.accepted,
            duplicates=result.duplicates,
            aggregates_updated=result.aggregates_updated,
        )
        return result

    async def list_for_district(
        self, district_id: int, start: datetime, end: datetime, limit: int = 1000
    ):
        station_ids = await self.location_repo.station_ids_in_district(district_id)
        return await self.repo.list_observations(station_ids, start, end, limit=limit)

    async def recompute_aggregates(self, district_ids: list[int], lookback_days: int = 10) -> int:
        count = await self.repo.compute_daily_aggregates(district_ids, lookback_days=lookback_days)
        await self.session.commit()
        logger.info("aggregates_recomputed", districts=len(district_ids), windows=count)
        return count
