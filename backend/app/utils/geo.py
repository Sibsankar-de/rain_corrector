"""Geographic helpers.

Bbox queries are translated to a SQLAlchemy range expression against district
centroids. The dataset is small enough that a bounding-box filter is
appropriate; a PostGIS path is documented in ARCHITECTURE.md for scale.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, and_

from app.models.location import District


@dataclass(frozen=True)
class BoundingBox:
    min_lat: float | None = None
    min_lon: float | None = None
    max_lat: float | None = None
    max_lon: float | None = None

    def is_empty(self) -> bool:
        return all(v is None for v in (self.min_lat, self.min_lon, self.max_lat, self.max_lon))

    def apply(self, stmt: Select) -> Select:
        clauses = []
        if self.min_lat is not None:
            clauses.append(District.centroid_lat >= self.min_lat)
        if self.max_lat is not None:
            clauses.append(District.centroid_lat <= self.max_lat)
        if self.min_lon is not None:
            clauses.append(District.centroid_lon >= self.min_lon)
        if self.max_lon is not None:
            clauses.append(District.centroid_lon <= self.max_lon)
        return stmt.where(and_(*clauses)) if clauses else stmt

    def as_dict(self) -> dict[str, float | None]:
        return {
            "min_lat": self.min_lat,
            "min_lon": self.min_lon,
            "max_lat": self.max_lat,
            "max_lon": self.max_lon,
        }
