"""Forecast generation, alert derivation and the no-leakage guard."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.enums import ForecastStatus
from app.ml.predictor import ForecastGenerator
from app.ml.registry import model_registry
from app.models import Forecast
from app.repositories.forecast_repository import ForecastRepository
from app.services.alert_service import AlertService
from app.services.severity import classify
from tests.factories import (
    BASE_TIME,
    make_active_model,
    make_daily_aggregates,
    make_district,
    make_forecast_run,
    make_region,
)


class TestSeverityConsistency:
    def test_persisted_severity_matches_the_classifier(self) -> None:
        for rainfall in (0.0, 1.0, 3.0, 9.0, 20.0, 40.0):
            assert classify(rainfall) in {
                "none",
                "light",
                "moderate",
                "heavy",
                "very_heavy",
                "extreme",
            }


class TestForecastGeneration:
    async def test_generates_one_forecast_per_district(
        self, session, trained_artifact: Path
    ) -> None:
        region = await make_region(session)
        districts = [
            await make_district(session, region, code="MH-MUM", lat=19.2, lon=72.9),
            await make_district(session, region, code="MH-PUN", lat=18.5, lon=73.8),
        ]
        for district in districts:
            await make_daily_aggregates(
                session, district, [2.0, 5.0, 12.0, 1.0, 8.0, 0.0, 3.0, 20.0, 4.0, 6.0]
            )
        model = await make_active_model(session, trained_artifact)
        await session.commit()

        artifact = model_registry.set_active(model.version)
        run, predictions, _ = await ForecastGenerator(session).generate(
            artifact=artifact,
            issued_at=BASE_TIME - timedelta(days=1),
            horizon_hours=24,
            step_hours=24,
            district_ids=[d.id for d in districts],
        )
        await session.commit()

        assert len(predictions) == 2
        assert run.model_version_id == model.id
        assert {p.district_id for p in predictions} == {d.id for d in districts}

        stored = (
            (await session.execute(select(Forecast).where(Forecast.run_id == run.id)))
            .scalars()
            .all()
        )
        assert len(stored) == 2

    async def test_predictions_never_go_negative(self, session, trained_artifact: Path) -> None:
        region = await make_region(session)
        district = await make_district(session, region)
        await make_daily_aggregates(session, district, [0.0] * 12)
        model = await make_active_model(session, trained_artifact)
        await session.commit()

        artifact = model_registry.set_active(model.version)
        _, predictions, _ = await ForecastGenerator(session).generate(
            artifact=artifact,
            issued_at=BASE_TIME - timedelta(days=1),
            district_ids=[district.id],
        )
        await session.commit()

        assert all(p.predicted_rainfall_mm >= 0 for p in predictions)
        assert all(
            p.lower_bound_mm <= p.predicted_rainfall_mm <= p.upper_bound_mm for p in predictions
        )

    async def test_intervals_bracket_the_point_forecast(
        self, session, trained_artifact: Path
    ) -> None:
        region = await make_region(session)
        district = await make_district(session, region)
        await make_daily_aggregates(
            session, district, [30.0, 12.0, 4.0, 18.0, 2.0, 0.0, 1.0, 25.0, 9.0, 3.0]
        )
        model = await make_active_model(session, trained_artifact)
        await session.commit()

        artifact = model_registry.set_active(model.version)
        _, predictions, _ = await ForecastGenerator(session).generate(
            artifact=artifact, issued_at=BASE_TIME - timedelta(days=1), district_ids=[district.id]
        )
        await session.commit()

        for prediction in predictions:
            assert prediction.lower_bound_mm <= prediction.predicted_rainfall_mm
            assert prediction.predicted_rainfall_mm <= prediction.upper_bound_mm

    async def test_future_issue_time_is_rejected(self, session, trained_artifact: Path) -> None:
        from datetime import timedelta as delta

        from app.utils.time import utcnow

        region = await make_region(session)
        district = await make_district(session, region)
        model = await make_active_model(session, trained_artifact)
        await session.commit()

        artifact = model_registry.set_active(model.version)
        with pytest.raises(ValueError, match="cannot be in the future"):
            await ForecastGenerator(session).generate(
                artifact=artifact, issued_at=utcnow() + delta(days=2), district_ids=[district.id]
            )

    async def test_issue_time_in_the_future_is_rejected_before_any_write(
        self, session, trained_artifact: Path
    ) -> None:
        from app.utils.time import utcnow

        region = await make_region(session)
        district = await make_district(session, region)
        model = await make_active_model(session, trained_artifact)
        await session.commit()
        before = (await session.execute(select(Forecast))).scalars().all()

        artifact = model_registry.set_active(model.version)
        with pytest.raises(ValueError):
            await ForecastGenerator(session).generate(
                artifact=artifact,
                issued_at=utcnow() + timedelta(days=1),
                district_ids=[district.id],
            )
        after = (await session.execute(select(Forecast))).scalars().all()
        assert len(before) == len(after) == 0

    async def test_generation_without_registration_is_refused(
        self, session, trained_artifact: Path
    ) -> None:
        from app.core.exceptions import ModelUnavailableError

        region = await make_region(session)
        district = await make_district(session, region)
        await make_daily_aggregates(session, district, [1.0] * 12)
        await session.commit()

        artifact = model_registry.set_active(trained_artifact.name)
        with pytest.raises(ModelUnavailableError, match="not registered"):
            await ForecastGenerator(session).generate(
                artifact=artifact,
                issued_at=BASE_TIME - timedelta(days=1),
                district_ids=[district.id],
            )


class TestForecastPersistence:
    async def test_detail_includes_lead_time_values(self, session, trained_artifact: Path) -> None:
        region = await make_region(session)
        district = await make_district(session, region)
        model = await make_active_model(session, trained_artifact)
        issued = BASE_TIME - timedelta(days=2)
        await make_forecast_run(session, model, district, BASE_TIME - timedelta(days=1), issued)
        await session.commit()

        repo = ForecastRepository(session)
        stored = (await session.execute(select(Forecast))).scalars().one()
        detail = await repo.get_forecast(stored.id)

        assert detail is not None
        assert len(detail.values) == 1
        assert detail.values[0].lead_hours == 24.0

    async def test_status_filtering_uses_the_indexed_columns(
        self, session, trained_artifact: Path
    ) -> None:
        region = await make_region(session)
        districts = [
            await make_district(session, region, code="MH-MUM", lat=19.2, lon=72.9),
            await make_district(session, region, code="MH-PUN", lat=18.5, lon=73.8),
        ]
        model = await make_active_model(session, trained_artifact)
        issued = BASE_TIME - timedelta(days=2)
        target = BASE_TIME - timedelta(days=1)

        first = await make_forecast_run(
            session, model, districts[0], target, issued, predicted_mm=20.0
        )
        await make_forecast_run(session, model, districts[1], target, issued, predicted_mm=2.0)
        first.status = ForecastStatus.VERIFIED
        await session.commit()

        from app.schemas.forecast import ForecastQueryFilters

        repo = ForecastRepository(session)
        rows, total = await repo.list_forecasts(
            ForecastQueryFilters(min_rainfall_mm=10.0), offset=0, limit=10
        )
        assert total == 1
        assert rows[0].district_id == districts[0].id

    async def test_bounding_box_filter_is_applied(self, session, trained_artifact: Path) -> None:
        from app.schemas.forecast import ForecastQueryFilters

        region = await make_region(session)
        mumbai = await make_district(session, region, code="MH-MUM", lat=19.2, lon=72.9)
        pune = await make_district(session, region, code="MH-PUN", lat=18.5, lon=73.8)
        model = await make_active_model(session, trained_artifact)
        issued = BASE_TIME - timedelta(days=2)
        target = BASE_TIME - timedelta(days=1)
        await make_forecast_run(session, model, mumbai, target, issued)
        await make_forecast_run(session, model, pune, target, issued)
        await session.commit()

        rows, total = await ForecastRepository(session).list_forecasts(
            ForecastQueryFilters(min_lat=19.0, max_lat=19.5, min_lon=72.5, max_lon=73.0),
            offset=0,
            limit=10,
        )
        assert total == 1
        assert rows[0].district_id == mumbai.id


class TestAlerts:
    async def test_heavy_forecast_raises_a_warning(self, session, trained_artifact: Path) -> None:
        region = await make_region(session)
        district = await make_district(session, region)
        model = await make_active_model(session, trained_artifact)
        issued = BASE_TIME - timedelta(days=2)
        forecast = await make_forecast_run(
            session,
            model,
            district,
            BASE_TIME - timedelta(days=1),
            issued,
            predicted_mm=20.0,
            severity="heavy",
        )
        await session.commit()

        created = await AlertService(session).evaluate_forecasts([forecast])
        await session.commit()
        assert created == 1

    async def test_light_forecast_raises_nothing(self, session, trained_artifact: Path) -> None:
        region = await make_region(session)
        district = await make_district(session, region)
        model = await make_active_model(session, trained_artifact)
        issued = BASE_TIME - timedelta(days=2)
        forecast = await make_forecast_run(
            session,
            model,
            district,
            BASE_TIME - timedelta(days=1),
            issued,
            predicted_mm=1.0,
            severity="light",
        )
        await session.commit()

        assert await AlertService(session).evaluate_forecasts([forecast]) == 0

    async def test_extreme_forecast_raises_critical(self, session, trained_artifact: Path) -> None:
        from app.core.enums import AlertSeverity

        region = await make_region(session)
        district = await make_district(session, region)
        model = await make_active_model(session, trained_artifact)
        issued = BASE_TIME - timedelta(days=2)
        forecast = await make_forecast_run(
            session,
            model,
            district,
            BASE_TIME - timedelta(days=1),
            issued,
            predicted_mm=60.0,
            severity="extreme",
        )
        await session.commit()

        await AlertService(session).evaluate_forecasts([forecast])
        alerts = await AlertService(session).list_alerts(None, None, None, None, 0, 10)
        assert alerts[0][0].severity == AlertSeverity.CRITICAL

    async def test_cooldown_suppresses_repeat_alerts(self, session, trained_artifact: Path) -> None:
        region = await make_region(session)
        district = await make_district(session, region)
        model = await make_active_model(session, trained_artifact)
        issued = BASE_TIME - timedelta(days=2)
        target = BASE_TIME - timedelta(days=1)

        # Two issuances for the same district, one hour apart: a run holds one
        # forecast per district, so the second needs its own run.
        first = await make_forecast_run(
            session, model, district, target, issued, predicted_mm=20.0, severity="heavy"
        )
        second = await make_forecast_run(
            session,
            model,
            district,
            target + timedelta(hours=1),
            issued + timedelta(hours=1),
            predicted_mm=22.0,
            severity="heavy",
        )
        await session.commit()

        service = AlertService(session)
        assert await service.evaluate_forecasts([first]) == 1
        assert await service.evaluate_forecasts([second]) == 0


class TestLeakageGuard:
    def test_aggregate_starting_after_the_target_is_rejected(self) -> None:
        from app.services.verification_service import VerificationService

        service = VerificationService.__new__(VerificationService)

        class Forecast:
            id = 1
            target_time = datetime(2026, 9, 27, tzinfo=UTC)

        class Aggregate:
            id = 1
            observed_at = datetime(2026, 9, 28, tzinfo=UTC)
            window_minutes = 1440

        with pytest.raises(ValueError, match="starts after"):
            service._assert_no_leakage(Forecast(), Aggregate())

    def test_aggregate_ending_before_the_target_is_rejected(self) -> None:
        from app.services.verification_service import VerificationService

        service = VerificationService.__new__(VerificationService)

        class Forecast:
            id = 1
            target_time = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)

        class Aggregate:
            id = 1
            observed_at = datetime(2026, 9, 20, tzinfo=UTC)
            window_minutes = 1440

        with pytest.raises(ValueError, match="ends before"):
            service._assert_no_leakage(Forecast(), Aggregate())

    def test_matching_window_is_accepted(self) -> None:
        from app.services.verification_service import VerificationService

        service = VerificationService.__new__(VerificationService)

        class Forecast:
            id = 1
            target_time = datetime(2026, 9, 27, tzinfo=UTC)

        class Aggregate:
            id = 1
            observed_at = datetime(2026, 9, 26, tzinfo=UTC)
            window_minutes = 1440

        service._assert_no_leakage(Forecast(), Aggregate())
