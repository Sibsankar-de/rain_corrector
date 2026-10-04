"""Forecast generation using the loaded model artifact."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import ForecastStatus
from app.core.exceptions import ModelUnavailableError, PredictionError
from app.core.logging_config import get_logger
from app.ml.base import ModelArtifact, PredictionOutput
from app.ml.features import DistrictHistory, build_features
from app.ml.registry import model_registry
from app.models.forecast import Forecast, ForecastRun, ForecastValue
from app.repositories.forecast_repository import ForecastRepository
from app.repositories.location_repository import LocationRepository
from app.repositories.model_repository import ModelRepository
from app.repositories.observation_repository import ObservationRepository
from app.services.severity import classify
from app.utils.time import floor_to_step, utcnow

logger = get_logger(__name__)

HISTORY_DAYS = 30


class ForecastGenerator:
    """Builds and persists forecast runs for a set of districts."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.location_repo = LocationRepository(session)
        self.forecast_repo = ForecastRepository(session)
        self.observation_repo = ObservationRepository(session)
        self.model_repo = ModelRepository(session)

    async def _district_histories(
        self, district_ids: list[int], issue_time: datetime
    ) -> list[DistrictHistory]:
        rows = await self.observation_repo.district_daily_history(
            district_ids, end=issue_time, days=HISTORY_DAYS
        )
        grouped: dict[int, dict[datetime, float]] = {
            district_id: {} for district_id in district_ids
        }
        for district_id, observed_at, rainfall in rows:
            grouped[district_id][observed_at] = rainfall

        districts = await self.location_repo.get_districts(district_ids)
        return [
            DistrictHistory(
                district_id=d.id,
                latitude=d.centroid_lat,
                longitude=d.centroid_lon,
                daily_rainfall=grouped.get(d.id, {}),
            )
            for d in districts
        ]

    async def generate(
        self,
        artifact: ModelArtifact | None = None,
        issued_at: datetime | None = None,
        horizon_hours: int | None = None,
        step_hours: int = 6,
        district_ids: list[int] | None = None,
        persist: bool = True,
        generator: str = "api",
    ) -> tuple[ForecastRun, list[PredictionOutput], int]:
        """Issue a forecast run.

        Returns the run, its predictions and how many forecasts were created. A
        run is identified by (model version, base time), so a repeated request
        for the same issuance returns the existing run with a count of zero
        instead of colliding on the unique run id. That makes a retried or
        duplicated scheduler tick safe.
        """
        artifact = artifact or model_registry.get_active()
        issue_time = floor_to_step(issued_at or utcnow(), step_hours)
        if issue_time > utcnow():
            raise ValueError("issued_at cannot be in the future")
        horizon = horizon_hours or settings.default_forecast_horizon_hours

        targets = district_ids or await self.location_repo.all_district_ids()
        if not targets:
            raise PredictionError("No districts available for forecasting.")

        histories = await self._district_histories(targets, issue_time)
        frame = build_features(histories, issue_time, horizon)
        frame.insert(0, "district_id", [h.district_id for h in histories])

        feature_frame = frame.drop(columns=["district_id"])
        try:
            point, lower, upper = artifact.predict_interval(feature_frame)
        except Exception as exc:  # surfaced as a 500 with a logged traceback
            logger.error(
                "prediction_failed", version=artifact.version, error=str(exc), exc_info=True
            )
            raise PredictionError(f"Model inference failed: {exc}") from exc

        step_starts = _step_starts(issue_time, horizon, step_hours)
        target_time = issue_time + timedelta(hours=horizon)
        run_uid = f"fr_{artifact.version}_{issue_time:%Y%m%dT%H%MZ}"

        predictions: list[PredictionOutput] = []
        for position, history in enumerate(histories):
            value = float(max(point[position], 0.0))
            lo = float(max(min(lower[position], value), 0.0))
            hi = float(max(upper[position], value))
            predictions.append(
                PredictionOutput(
                    district_id=history.district_id,
                    target_time=target_time,
                    lead_time_hours=float(horizon),
                    predicted_rainfall_mm=value,
                    lower_bound_mm=lo,
                    upper_bound_mm=hi,
                    predicted_probability=None,
                    severity=classify(value),
                    model_version=artifact.version,
                )
            )

        if not persist:
            return (
                _unsaved_run(run_uid, artifact, issue_time, horizon, step_hours, step_starts),
                predictions,
                len(predictions),
            )

        existing = await self.forecast_repo.get_run(run_uid)
        if existing is not None:
            logger.info("forecast_run_already_exists", run_uid=run_uid)
            return existing, [], 0

        model_record = await self.model_repo.get_by_version(artifact.version)
        if model_record is None:
            raise ModelUnavailableError(
                f"Model version '{artifact.version}' is not registered in the database. "
                "Run scripts/run_training.py or register it before generating forecasts."
            )

        run = ForecastRun(
            run_uid=run_uid,
            model_version_id=model_record.id,
            issued_at=issue_time,
            horizon_hours=horizon,
            step_hours=step_hours,
            valid_from=step_starts[0],
            valid_to=step_starts[-1] + timedelta(hours=step_hours),
            generator=generator,
            feature_snapshot_hash=_feature_hash(frame),
        )
        await self.forecast_repo.add_run(run)
        for prediction in predictions:
            forecast = Forecast(
                run_id=run.id,
                district_id=prediction.district_id,
                target_time=prediction.target_time,
                lead_time_hours=prediction.lead_time_hours,
                predicted_rainfall_mm=prediction.predicted_rainfall_mm,
                predicted_probability=prediction.predicted_probability,
                lower_bound_mm=prediction.lower_bound_mm,
                upper_bound_mm=prediction.upper_bound_mm,
                severity=prediction.severity,
                status=ForecastStatus.ISSUED,
                feature_inputs={"district_id": prediction.district_id},
            )
            await self.forecast_repo.add_forecasts([forecast])
            await self.forecast_repo.add_values(
                [
                    ForecastValue(
                        forecast_id=forecast.id,
                        step_index=index,
                        step_start=start,
                        step_end=start + timedelta(hours=step_hours),
                        lead_hours=(start - issue_time).total_seconds() / 3600 + step_hours,
                        predicted_rainfall_mm=round(_allocate(value, index, len(step_starts)), 4),
                        lower_bound_mm=round(_allocate(lo, index, len(step_starts)), 4),
                        upper_bound_mm=round(_allocate(hi, index, len(step_starts)), 4),
                    )
                    for index, start in enumerate(step_starts)
                ]
            )

        logger.info(
            "forecast_run_generated",
            run_uid=run_uid,
            model_version=artifact.version,
            issued_at=issue_time.isoformat(),
            horizon_hours=horizon,
            districts=len(predictions),
        )
        return run, predictions, len(predictions)

    async def generate_for_request(
        self,
        model_version: str | None = None,
        issued_at: datetime | None = None,
        horizon_hours: int | None = None,
        step_hours: int = 6,
        district_ids: list[int] | None = None,
    ) -> tuple[ForecastRun, list[PredictionOutput], int]:
        artifact = (
            model_registry.reload_if_needed(model_version) or model_registry.get_active()
            if model_version
            else model_registry.get_active()
        )
        return await self.generate(
            artifact=artifact,
            issued_at=issued_at,
            horizon_hours=horizon_hours,
            step_hours=step_hours,
            district_ids=district_ids,
        )


