"""Dataset loading for CSV, JSONL and the PostgreSQL database."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REQUIRED_OBSERVATION_COLUMNS = ("district_id", "observed_at", "rainfall_mm")
REQUIRED_DISTRICT_COLUMNS = ("id", "code", "name", "centroid_lat", "centroid_lon")


class DatasetError(RuntimeError):
    """Raised when a dataset cannot be loaded at all."""


def load_observations(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise DatasetError(f"Observation file not found: {path}")
    if path.suffix.lower() in (".csv", ".txt"):
        frame = pd.read_csv(path)
    elif path.suffix.lower() in (".jsonl", ".ndjson"):
        frame = pd.read_json(path, lines=True)
    elif path.suffix.lower() == ".parquet":
        frame = pd.read_parquet(path)
    else:
        raise DatasetError(f"Unsupported observation file type: {path.suffix}")

    missing = [c for c in REQUIRED_OBSERVATION_COLUMNS if c not in frame.columns]
    if missing:
        raise DatasetError(f"Observation file is missing columns: {missing}")
    return frame


def load_districts(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise DatasetError(f"District file not found: {path}")
    frame = pd.read_csv(path) if path.suffix.lower() == ".csv" else pd.read_json(path)
    missing = [c for c in REQUIRED_DISTRICT_COLUMNS if c not in frame.columns]
    if missing:
        raise DatasetError(f"District file is missing columns: {missing}")
    return frame


def load_from_database(connection_string: str, days: int = 730) -> pd.DataFrame:
    """Read daily district aggregates joined to district coordinates.

    Used by the retraining job so production verification data feeds the next
    training run without an intermediate export.
    """
    query = f"""
        SELECT
            a.district_id,
            d.centroid_lat AS lat,
            d.centroid_lon AS lon,
            a.observed_at,
            a.rainfall_mm
        FROM district_aggregates a
        JOIN districts d ON d.id = a.district_id
        WHERE a.window_minutes = 1440
          AND a.observed_at >= NOW() - INTERVAL '{int(days)} days'
        ORDER BY a.district_id, a.observed_at
    """
    return pd.read_sql_query(query, con=connection_string)


def attach_coordinates(observations: pd.DataFrame, districts: pd.DataFrame) -> pd.DataFrame:
    """Join coordinates, accepting either numeric district ids or codes.

    The synthetic demo dataset keys observations by district code while the
    database keys them by primary key, so both are supported and normalised to
    the numeric id used by the API.
    """
    frame = observations.copy()
    coords = districts[["id", "code", "centroid_lat", "centroid_lon"]].rename(
        columns={"centroid_lat": "lat", "centroid_lon": "lon"}
    )

    # The dataset may already carry coordinates; only join what is missing so a
    # double merge cannot produce lat_x / lat_y pairs.
    has_coordinates = "lat" in frame.columns and "lon" in frame.columns
    if has_coordinates and frame["lat"].notna().all():
        _require_known_districts(frame["district_id"], frame)
        return _normalise_district_id(frame)

    if has_coordinates:
        coords = coords.drop(columns=["lat", "lon"])

    observations_numeric = pd.to_numeric(frame["district_id"], errors="coerce")
    if observations_numeric.notna().all():
        frame["district_id"] = observations_numeric.astype("int64")
        frame = frame.merge(
            coords[["id", "lat", "lon"]].rename(columns={"id": "district_id"}),
            on="district_id",
            how="left",
        )
    else:
        frame["district_id"] = frame["district_id"].astype(str).str.strip()
        frame = frame.merge(
            coords[["code", "id", "lat", "lon"]].rename(columns={"code": "district_id"}),
            on="district_id",
            how="left",
        )
        # The code is replaced by the numeric primary key the API uses.
        frame["district_id"] = frame.pop("id")

    _require_known_districts(frame["district_id"], frame, lat_column="lat")
    return _normalise_district_id(frame.drop(columns=["id", "code"], errors="ignore"))


def _require_known_districts(
    district_id: pd.Series, frame: pd.DataFrame, lat_column: str = "district_id"
) -> None:
    """Fail on districts absent from the dimension table.

    Checked against the latitude column, which is null exactly when the join
    missed. On the early-return path the column holding the id is used instead,
    because no join happened.
    """
    source = frame[lat_column] if lat_column in frame.columns else district_id
    unknown = source.isna()
    if lat_column == "district_id" and not unknown.any():
        known = set(frame["district_id"].unique())
        unknown = ~frame["district_id"].isin(known)
    if not unknown.any():
        return
    labels = sorted(district_id[unknown].astype(str).unique())
    raise DatasetError(f"Observations reference districts without coordinates: {labels}")


def _normalise_district_id(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    numeric = pd.to_numeric(frame["district_id"], errors="coerce")
    if numeric.notna().all():
        frame["district_id"] = numeric.astype("int64")
    return frame


def daily_completeness(frame: pd.DataFrame) -> pd.DataFrame:
    """Report per-district day coverage so gaps are visible before training."""
    frame = frame.copy()
    frame["observed_date"] = (
        pd.to_datetime(frame["observed_at"]).dt.tz_localize(None).dt.normalize()
    )
    grouped = frame.groupby("district_id")["observed_date"]
    span = (grouped.max() - grouped.min()).dt.days + 1
    return pd.DataFrame(
        {
            "first_date": grouped.min(),
            "last_date": grouped.max(),
            "distinct_days": grouped.nunique(),
            "span_days": span,
            "missing_days": span - grouped.nunique(),
        }
    ).reset_index()


def summarise(frame: pd.DataFrame) -> dict[str, Any]:
    rainfall = frame["rainfall_mm"].astype(float)
    return {
        "rows": int(len(frame)),
        "districts": int(frame["district_id"].nunique()),
        "date_min": str(pd.to_datetime(frame["observed_at"]).min()),
        "date_max": str(pd.to_datetime(frame["observed_at"]).max()),
        "mean_rainfall_mm": round(float(rainfall.mean()), 4),
        "median_rainfall_mm": round(float(rainfall.median()), 4),
        "p95_rainfall_mm": round(float(np.percentile(rainfall, 95)), 4),
        "max_rainfall_mm": round(float(rainfall.max()), 4),
        "heavy_event_rate": round(float((rainfall >= 15.0).mean()), 4),
    }
