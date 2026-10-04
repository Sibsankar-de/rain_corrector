"""Observation ingestion and district aggregation persistence."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.forecast import Forecast
from app.models.location import District, Station
from app.models.observation import DistrictAggregate, StationObservation
from app.schemas.location import ObservationCreate
from app.utils.time import floor_to_step, utcnow


class ObservationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def existing_keys(
        self, keys: list[tuple[int, datetime, int]]
    ) -> set[tuple[int, datetime, int]]:
        if not keys:
            return set()
        station_ids = {k[0] for k in keys}
        observed_values = {k[1] for k in keys}
        result = await self.session.execute(
            select(
                StationObservation.station_id,
                StationObservation.observed_at,
                StationObservation.window_minutes,
            ).where(
                StationObservation.station_id.in_(station_ids),
                StationObservation.observed_at.in_(observed_values),
            )
        )
        return {(row[0], row[1], row[2]) for row in result.all()}

    async def bulk_insert(self, observations: list[ObservationCreate]) -> int:
        """Insert observations, skipping rows that already exist.

        Returns the number of rows the statement attempted; the caller has
        already excluded known duplicates, and PostgreSQL's ON CONFLICT DO
        NOTHING makes the write idempotent for rows that raced in meanwhile.
        """
        rows = [obs.model_dump() for obs in observations]
        if not rows:
            return 0
        # One asyncpg statement cannot exceed 32767 bind parameters, so a large
        # batch is split into chunks that stay well below the ceiling.
        chunk_size = max(30000 // len(rows[0]), 1)
        for start in range(0, len(rows), chunk_size):
            await self.session.execute(
                pg_insert(StationObservation)
                .values(rows[start : start + chunk_size])
                .on_conflict_do_nothing(
                    index_elements=[
                        StationObservation.station_id,
                        StationObservation.observed_at,
                        StationObservation.window_minutes,
                    ]
                )
            )
        await self.session.flush()
        return len(rows)

    async def list_observations(
        self,
        station_ids: list[int],
        start: datetime,
        end: datetime,
        limit: int = 5000,
    ) -> list[StationObservation]:
        stmt = select(StationObservation).where(
            StationObservation.station_id.in_(station_ids),
            StationObservation.observed_at >= start,
            StationObservation.observed_at <= end,
        )
        result = await self.session.execute(
            stmt.order_by(StationObservation.observed_at).limit(limit)
        )
        return list(result.scalars().all())

    async def get_aggregate(
        self, district_id: int, window_start: datetime, window_minutes: int
    ) -> DistrictAggregate | None:
        return await self.session.scalar(
            select(DistrictAggregate).where(
                DistrictAggregate.district_id == district_id,
                DistrictAggregate.observed_at == window_start,
                DistrictAggregate.window_minutes == window_minutes,
            )
        )

    async def find_aggregate_covering(
        self, district_id: int, target_time: datetime, window_minutes: int = 1440
    ) -> DistrictAggregate | None:
        """Aggregate whose accumulation window ends at or just after target_time.

        Verification must not use an aggregate that started after the forecast
        target, otherwise information from the future leaks into scoring.
        """
        start = target_time - timedelta(minutes=window_minutes)
        return await self.session.scalar(
            select(DistrictAggregate)
            .where(
                DistrictAggregate.district_id == district_id,
                DistrictAggregate.observed_at == start,
                DistrictAggregate.window_minutes == window_minutes,
            )
            .order_by(DistrictAggregate.computed_at.desc())
        )

    async def upsert_aggregate(
        self,
        district_id: int,
        observed_at: datetime,
        window_minutes: int,
        rainfall_mm: float,
        station_count: int,
        coverage_ratio: float,
        origin: str,
    ) -> DistrictAggregate:
        stmt = pg_insert(DistrictAggregate).values(
            district_id=district_id,
            observed_at=observed_at,
            window_minutes=window_minutes,
            rainfall_mm=rainfall_mm,
            station_count=station_count,
            coverage_ratio=coverage_ratio,
            origin=origin,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_agg_district_time_window",
            set_={
                "rainfall_mm": stmt.excluded.rainfall_mm,
                "station_count": stmt.excluded.station_count,
                "coverage_ratio": stmt.excluded.coverage_ratio,
                "origin": stmt.excluded.origin,
                "computed_at": utcnow(),
            },
        )
        await self.session.execute(stmt)
        await self.session.flush()
        return await self.get_aggregate(district_id, observed_at, window_minutes)  # type: ignore[return-value]

    async def compute_daily_aggregates(
        self, district_ids: list[int], lookback_days: int = 10
    ) -> int:
        """Recompute daily district aggregates from station observations."""
        end = floor_to_step(utcnow().replace(minute=0, second=0, microsecond=0), 24)
        start = end - timedelta(days=lookback_days)
        stations = list(
            (
                await self.session.execute(
                    select(Station).where(
                        Station.district_id.in_(district_ids), Station.is_active.is_(True)
                    )
                )
            ).scalars()
        )
        by_district: dict[int, list[Station]] = {}
        for station in stations:
            by_district.setdefault(station.district_id, []).append(station)

        updated = 0
        for district_id, district_stations in by_district.items():
            station_ids = [s.id for s in district_stations]
            obs = await self.list_observations(station_ids, start, end)
            by_window: dict[datetime, list[float]] = {}
            for row in obs:
                window_key = floor_to_step(
                    row.observed_at - timedelta(minutes=row.window_minutes), 24
                )
                by_window.setdefault(window_key, []).append(row.rainfall_mm)

            for window_key, values in by_window.items():
                rainfall = sum(values)
                coverage = len(values) / max(len(district_stations) * 2, 1)
                await self.upsert_aggregate(
                    district_id=district_id,
                    observed_at=window_key,
                    window_minutes=1440,
                    rainfall_mm=round(rainfall, 4),
                    station_count=len(values),
                    coverage_ratio=round(min(coverage, 1.0), 4),
                    origin="observed",
                )
                updated += 1
        return updated

    async def list_daily_aggregates(
        self,
        district_id: int,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 365,
    ) -> list[DistrictAggregate]:
        stmt = select(DistrictAggregate).where(DistrictAggregate.district_id == district_id)
        if start:
            stmt = stmt.where(DistrictAggregate.observed_at >= start)
        if end:
            stmt = stmt.where(DistrictAggregate.observed_at <= end)
        result = await self.session.execute(
            stmt.order_by(DistrictAggregate.observed_at).limit(limit)
        )
        return list(result.scalars().all())

    async def daily_history(
        self, district_ids: list[int], end: datetime, days: int = 30
    ) -> list[DistrictAggregate]:
        """Daily aggregates strictly before `end`, most recent `days` days.

        The predictor needs history it can attribute to observations that were
        already available at the issue time, so the window is exclusive of `end`.
        """
        start = end - timedelta(days=days)
        result = await self.session.execute(
            select(DistrictAggregate)
            .where(
                DistrictAggregate.district_id.in_(district_ids),
                DistrictAggregate.window_minutes == 1440,
                DistrictAggregate.observed_at >= start,
                DistrictAggregate.observed_at < end,
            )
            .order_by(DistrictAggregate.district_id, DistrictAggregate.observed_at)
        )
        return list(result.scalars().all())

    async def district_daily_history(
        self, district_ids: list[int], end: datetime, days: int = 30
    ) -> list[tuple[int, datetime, float]]:
        """(district_id, observed_at, rainfall_mm) strictly before `end`.

        The predictor needs history attributable to observations available at
        the issue time, so the window is exclusive of `end`.
        """
        result = await self.session.execute(
            select(
                DistrictAggregate.district_id,
                DistrictAggregate.observed_at,
                DistrictAggregate.rainfall_mm,
            )
            .where(
                DistrictAggregate.district_id.in_(district_ids),
                DistrictAggregate.window_minutes == 1440,
                DistrictAggregate.observed_at >= end - timedelta(days=days),
                DistrictAggregate.observed_at < end,
            )
            .order_by(DistrictAggregate.district_id, DistrictAggregate.observed_at)
        )
        return [(row[0], row[1], row[2]) for row in result.all()]

    async def forecasts_for_run(self, run_id: int) -> list[Forecast]:
        result = await self.session.execute(select(Forecast).where(Forecast.run_id == run_id))
        return list(result.scalars().all())

    async def district_ids_for_stations(self, station_ids: set[int]) -> list[int]:
        if not station_ids:
            return []
        result = await self.session.execute(
            select(Station.district_id).where(Station.id.in_(station_ids)).distinct()
        )
        return list(result.scalars().all())

    async def district_station_map(self) -> dict[int, list[Station]]:
        result = await self.session.execute(
            select(Station)
            .join(District, District.id == Station.district_id)
            .where(Station.is_active.is_(True))
        )
        mapping: dict[int, list[Station]] = {}
        for station in result.scalars():
            mapping.setdefault(station.district_id, []).append(station)
        return mapping