def _unsaved_run(
    run_uid: str,
    artifact: ModelArtifact,
    issue_time: datetime,
    horizon_hours: int,
    step_hours: int,
    step_starts: list[datetime],
) -> ForecastRun:
    """Transient run object so preview calls return the same shape without a write."""
    return ForecastRun(
        id=-1,
        run_uid=run_uid,
        model_version_id=-1,
        issued_at=issue_time,
        horizon_hours=horizon_hours,
        step_hours=step_hours,
        valid_from=step_starts[0],
        valid_to=step_starts[-1] + timedelta(hours=step_hours),
        generator="preview",
    )


def _step_starts(issue_time: datetime, horizon_hours: int, step_hours: int) -> list[datetime]:
    starts: list[datetime] = []
    elapsed = 0
    while elapsed < horizon_hours:
        starts.append(issue_time + timedelta(hours=elapsed))
        elapsed += step_hours
    return starts or [issue_time]


def _allocate(total_mm: float, index: int, count: int) -> float:
    """Split a horizon total evenly across steps.

    The served model predicts the horizon total; a per-step split is required by
    the schema so the UI can chart the horizon. Even allocation keeps the sum
    consistent with the headline value instead of inventing a distribution.
    """
    return total_mm / max(count, 1)


def _feature_hash(frame) -> str:
    import hashlib

    payload = frame.to_csv(index=False).encode()
    return hashlib.sha256(payload).hexdigest()[:32]
