"""Data access for regions, districts and stations."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.models.location import District, Region, Station
from app.schemas.location import StationCreate
from app.utils.geo import BoundingBox


class LocationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_regions(self) -> list[Region]:
        result = await self.session.execute(select(Region).order_by(Region.name))
        return list(result.scalars().all())

    async def list_districts(
        self,
        bbox: BoundingBox,
        region_id: int | None = None,
        search: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[District], int]:
        stmt = select(District)
        stmt = bbox.apply(stmt)
        if region_id is not None:
            stmt = stmt.where(District.region_id == region_id)
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(District.name.ilike(pattern))

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = await self.session.scalar(count_stmt) or 0
        result = await self.session.execute(
            stmt.options(selectinload(District.region))
            .order_by(District.name)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def all_district_ids(self) -> list[int]:
        result = await self.session.execute(select(District.id).order_by(District.id))
        return list(result.scalars().all())

    async def get_district(self, district_id: int) -> District:
        district = await self.session.scalar(
            select(District)
            .where(District.id == district_id)
            .options(selectinload(District.region))
        )
        if district is None:
            raise NotFoundError(f"District {district_id} does not exist.")
        return district

    async def get_districts(self, district_ids: list[int]) -> list[District]:
        if not district_ids:
            return []
        result = await self.session.execute(select(District).where(District.id.in_(district_ids)))
        return list(result.scalars().all())

    async def get_district_by_code(self, code: str) -> District | None:
        return await self.session.scalar(select(District).where(District.code == code))

    async def station_count_for_district(self, district_id: int) -> int:
        return (
            await self.session.scalar(
                select(func.count()).select_from(Station).where(Station.district_id == district_id)
            )
            or 0
        )

    async def list_stations(
        self, district_id: int | None = None, active_only: bool = True, limit: int = 500
    ) -> list[Station]:
        stmt = select(Station).options(selectinload(Station.district))
        if district_id is not None:
            stmt = stmt.where(Station.district_id == district_id)
        if active_only:
            stmt = stmt.where(Station.is_active.is_(True))
        result = await self.session.execute(stmt.order_by(Station.code).limit(limit))
        return list(result.scalars().all())

    async def create_station(self, payload: StationCreate) -> Station:
        await self.get_district(payload.district_id)
        station = Station(**payload.model_dump())
        self.session.add(station)
        await self.session.commit()
        await self.session.refresh(station)
        return station

    async def station_ids_in_district(self, district_id: int) -> list[int]:
        result = await self.session.execute(
            select(Station.id).where(Station.district_id == district_id)
        )
        return list(result.scalars().all())

    async def upsert_station(
        self,
        code: str,
        name: str,
        district_id: int,
        latitude: float,
        longitude: float,
        elevation_m: float | None = None,
        installed_at=None,
    ) -> Station:
        station = await self.session.scalar(select(Station).where(Station.code == code))
        if station is None:
            station = Station(
                code=code,
                name=name,
                district_id=district_id,
                latitude=latitude,
                longitude=longitude,
                elevation_m=elevation_m,
                installed_at=installed_at,
            )
            self.session.add(station)
        else:
            station.name = name
            station.district_id = district_id
            station.latitude = latitude
            station.longitude = longitude
            station.elevation_m = elevation_m
        await self.session.flush()
        return station
