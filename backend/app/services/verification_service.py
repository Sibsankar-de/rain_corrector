"""Verification workflow: score matured forecasts and summarise skill."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import ForecastStatus, VerificationStatus
from app.core.logging_config import get_logger
from app.models.verification import VerificationBatch
from app.repositories.forecast_repository import ForecastRepository
from app.repositories.observation_repository import ObservationRepository
from app.repositories.verification_repository import VerificationRepository
from app.schemas.forecast import VerificationMetricsSummary
from app.services import verification_metrics as vm
from app.utils.time import utcnow

logger = get_logger(__name__)

AGGREGATE_WINDOW_MINUTES = 1440


class VerificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.forecast_repo = ForecastRepository(session)
        self.observation_repo = ObservationRepository(session)
        self.verification_repo = VerificationRepository(session)

    async def run_verification(
        self,
        model_version: str | None = None,
        district_ids: list[int] | None = None,
        lookback_days: int = 14,
        force: bool = False,
        triggered_by: str = "scheduled_job",
        event_threshold_mm: float = vm.DEFAULT_EVENT_THRESHOLD_MM,
    ) -> VerificationBatch:
        batch_uid = f"vrf_{utcnow():%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}"
        batch = await self.verification_repo.add_batch(
            VerificationBatch(
                batch_uid=batch_uid,
                triggered_by=triggered_by,
                candidates_considered=0,
                forecasts_verified=0,
                forecasts_pending=0,
                status="running",
            )
        )

        candidates = await self.forecast_repo.eligible_for_verification(
            grace_period_hours=settings.verification_grace_period_hours,
            lookback_days=lookback_days,
            model_version=model_version,
            district_ids=district_ids,
        )
        batch.candidates_considered = len(candidates)

        verified_count = 0
        pending_count = 0
        for forecast in candidates:
            existing = await self.verification_repo.get_for_forecast(forecast.id)
            if (
                existing is not None
                and existing.status == VerificationStatus.VERIFIED
                and not force
            ):
                continue

            target_time = forecast.target_time
            aggregate = await self.observation_repo.find_aggregate_covering(
                district_id=forecast.district_id,
                target_time=target_time,
                window_minutes=AGGREGATE_WINDOW_MINUTES,
            )
            if aggregate is None:
                pending_count += 1
                await self.verification_repo.upsert(
                    forecast_id=forecast.id,
                    aggregate_id=None,
                    status=VerificationStatus.MISSING_OBSERVATION,
                    values={"forecast_rainfall_mm": forecast.predicted_rainfall_mm},
                    observed_at=None,
                    verified_at=None,
                )
                continue

            self._assert_no_leakage(forecast, aggregate)
            await self._score_forecast(forecast.id, aggregate, event_threshold_mm)
            verified_count += 1

        await self.session.flush()
        batch.forecasts_verified = verified_count
        batch.forecasts_pending = pending_count
        batch.status = "completed"
        batch.finished_at = utcnow()
        await self.session.flush()

        summary = await self.metrics_summary(model_version=model_version, district_ids=district_ids)
        batch.metrics_summary = summary.model_dump(mode="json")
        await self.session.flush()

        logger.info(
            "verification_batch_completed",
            batch_uid=batch_uid,
            considered=len(candidates),
            verified=verified_count,
            pending=pending_count,
            model_version=model_version,
        )
        return batch

    def _assert_no_leakage(self, forecast, aggregate) -> None:
        """Guard against scoring a forecast with an aggregate produced after scoring time.

        The aggregate window must end at or after the forecast target (it
        describes the target period) and must have been computed no earlier than
        the end of that window plus the configured grace period.
        """
        if aggregate.observed_at > forecast.target_time:
            raise ValueError(
                f"Aggregate {aggregate.id} starts after forecast {forecast.id} target time."
            )
        window_end = aggregate.observed_at + timedelta(minutes=aggregate.window_minutes)
        if window_end < forecast.target_time - timedelta(hours=1):
            raise ValueError(
                f"Aggregate {aggregate.id} window ends before forecast {forecast.id} target time."
            )

    async def _score_forecast(self, forecast_id: int, aggregate, event_threshold_mm: float) -> None:
        forecast = await self.forecast_repo.get_forecast(forecast_id)
        if forecast is None:
            return

        predicted = float(forecast.predicted_rainfall_mm)
        observed = float(aggregate.rainfall_mm)
        error = observed - predicted
        counts = vm.categorical_counts(
            np.array([predicted]), np.array([observed]), event_threshold_mm
        )
        mae = abs(error)
        rmse = mae
        nse = vm.nash_sutcliffe_efficiency(np.array([predicted]), np.array([observed]))
        brier = ((predicted - observed) / max(event_threshold_mm, 1e-6)) ** 2

        await self.verification_repo.upsert(
            forecast_id=forecast_id,
            aggregate_id=aggregate.id,
            status=VerificationStatus.VERIFIED,
            values={
                "observed_rainfall_mm": observed,
                "forecast_rainfall_mm": predicted,
                "error_mm": error,
                "absolute_error_mm": mae,
                "bias_mm": -error,
                "rmse_mm": rmse,
                "nash_sutcliffe": nse,
                "brier_score": float(brier),
                "hit": counts.hits == 1,
                "false_alarm": counts.false_alarms == 1,
                "missed": counts.misses == 1,
                "correct_negatives": counts.correct_negatives == 1,
                "verification_windows": [
                    {
                        "start": aggregate.observed_at.isoformat(),
                        "end": (
                            aggregate.observed_at + timedelta(minutes=aggregate.window_minutes)
                        ).isoformat(),
                        "window_minutes": aggregate.window_minutes,
                        "station_count": aggregate.station_count,
                        "coverage_ratio": aggregate.coverage_ratio,
                    }
                ],
            },
            observed_at=aggregate.observed_at,
            verified_at=utcnow(),
        )
        await self.forecast_repo.set_status(forecast, ForecastStatus.VERIFIED)

    async def metrics_summary(
        self,
        model_version: str | None = None,
        district_ids: list[int] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        event_threshold_mm: float = vm.DEFAULT_EVENT_THRESHOLD_MM,
    ) -> VerificationMetricsSummary:
        rows = await self.verification_repo.scored_rows(
            model_version=model_version, district_ids=district_ids, start=start, end=end
        )
        if not rows:
            return VerificationMetricsSummary(
                sample_size=0,
                mean_error_mm=0.0,
                mean_absolute_error_mm=0.0,
                rmse_mm=0.0,
                bias_mm=0.0,
                computed_at=utcnow(),
            )

        forecasts = np.array([float(f.predicted_rainfall_mm) for _, f in rows])
        observed = np.array([float(r.observed_rainfall_mm or 0.0) for r, _ in rows])
        leads = np.array([float(f.lead_time_hours) for _, f in rows])

        cont = vm.continuous_metrics(forecasts, observed)
        cat = vm.categorical_metrics(forecasts, observed, event_threshold_mm)
        nse = vm.nash_sutcliffe_efficiency(forecasts, observed)

        by_lead: dict[str, dict[str, float]] = {}
        for bucket in sorted({vm.lead_time_bucket(v) for v in leads}):
            mask = np.array([vm.lead_time_bucket(v) == bucket for v in leads])
            by_lead[bucket] = vm.continuous_metrics(forecasts[mask], observed[mask]).to_dict()

        by_severity: dict[str, dict[str, float]] = {}
        for severity in sorted({f.severity for _, f in rows}):
            mask = np.array([f.severity == severity for _, f in rows])
            if mask.any():
                by_severity[severity] = vm.continuous_metrics(
                    forecasts[mask], observed[mask]
                ).to_dict()

        return VerificationMetricsSummary(
            sample_size=cont.sample_size,
            mean_error_mm=cont.mean_error_mm,
            mean_absolute_error_mm=cont.mean_absolute_error_mm,
            rmse_mm=cont.rmse_mm,
            bias_mm=cont.bias_mm,
            nash_sutcliffe=nse,
            brier_score=cat.brier_score,
            hit_rate=cat.hit_rate,
            false_alarm_ratio=cat.far,
            detection_score=cat.pod,
            critical_success_index=cat.csi,
            by_lead_bucket=by_lead,
            by_severity=by_severity,
            computed_at=utcnow(),
        )
