"""Verification workflow: eligibility, scoring, metrics and persistence."""

from __future__ import annotations

import itertools
from datetime import timedelta
from pathlib import Path

import pytest

from app.core.enums import VerificationStatus
from app.models import VerificationResult
from app.services.verification_service import VerificationService
from app.utils.time import utcnow
from tests.factories import (
    make_daily_aggregates,
    make_district,
    make_forecast_run,
    make_region,
)

_SEQUENCE = itertools.count(1)


async def _seed_pair(
    session,
    model,
    *,
    rainfall: float,
    predicted: float,
    days_ago: int = 3,
    issue_lag_days: int = 1,
):
    """A district with an aggregate window and a forecast targeting it.

    Each call uses a fresh region and district so several pairs can coexist in
    one test.
    """
    index = next(_SEQUENCE)
    region = await make_region(session, code=f"R{index}", name=f"Region {index}")
    district = await make_district(
        session,
        region,
        code=f"D{index}",
        name=f"District {index}",
        lat=19.0 + index * 0.1,
        lon=72.0 + index * 0.1,
    )
    target = utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)
    await make_daily_aggregates(session, district, [rainfall], start=target - timedelta(days=1))
    forecast = await make_forecast_run(
        session,
        model,
        district,
        target,
        target - timedelta(days=issue_lag_days),
        predicted_mm=predicted,
    )
    await session.commit()
    return district, forecast, target


class TestVerificationScoring:
    async def test_error_is_observed_minus_forecast(
        self, session, shared_model, trained_artifact: Path
    ) -> None:
        _, forecast, _ = await _seed_pair(session, shared_model, rainfall=20.0, predicted=5.0)

        batch = await VerificationService(session).run_verification(lookback_days=14)
        await session.commit()

        assert batch.forecasts_verified == 1
        result = await _result(session, forecast.id)
        assert result.observed_rainfall_mm == pytest.approx(20.0)
        assert result.forecast_rainfall_mm == pytest.approx(5.0)
        assert result.error_mm == pytest.approx(15.0)
        assert result.absolute_error_mm == pytest.approx(15.0)
        assert result.bias_mm == pytest.approx(-15.0)
        assert result.status == VerificationStatus.VERIFIED

    async def test_forecast_marks_its_district_as_a_miss(
        self, session, shared_model, trained_artifact: Path
    ) -> None:
        # A dry forecast against a heavy event is a miss, not a hit.
        _, forecast, _ = await _seed_pair(session, shared_model, rainfall=30.0, predicted=1.0)

        await VerificationService(session).run_verification(lookback_days=14)
        await session.commit()

        result = await _result(session, forecast.id)
        assert result.missed is True
        assert result.hit is False
        assert result.false_alarm is False

    async def test_wet_forecast_against_a_dry_event_is_a_false_alarm(
        self, session, shared_model, trained_artifact: Path
    ) -> None:
        _, forecast, _ = await _seed_pair(session, shared_model, rainfall=0.5, predicted=25.0)

        await VerificationService(session).run_verification(lookback_days=14)
        await session.commit()

        result = await _result(session, forecast.id)
        assert result.false_alarm is True
        assert result.correct_negatives is False

    async def test_dry_forecast_against_a_dry_event_is_a_correct_negative(
        self, session, shared_model, trained_artifact: Path
    ) -> None:
        _, forecast, _ = await _seed_pair(session, shared_model, rainfall=0.2, predicted=0.4)

        await VerificationService(session).run_verification(lookback_days=14)
        await session.commit()

        result = await _result(session, forecast.id)
        assert result.correct_negatives is True

    async def test_matching_forecast_is_a_hit(
        self, session, shared_model, trained_artifact: Path
    ) -> None:
        _, forecast, _ = await _seed_pair(session, shared_model, rainfall=22.0, predicted=24.0)

        await VerificationService(session).run_verification(lookback_days=14)
        await session.commit()

        result = await _result(session, forecast.id)
        assert result.hit is True

    async def test_verification_window_is_recorded(
        self, session, shared_model, trained_artifact: Path
    ) -> None:
        _, forecast, _ = await _seed_pair(session, shared_model, rainfall=12.0, predicted=9.0)

        await VerificationService(session).run_verification(lookback_days=14)
        await session.commit()

        result = await _result(session, forecast.id)
        assert result.verification_windows
        window = result.verification_windows[0]
        assert window["window_minutes"] == 1440
        assert window["end"] > window["start"]


