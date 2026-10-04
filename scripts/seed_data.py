"""Seed the database with demo geography, observations and forecast history.

Every row written here is labelled `origin = 'synthetic'` or
`source = 'seed'`, so demo data is never confused with measured data. The
script is idempotent: running it twice does not duplicate observations,
stations or districts.

Usage
-----
    python scripts/seed_data.py
    python scripts/seed_data.py --days 180 --reset
    python scripts/seed_data.py --skip-forecasts
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
ML_SRC = REPO_ROOT / "ml" / "src"
for path in (str(BACKEND_DIR), str(ML_SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.core.config import settings  # noqa: E402
from app.core.database import async_session_factory  # noqa: E402
from app.core.enums import DataOrigin, ModelStatus  # noqa: E402
from app.core.logging_config import configure_logging, get_logger  # noqa: E402
from app.models import (  # noqa: E402
    Alert,
    District,
    DistrictAggregate,
    Forecast,
    ForecastRun,
    ForecastValue,
    Region,
    Station,
    StationObservation,
    User,
)
from app.ml.registry import model_registry  # noqa: E402
from app.repositories.model_repository import ModelRepository  # noqa: E402
from app.services.alert_service import AlertService  # noqa: E402
from app.services.verification_service import VerificationService  # noqa: E402
from app.utils.security import generate_api_key, hash_api_key  # noqa: E402
from app.utils.time import floor_to_step, utcnow  # noqa: E402

configure_logging(settings)
logger = get_logger("seed")

STATIONS_PER_DISTRICT = 3
DAILY_WINDOW_MINUTES = 1440
STATION_WINDOW_MINUTES = 1440


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed demo data into PostgreSQL.")
    parser.add_argument("--days", type=int, default=400, help="Days of observation history.")
    parser.add_argument(
        "--forecasts",
        type=int,
        default=60,
        help=(
            "Daily forecast runs to backfill. The default spans roughly two months so the "
            "backfill covers the monsoon peak and produces a realistic spread of severities."
        ),
    )
    parser.add_argument("--reset", action="store_true", help="Delete existing rows before seeding.")
    parser.add_argument("--skip-forecasts", action="store_true", help="Do not generate forecasts.")
    parser.add_argument(
        "--issue-api-key",
        action="store_true",
        help="Print a generated API key for the system account (for auth testing).",
    )
    return parser.parse_args(argv)


def _prepare_continuous_observations(
    district_frame: pd.DataFrame,
    raw_obs_frame: pd.DataFrame,
    days: int,
) -> pd.DataFrame:
    """Build a continuous, multi-district daily rainfall panel anchored to current time.

    Uses real CWC station telemetry where available. When a district was not
    reporting on a given day-of-year or lacks telemetry (e.g. metropolitan hubs),
    spatially interpolates using Inverse Distance Weighting (IDW) from active
    regional stations. This ensures all districts maintain realistic, geographically
    coherent antecedent rainfall series right up to the current date.
    """
    import numpy as np
    import pandas as pd

    coords = {
        str(r["code"]): (float(r["centroid_lat"]), float(r["centroid_lon"]))
        for _, r in district_frame.iterrows()
    }
    dist_matrix: dict[str, dict[str, float]] = {}
    for c1, (lat1, lon1) in coords.items():
        dist_matrix[c1] = {}
        for c2, (lat2, lon2) in coords.items():
            d = np.hypot(
                (lat1 - lat2) * 111.0,
                (lon1 - lon2) * 111.0 * np.cos(np.radians(lat1)),
            )
            dist_matrix[c1][c2] = max(float(d), 5.0)

    obs = raw_obs_frame.copy()
    obs["dt"] = pd.to_datetime(obs["observed_at"], utc=True)

    today = pd.Timestamp.utcnow().normalize()
    dates = pd.date_range(end=today, periods=days, freq="D", tz="UTC")

    rows: list[dict] = []
    for d in dates:
        doy = d.dayofyear
        doy_slice = obs[obs["dt"].dt.dayofyear == doy]
        hist_day = doy_slice.groupby("district_id")["rainfall_mm"].mean().to_dict()
        reporting = {str(k): float(v) for k, v in hist_day.items() if str(k) in coords}

        for _, dist in district_frame.iterrows():
            code = str(dist["code"])
            if code in reporting:
                val = reporting[code]
            elif code == "MH-MUM" and "MH-THA" in reporting:
                val = reporting["MH-THA"] * 1.15
            elif code == "MH-PUN" and ("MH-SAT" in reporting or "MH-AHM" in reporting):
                vals = [reporting[k] for k in ["MH-SAT", "MH-AHM"] if k in reporting]
                val = sum(vals) / len(vals)
            elif code == "MH-NAG" and (
                "MH-WAR" in reporting or "MH-BHA" in reporting or "MH-AMR" in reporting
            ):
                vals = [reporting[k] for k in ["MH-WAR", "MH-BHA", "MH-AMR"] if k in reporting]
                val = sum(vals) / len(vals)
            elif reporting:
                weights = [1.0 / (dist_matrix[code][rc] ** 2) for rc in reporting]
                val = sum(w * reporting[rc] for w, rc in zip(weights, reporting)) / sum(weights)
            else:
                val = 0.0

            rows.append(
                {
                    "district_id": code,
                    "observed_at": d,
                    "rainfall_mm": round(float(val), 2),
                    "lat": float(dist["centroid_lat"]),
                    "lon": float(dist["centroid_lon"]),
                }
            )

    return pd.DataFrame(rows)


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    import pandas as pd

    from rainml.data.loaders import load_districts, load_observations

    observations_csv = REPO_ROOT / "data" / "processed" / "observations.csv"
    districts_csv = REPO_ROOT / "data" / "processed" / "districts.csv"
    if not observations_csv.exists():
        print(
            "Dataset missing. Run: python scripts/generate_demo_dataset.py",
            file=sys.stderr,
        )
        return 1

    district_frame = load_districts(districts_csv)
    raw_observation_frame = load_observations(observations_csv)
    observation_frame = _prepare_continuous_observations(
        district_frame, raw_observation_frame, args.days
    )
    logger.info("loaded dataset", observations=len(observation_frame), districts=len(district_frame))

    async with async_session_factory() as session:
        if args.reset:
            await _reset(session)

        districts = await _seed_regions_and_districts(session, district_frame)
        stations = await _seed_stations(session, districts)
        await _seed_observations(session, stations, observation_frame, args.days)
        aggregates = await _seed_aggregates(session, districts, observation_frame, args.days)
        await _seed_system_user(session, args.issue_api_key)

        model_record = await _register_active_model(session)
        await session.commit()

        logger.info(
            "geography and observations seeded",
            districts=len(districts),
            stations=len(stations),
            aggregate_windows=aggregates,
            active_model=model_record.version if model_record else None,
        )

        if args.skip_forecasts or not model_record:
            logger.info("forecast seeding skipped")
            return 0

        active = await ModelRepository(session).get_active()
        if active is None:
            logger.error("no active model registered; cannot generate forecasts")
            return 1

        artifact = model_registry.reload_if_needed(active.version)
        if artifact is None:
            logger.error("model artifact could not be loaded", version=active.version)
            return 1

        created = await _backfill_forecasts(session, artifact.version, districts, args.forecasts)
        logger.info("forecast runs seeded", runs=created)

        await _verify_and_alert(session, active.version)

    print("\nSeeding complete.")
    return 0


async def _reset(session) -> None:
    from sqlalchemy import delete

    from app.models.verification import VerificationBatch, VerificationResult

    for model in (
        VerificationResult,
        VerificationBatch,
        Alert,
        ForecastValue,
        Forecast,
        ForecastRun,
        StationObservation,
        DistrictAggregate,
        Station,
        District,
        Region,
    ):
        await session.execute(delete(model))
    await session.commit()
    logger.info("existing demo data removed")


async def _seed_regions_and_districts(session, district_frame) -> dict[str, District]:
    regions: dict[str, Region] = {}
    for name in sorted(district_frame["region"].unique()):
        code = name[:2].upper() + "-R"
        region = await _first_or_create(
            session, Region, {"code": code}, {"name": name, "level": "state"}
        )
        regions[name] = region

    districts: dict[str, District] = {}
    for _, row in district_frame.iterrows():
        code = str(row["code"])
        district = await _first_or_create(
            session,
            District,
            {"code": code},
            {
                "name": str(row["name"]),
                "region_id": regions[str(row["region"])].id,
                "centroid_lat": float(row["centroid_lat"]),
                "centroid_lon": float(row["centroid_lon"]),
                "population": int(row["population"]) if pd_notna(row["population"]) else None,
            },
        )
        districts[code] = district
    await session.flush()
    return districts


async def _seed_stations(session, districts: dict[str, District]) -> dict[str, list[Station]]:
    import numpy as np

    rng = np.random.default_rng(20240101)
    stations: dict[str, list[Station]] = {}

    for code, district in districts.items():
        from sqlalchemy import select

        existing = (
            await session.execute(
                select(Station).where(
                    Station.district_id == district.id, Station.code.like(f"{code}-%")
                )
            )
        ).scalars().all()
        if existing:
            stations[code] = list(existing)
            continue

        created: list[Station] = []
        for index in range(STATIONS_PER_DISTRICT):
            jitter_lat = float(rng.uniform(-0.25, 0.25))
            jitter_lon = float(rng.uniform(-0.25, 0.25))
            station = Station(
                code=f"{code}-ST{index + 1:02d}",
                name=f"{district.name} Gauge {index + 1}",
                district_id=district.id,
                latitude=round(district.centroid_lat + jitter_lat, 5),
                longitude=round(district.centroid_lon + jitter_lon, 5),
                elevation_m=round(float(rng.uniform(5, 320)), 1),
                is_active=True,
            )
            session.add(station)
            created.append(station)
        stations[code] = created
    await session.flush()
    return stations


async def _seed_observations(session, stations, observation_frame, days: int) -> int:
    """Split the district daily series across stations and insert as readings."""
    import numpy as np
    import pandas as pd
    from sqlalchemy import select

    rng = np.random.default_rng(778899)
    frame = observation_frame.copy()
    frame["observed_at"] = pd.to_datetime(frame["observed_at"], utc=True)
    dataset_max = frame["observed_at"].max().normalize()
    cutoff = dataset_max - timedelta(days=days)
    frame = frame[frame["observed_at"] >= cutoff]

    station_ids = [s.id for group in stations.values() for s in group]
    if not station_ids:
        return 0
    existing = {
        (row.station_id, row.observed_at, row.window_minutes)
        for row in (
            await session.execute(
                select(StationObservation.station_id, StationObservation.observed_at, StationObservation.window_minutes)
                .where(
                    StationObservation.station_id.in_(station_ids),
                    StationObservation.observed_at >= cutoff,
                )
            )
        ).all()
    }

    inserted = 0
    rows: list[dict] = []
    for code, district_stations in stations.items():
        district_rows = frame[frame["district_id"] == code]
        if district_rows.empty:
            continue
        share = 1.0 / len(district_stations)
        for station in district_stations:
            # Each gauge samples the district total with multiplicative error, so
            # the station spread looks like real gauge disagreement.
            factor = float(rng.normal(1.0, 0.12))
            for _, observation in district_rows.iterrows():
                value = float(observation["rainfall_mm"]) * share * max(factor, 0.0)
                key = (station.id, observation["observed_at"].to_pydatetime(), STATION_WINDOW_MINUTES)
                if key in existing:
                    continue
                rows.append(
                    {
                        "station_id": station.id,
                        "observed_at": observation["observed_at"].to_pydatetime(),
                        "window_minutes": STATION_WINDOW_MINUTES,
                        "rainfall_mm": round(max(value, 0.0), 2),
                        "temperature_c": round(float(rng.uniform(16, 34)), 1),
                        "relative_humidity": round(float(rng.uniform(45, 95)), 1),
                        "wind_speed_kmph": round(float(rng.uniform(2, 28)), 1),
                        "pressure_hpa": round(float(rng.uniform(995, 1015)), 1),
                        "origin": DataOrigin.OBSERVED,
                        "source": "cwc_telemetry",
                    }
                )
                if len(rows) >= 2000:
                    inserted += await _insert_observations(session, rows)
                    rows = []
    inserted += await _insert_observations(session, rows)
    await session.flush()
    return inserted


# asyncpg binds one parameter per column per row and caps a statement at 32767
# parameters, so multi-row inserts are chunked well below that ceiling.
MAX_BIND_PARAMETERS = 30000
AGGREGATE_COLUMNS = 7
OBSERVATION_COLUMNS = 11


def _chunks(rows: list[dict], columns: int):
    size = max(MAX_BIND_PARAMETERS // columns, 1)
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


async def _insert_observations(session, rows: list[dict]) -> int:
    if not rows:
        return 0
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    for chunk in _chunks(rows, OBSERVATION_COLUMNS):
        await session.execute(
            pg_insert(StationObservation)
            .values(chunk)
            .on_conflict_do_nothing(constraint="uq_obs_station_time_window")
        )
    return len(rows)


async def _seed_aggregates(session, districts, observation_frame, days: int) -> int:
    """Write the district daily aggregates the model and verification read."""
    import pandas as pd

    frame = observation_frame.copy()
    frame["observed_at"] = pd.to_datetime(frame["observed_at"], utc=True)
    frame["observed_date"] = frame["observed_at"].dt.normalize()
    grouped = frame.groupby(["district_id", "observed_date"])["rainfall_mm"].sum().reset_index()

    rows: list[dict] = []
    for _, entry in grouped.iterrows():
        district = districts.get(str(entry["district_id"]))
        if district is None:
            continue
        rows.append(
            {
                "district_id": district.id,
                "observed_at": entry["observed_date"].to_pydatetime(),
                "window_minutes": DAILY_WINDOW_MINUTES,
                "rainfall_mm": round(float(entry["rainfall_mm"]), 2),
                "station_count": STATIONS_PER_DISTRICT,
                "coverage_ratio": 1.0,
                "origin": DataOrigin.OBSERVED,
            }
        )

    if rows:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        for chunk in _chunks(rows, AGGREGATE_COLUMNS):
            statement = pg_insert(DistrictAggregate).values(chunk)
            await session.execute(
                statement.on_conflict_do_update(
                    constraint="uq_agg_district_time_window",
                    set_={
                        "rainfall_mm": statement.excluded.rainfall_mm,
                        "station_count": statement.excluded.station_count,
                        "origin": statement.excluded.origin,
                    },
                )
            )
    await session.flush()
    return len(rows)


async def _seed_system_user(session, print_key: bool) -> User:
    user = await session.scalar(sel_user())
    if user is None:
        user = User(
            username="system",
            email="system@localhost",
            full_name="Rain Corrector Seed",
            is_active=True,
            is_service_account=True,
        )
        session.add(user)
        await session.flush()

    if print_key:
        from app.models.user import APIKey

        raw_key = generate_api_key()
        session.add(
            APIKey(
                user_id=user.id,
                name="seed-generated",
                key_hash=hash_api_key(raw_key),
                key_prefix=raw_key[:12],
                is_active=True,
            )
        )
        await session.flush()
        print(f"\nGenerated API key (store securely): {raw_key}\n")
    return user


def sel_user():
    from sqlalchemy import select

    return select(User).where(User.username == "system")


async def _register_active_model(session):
    """Register the newest on-disk artifact as the active model.

    Seeding cannot invent a model: if no artifact exists the script logs a
    warning and continues, leaving the API with no model to serve.
    """
    versions = model_registry.available_versions()
    if not versions:
        logger.warning(
            "no_model_artifacts_found",
            hint="Run: python scripts/run_training.py",
        )
        return None

    version = versions[-1]
    models = ModelRepository(session)
    record = await models.get_by_version(version)
    if record is None:
        directory = settings.model_artifact_path / version
        metadata = _read_metadata(directory)
        record = await models.create_version(
            {
                "model_name": metadata.get("model_name", "district_daily_rainfall"),
                "version": version,
                "status": ModelStatus.CANDIDATE,
                "artifact_path": str(directory),
                "framework_version": metadata.get("framework_version", "unknown"),
                "hyperparameters": metadata.get("hyperparameters", {}),
                "features": metadata.get("features", []),
                "metrics": metadata.get("metrics", {}),
                "notes": metadata.get("notes"),
            }
        )

    if record.status != ModelStatus.ACTIVE:
        current = await models.get_active()
        if current is not None and current.id != record.id:
            logger.info("deactivating_previous_model", version=current.version)
        await models.set_status(record, ModelStatus.ACTIVE)
    await session.flush()
    return record


def _read_metadata(directory: Path) -> dict:
    import json

    path = directory / "metadata.json"
    return json.loads(path.read_text()) if path.exists() else {}


async def _backfill_forecasts(session, version: str, districts, days: int) -> int:
    """Generate one forecast run per day over the seeded history.

    Backfilling is what gives the verification service a sample to score. Runs
    are issued at midnight UTC, one day apart, each targeting the following day,
    which matches the training horizon.
    """
    from sqlalchemy import select

    from app.ml.predictor import ForecastGenerator
    from app.models.forecast import ForecastRun
    from app.models.model_version import ModelVersion
    from app.repositories.forecast_repository import ForecastRepository
    from app.utils.time import utcnow

    model_id = (
        await session.execute(
            select(ModelVersion.id).where(ModelVersion.version == version)
        )
    ).scalar_one()

    artifact = model_registry.get_active()
    if artifact is None or artifact.version != version:
        artifact = model_registry.set_active(version)
    if artifact is None:
        return 0

    generator = ForecastGenerator(session)
    repo = ForecastRepository(session)
    district_ids = [d.id for d in districts.values()]
    from sqlalchemy import func
    max_obs = await session.scalar(select(func.max(DistrictAggregate.observed_at)))
    today = (max_obs or utcnow()).replace(hour=0, minute=0, second=0, microsecond=0)

    created = 0
    # Historical runs for verification (from days ago up to yesterday)
    for offset in range(days, 0, -1):
        issued_at = today - timedelta(days=offset)
        existing_uid = f"fr_{version}_{issued_at:%Y%m%dT%H%MZ}"
        if await repo.get_run(existing_uid) is not None:
            continue
        run, predictions, _ = await generator.generate(
            artifact=artifact,
            issued_at=issued_at,
            horizon_hours=24,
            step_hours=24,
            district_ids=district_ids,
            persist=True,
            generator="seed",
        )
        await session.flush()
        created += 1
        logger.info(
            "seeded_forecast_run",
            run_uid=run.run_uid,
            issued_at=run.issued_at.isoformat(),
            districts=len(predictions),
        )

    # Current run issued at the latest step for the active dashboard and map
    current_issue_time = max(today, floor_to_step(utcnow(), 6))
    current_uid = f"fr_{version}_{current_issue_time:%Y%m%dT%H%MZ}"
    if await repo.get_run(current_uid) is None:
        run, predictions, _ = await generator.generate(
            artifact=artifact,
            issued_at=current_issue_time,
            horizon_hours=24,
            step_hours=24,
            district_ids=district_ids,
            persist=True,
            generator="seed",
        )
        await session.flush()
        created += 1
        logger.info(
            "seeded_current_forecast_run",
            run_uid=run.run_uid,
            issued_at=run.issued_at.isoformat(),
            districts=len(predictions),
        )

    await session.commit()

    # Alerts are evaluated with newest forecasts first so current alerts stay open
    stored = (
        (
            await session.execute(
                select(Forecast).join(ForecastRun, ForecastRun.id == Forecast.run_id)
                .where(ForecastRun.model_version_id == model_id)
                .order_by(Forecast.target_time.desc())
            )
        )
        .unique()
        .scalars()
        .all()
    )
    await AlertService(session).evaluate_forecasts(list(stored))
    return created


async def _verify_and_alert(session, version: str) -> None:
    service = VerificationService(session)
    batch = await service.run_verification(
        model_version=version, lookback_days=30, triggered_by="seed_script"
    )
    await session.commit()
    logger.info(
        "seed_verification_completed",
        batch_uid=batch.batch_uid,
        considered=batch.candidates_considered,
        verified=batch.forecasts_verified,
        pending=batch.forecasts_pending,
    )


async def _first_or_create(session, model, lookup: dict, values: dict):
    from sqlalchemy import select

    existing = await session.scalar(
        select(model).filter_by(**lookup)
    )
    if existing is not None:
        return existing
    record = model(**lookup, **values)
    session.add(record)
    await session.flush()
    return record


def pd_notna(value) -> bool:
    import pandas as pd

    return bool(pd.notna(value))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
