"""Location endpoints: regions, districts and stations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.location_repository import LocationRepository
from app.schemas.common import PaginatedResponse, PaginationParams
from app.schemas.location import (
    DistrictDetail,
    DistrictSummary,
    RegionRead,
    StationCreate,
    StationRead,
)
from app.services.location_service import LocationService
from app.utils.geo import BoundingBox

router = APIRouter()


@router.get("/regions", response_model=list[RegionRead], summary="List regions")
async def list_regions(db: AsyncSession = Depends(get_db)) -> list[RegionRead]:
    regions = await LocationRepository(db).list_regions()
    return [RegionRead.model_validate(r) for r in regions]


@router.get(
    "/districts", response_model=PaginatedResponse[DistrictSummary], summary="List districts"
)
async def list_districts(
    pagination: PaginationParams = Depends(),
    region_id: int | None = Query(default=None, description="Filter by region id"),
    search: str | None = Query(default=None, min_length=2, max_length=64),
    min_lat: float | None = Query(default=None, ge=-90, le=90),
    min_lon: float | None = Query(default=None, ge=-180, le=180),
    max_lat: float | None = Query(default=None, ge=-90, le=90),
    max_lon: float | None = Query(default=None, ge=-180, le=180),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[DistrictSummary]:
    service = LocationService(db)
    bbox = BoundingBox(min_lat, min_lon, max_lat, max_lon)
    items, total = await service.list_districts(
        bbox=bbox,
        region_id=region_id,
        search=search,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return PaginatedResponse.build(items, total, pagination.page, pagination.page_size)


@router.get("/districts/{district_id}", response_model=DistrictDetail, summary="District detail")
async def get_district(district_id: int, db: AsyncSession = Depends(get_db)) -> DistrictDetail:
    return await LocationService(db).get_district(district_id)


@router.get("/stations", response_model=list[StationRead], summary="List stations")
async def list_stations(
    district_id: int | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
) -> list[StationRead]:
    stations = await LocationService(db).list_stations(district_id=district_id, limit=limit)
    return [StationRead.model_validate(s) for s in stations]


@router.post(
    "/stations",
    response_model=StationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a station",
)
async def create_station(payload: StationCreate, db: AsyncSession = Depends(get_db)) -> StationRead:
    station = await LocationService(db).create_station(payload)
    return StationRead.model_validate(station)