class TestVerificationEligibility:
    async def test_forecast_inside_the_grace_period_is_not_scored(
        self, session, shared_model, trained_artifact: Path
    ) -> None:
        # A target that elapsed minutes ago has not cleared the grace period, so
        # scoring it could compare against a partially accumulated observation.
        # A target that elapsed an hour ago has not cleared the six hour grace
        # period, so it is not even a candidate: scoring it could compare against
        # an observation whose accumulation window is still open.
        region = await make_region(session, code="RG", name="Grace")
        district = await make_district(session, region, code="DG", name="Grace district")
        target = utcnow() - timedelta(hours=1)
        await make_daily_aggregates(session, district, [20.0], start=target - timedelta(days=1))
        await make_forecast_run(session, shared_model, district, target, target - timedelta(days=1))
        await session.commit()

        batch = await VerificationService(session).run_verification(lookback_days=14)
        await session.commit()

        assert batch.forecasts_verified == 0
        assert batch.candidates_considered == 0

    async def test_forecast_without_an_observation_stays_pending(
        self, session, shared_model, trained_artifact: Path
    ) -> None:
        region = await make_region(session)
        district = await make_district(session, region)
        target = utcnow() - timedelta(days=3)
        forecast = await make_forecast_run(
            session, shared_model, district, target, target - timedelta(days=1)
        )
        await session.commit()

        batch = await VerificationService(session).run_verification(lookback_days=14)
        await session.commit()

        assert batch.forecasts_verified == 0
        assert batch.forecasts_pending == 1
        result = await _result(session, forecast.id)
        assert result.status == VerificationStatus.MISSING_OBSERVATION
        assert result.observed_rainfall_mm is None

    async def test_pending_forecast_is_not_forecasts_nonexistent(
        self, session, shared_model, trained_artifact: Path
    ) -> None:
        region = await make_region(session)
        district = await make_district(session, region)
        target = utcnow() - timedelta(days=3)
        forecast = await make_forecast_run(
            session, shared_model, district, target, target - timedelta(days=1)
        )
        await session.commit()

        service = VerificationService(session)
        await service.run_verification(lookback_days=14)
        summary = await service.metrics_summary()
        await session.commit()

        assert summary.sample_size == 0
        result = await _result(session, forecast.id)
        assert result.observed_rainfall_mm is None

    async def test_already_verified_forecasts_are_not_rescored(
        self, session, shared_model, trained_artifact: Path
    ) -> None:
        _, _, _ = await _seed_pair(session, shared_model, rainfall=20.0, predicted=5.0)
        service = VerificationService(session)

        first = await service.run_verification(lookback_days=14)
        second = await service.run_verification(lookback_days=14)
        await session.commit()

        assert first.forecasts_verified == 1
        assert second.forecasts_verified == 0

    async def test_force_rescores_an_existing_result(
        self, session, shared_model, trained_artifact: Path
    ) -> None:
        _, _, _ = await _seed_pair(session, shared_model, rainfall=20.0, predicted=5.0)
        service = VerificationService(session)

        await service.run_verification(lookback_days=14)
        forced = await service.run_verification(lookback_days=14, force=True)
        await session.commit()

        assert forced.forecasts_verified == 1

    async def test_lookback_window_excludes_older_forecasts(
        self, session, shared_model, trained_artifact: Path
    ) -> None:
        region = await make_region(session)
        district = await make_district(session, region)
        target = utcnow() - timedelta(days=40)
        await make_daily_aggregates(session, district, [20.0], start=target - timedelta(days=1))
        await make_forecast_run(session, shared_model, district, target, target - timedelta(days=1))
        await session.commit()

        batch = await VerificationService(session).run_verification(lookback_days=7)
        await session.commit()

        assert batch.forecasts_verified == 0


class TestVerificationMetrics:
    async def test_metrics_use_verified_rows_only(
        self, session, shared_model, trained_artifact: Path
    ) -> None:
        await _seed_pair(session, shared_model, rainfall=20.0, predicted=5.0, days_ago=2)
        await _seed_pair(session, shared_model, rainfall=2.0, predicted=4.0, days_ago=3)

        service = VerificationService(session)
        await service.run_verification(lookback_days=14)
        summary = await service.metrics_summary()
        await session.commit()

        assert summary.sample_size == 2
        assert summary.mean_absolute_error_mm == pytest.approx((15.0 + 2.0) / 2)
        assert summary.rmse_mm == pytest.approx(((15.0**2 + 2.0**2) / 2) ** 0.5)

    async def test_bias_matches_the_signed_error(
        self, session, shared_model, trained_artifact: Path
    ) -> None:
        await _seed_pair(session, shared_model, rainfall=20.0, predicted=5.0, days_ago=2)

        service = VerificationService(session)
        await service.run_verification(lookback_days=14)
        summary = await service.metrics_summary()
        await session.commit()

        assert summary.bias_mm == pytest.approx(-15.0)
        assert summary.mean_error_mm == pytest.approx(15.0)

    async def test_lead_buckets_are_reported(
        self, session, shared_model, trained_artifact: Path
    ) -> None:
        await _seed_pair(session, shared_model, rainfall=20.0, predicted=5.0, days_ago=2)

        service = VerificationService(session)
        await service.run_verification(lookback_days=14)
        summary = await service.metrics_summary()
        await session.commit()

        assert "12-24h" in summary.by_lead_bucket
        assert summary.by_lead_bucket["12-24h"]["sample_size"] == 1

    async def test_empty_metrics_are_zeroed_not_null(
        self, session, shared_model, trained_artifact: Path
    ) -> None:
        summary = await VerificationService(session).metrics_summary()
        assert summary.sample_size == 0
        assert summary.mean_absolute_error_mm == 0.0

    async def test_model_version_filter_isolates_scores(
        self, session, shared_model, trained_artifact: Path
    ) -> None:
        await _seed_pair(session, shared_model, rainfall=20.0, predicted=5.0, days_ago=2)

        service = VerificationService(session)
        await service.run_verification(lookback_days=14)
        matching = await service.metrics_summary(model_version=trained_artifact.name)
        other = await service.metrics_summary(model_version="v999")
        await session.commit()

        assert matching.sample_size == 1
        assert other.sample_size == 0


class TestVerificationBatch:
    async def test_batch_records_the_run(
        self, session, shared_model, trained_artifact: Path
    ) -> None:
        await _seed_pair(session, shared_model, rainfall=20.0, predicted=5.0, days_ago=2)

        batch = await VerificationService(session).run_verification(
            lookback_days=14, triggered_by="unit_test"
        )
        await session.commit()

        assert batch.batch_uid.startswith("vrf_")
        assert batch.triggered_by == "unit_test"
        assert batch.status == "completed"
        assert batch.candidates_considered == 1
        assert batch.finished_at is not None

    async def test_batch_stores_a_metrics_snapshot(
        self, session, shared_model, trained_artifact: Path
    ) -> None:
        await _seed_pair(session, shared_model, rainfall=20.0, predicted=5.0, days_ago=2)

        batch = await VerificationService(session).run_verification(lookback_days=14)
        await session.commit()

        assert batch.metrics_summary["sample_size"] == 1


async def _result(session, forecast_id: int) -> VerificationResult:
    from sqlalchemy import select

    return (
        await session.execute(
            select(VerificationResult).where(VerificationResult.forecast_id == forecast_id)
        )
    ).scalar_one()
