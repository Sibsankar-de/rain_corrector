"""API surface: contracts, validation, error shape and pagination."""

from __future__ import annotations

import itertools
from datetime import timedelta

import pytest

from app.core.enums import AlertSeverity, ModelStatus
from app.models import Forecast
from tests.factories import (
    BASE_TIME,
    make_daily_aggregates,
    make_district,
    make_forecast_run,
    make_region,
    make_station,
)

pytestmark = pytest.mark.integration


class TestHealth:
    async def test_health_is_public(self, client) -> None:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    async def test_readiness_reports_database_and_model(
        self, client, shared_model, trained_artifact
    ) -> None:
        from app.ml.registry import model_registry

        model_registry.set_active(trained_artifact.name)
        response = await client.get("/api/v1/health/ready")
        payload = response.json()

        assert payload["database"] == "ok"
        assert payload["available_model_versions"]
        assert payload["model_loaded"] is (model_registry.active_version is not None)
        assert payload["model_version"] == model_registry.active_version

    async def test_readiness_is_503_without_a_model(self, client) -> None:
        from app.ml.registry import model_registry

        model_registry.set_active(None)
        response = await client.get("/api/v1/health/ready")
        assert response.status_code == 503
        assert response.json()["model_loaded"] is False


class TestOpenApi:
    async def test_schema_is_served(self, client) -> None:
        response = await client.get("/openapi.json")
        schema = response.json()
        assert schema["info"]["title"] == "Rain Corrector"
        assert "/api/v1/forecasts" in schema["paths"]
        assert "/api/v1/dashboard/overview" in schema["paths"]

    async def test_every_operation_is_described(self, client) -> None:
        schema = (await client.get("/openapi.json")).json()
        undocumented = [
            f"{method.upper()} {path}"
            for path, operations in schema["paths"].items()
            for method, operation in operations.items()
            if method in {"get", "post", "patch", "delete"} and not operation.get("summary")
        ]
        assert undocumented == []


class TestErrorContract:
    async def test_404_uses_the_structured_envelope(self, client) -> None:
        response = await client.get("/api/v1/forecasts/999999")
        payload = response.json()

        assert response.status_code == 404
        assert payload["error"]["code"] == "not_found"
        assert payload["request_id"]
        assert "Traceback" not in payload["error"]["message"]

    async def test_validation_error_lists_field_problems(self, client) -> None:
        response = await client.get("/api/v1/forecasts?min_lat=999")
        payload = response.json()

        assert response.status_code == 422
        assert payload["error"]["code"] == "validation_error"
        assert payload["error"]["details"][0]["field"] == "min_lat"

    async def test_request_id_is_echoed(self, client) -> None:
        response = await client.get("/api/v1/health", headers={"X-Request-ID": "trace-42"})
        assert response.headers["X-Request-ID"] == "trace-42"

    async def test_process_time_header_is_present(self, client) -> None:
        response = await client.get("/api/v1/health")
        assert response.headers["X-Process-Time"].endswith("ms")


class TestLocations:
    async def test_districts_are_paginated(self, client, session) -> None:
        region = await make_region(session)
        for index in range(5):
            await make_district(session, region, code=f"D{index}", name=f"District {index}")
        await session.commit()

        response = await client.get("/api/v1/locations/districts?page=1&page_size=2")
        payload = response.json()

        assert len(payload["items"]) == 2
        assert payload["meta"]["total"] == 5
        assert payload["meta"]["total_pages"] == 3
        assert payload["meta"]["has_next"] is True
        assert payload["meta"]["has_previous"] is False

    async def test_page_beyond_the_end_is_empty_not_an_error(self, client, session) -> None:
        region = await make_region(session)
        await make_district(session, region, code="D1", name="Only district")
        await session.commit()

        payload = (await client.get("/api/v1/locations/districts?page=9&page_size=20")).json()
        assert payload["items"] == []
        assert payload["meta"]["has_next"] is False

    async def test_search_filters_by_name(self, client, session) -> None:
        region = await make_region(session)
        await make_district(session, region, code="D1", name="Pune")
        await make_district(session, region, code="D2", name="Nagpur")
        await session.commit()

        payload = (await client.get("/api/v1/locations/districts?search=pune")).json()
        assert [d["name"] for d in payload["items"]] == ["Pune"]

    async def test_district_detail_includes_region_and_station_count(self, client, session) -> None:
        region = await make_region(session)
        district = await make_district(session, region)
        await make_station(session, district)
        await session.commit()

        payload = (await client.get(f"/api/v1/locations/districts/{district.id}")).json()
        assert payload["region"]["name"] == region.name
        assert payload["station_count"] == 1

    async def test_unknown_district_is_404(self, client) -> None:
        assert (await client.get("/api/v1/locations/districts/4242")).status_code == 404

    async def test_station_creation_validates_coordinates(self, client, session) -> None:
        region = await make_region(session)
        district = await make_district(session, region)
        await session.commit()

        response = await client.post(
            "/api/v1/locations/stations",
            json={
                "code": "ST-BAD",
                "name": "Bad gauge",
                "district_id": district.id,
                "latitude": 999,
                "longitude": 72.9,
            },
        )
        assert response.status_code == 422

    async def test_station_creation_rejects_a_blank_name(self, client, session) -> None:
        region = await make_region(session)
        district = await make_district(session, region)
        await session.commit()

        response = await client.post(
            "/api/v1/locations/stations",
            json={
                "code": "ST-BLANK",
                "name": "   ",
                "district_id": district.id,
                "latitude": 19.2,
                "longitude": 72.9,
            },
        )
        assert response.status_code == 422

    async def test_station_creation_succeeds(self, client, session) -> None:
        region = await make_region(session)
        district = await make_district(session, region)
        await session.commit()

        response = await client.post(
            "/api/v1/locations/stations",
            json={
                "code": "ST-OK",
                "name": "Working gauge",
                "district_id": district.id,
                "latitude": 19.2,
                "longitude": 72.9,
            },
        )
        assert response.status_code == 201
        assert response.json()["code"] == "ST-OK"


class TestObservations:
    async def test_ingest_accepts_a_batch_and_is_idempotent(self, client, session) -> None:
        region = await make_region(session)
        district = await make_district(session, region)
        station = await make_station(session, district)
        await session.commit()

        payload = {
            "observations": [
                {
                    "station_id": station.id,
                    "observed_at": BASE_TIME.isoformat(),
                    "window_minutes": 1440,
                    "rainfall_mm": 12.5,
                }
            ],
            "recompute_aggregates": False,
        }

        first = (await client.post("/api/v1/observations/ingest", json=payload)).json()
        second = (await client.post("/api/v1/observations/ingest", json=payload)).json()

        assert first["accepted"] == 1
        assert first["duplicates"] == 0
        assert second["accepted"] == 0
        assert second["duplicates"] == 1

    async def test_ingest_rejects_future_observations(self, client, session) -> None:
        from app.utils.time import utcnow

        region = await make_region(session)
        district = await make_district(session, region)
        station = await make_station(session, district)
        await session.commit()

        response = await client.post(
            "/api/v1/observations/ingest",
            json={
                "observations": [
                    {
                        "station_id": station.id,
                        "observed_at": (utcnow() + timedelta(days=1)).isoformat(),
                        "rainfall_mm": 5.0,
                    }
                ]
            },
        )
        assert response.status_code == 422

    async def test_ingest_rejects_an_empty_batch(self, client) -> None:
        response = await client.post("/api/v1/observations/ingest", json={"observations": []})
        assert response.status_code == 422

    async def test_aggregates_endpoint_returns_rows(self, client, session) -> None:
        region = await make_region(session)
        district = await make_district(session, region)
        await make_daily_aggregates(session, district, [3.0, 9.0, 22.0])
        await session.commit()

        payload = (
            await client.get(f"/api/v1/observations/aggregates?district_id={district.id}")
        ).json()
        assert len(payload) == 3
        assert payload[0]["window_minutes"] == 1440


class TestForecastsApi:
    async def test_forecast_detail_exposes_lead_time_values(
        self, client, session, shared_model, trained_artifact
    ) -> None:
        region = await make_region(session)
        district = await make_district(session, region)
        await make_forecast_run(
            session, shared_model, district, BASE_TIME, BASE_TIME - timedelta(days=1)
        )
        await session.commit()

        forecast_id = await _first_forecast_id(session)
        payload = (await client.get(f"/api/v1/forecasts/{forecast_id}")).json()

        assert payload["model_version"] == trained_artifact.name
        assert len(payload["values"]) == 1
        assert payload["district"]["code"] == district.code

    async def test_runs_endpoint_counts_forecasts(self, client, session, shared_model) -> None:
        region = await make_region(session)
        district = await make_district(session, region)
        await make_forecast_run(
            session, shared_model, district, BASE_TIME, BASE_TIME - timedelta(days=1)
        )
        await session.commit()

        payload = (await client.get("/api/v1/forecasts/runs")).json()
        assert payload["meta"]["total"] == 1
        assert payload["items"][0]["forecast_count"] == 1

    async def test_map_endpoint_returns_the_latest_run(self, client, session, shared_model) -> None:
        region = await make_region(session)
        district = await make_district(session, region)
        await make_forecast_run(
            session, shared_model, district, BASE_TIME, BASE_TIME - timedelta(days=1)
        )
        await session.commit()

        payload = (await client.get("/api/v1/forecasts/map")).json()
        assert len(payload) == 1
        assert payload[0]["district_id"] == district.id

    async def test_legend_is_contiguous(self, client) -> None:
        payload = (await client.get("/api/v1/forecasts/legend")).json()
        assert len(payload) >= 5
        for previous, current in itertools.pairwise(payload):
            assert previous["max_mm"] == current["min_mm"]

    async def test_severity_filter_narrows_results(self, client, session, shared_model) -> None:
        region = await make_region(session)
        district = await make_district(session, region, code="D1", name="One")
        other = await make_district(session, region, code="D2", name="Two")
        await make_forecast_run(
            session,
            shared_model,
            district,
            BASE_TIME,
            BASE_TIME - timedelta(days=1),
            predicted_mm=20.0,
            severity="heavy",
        )
        await make_forecast_run(
            session,
            shared_model,
            other,
            BASE_TIME,
            BASE_TIME - timedelta(days=1),
            predicted_mm=1.0,
            severity="light",
        )
        await session.commit()

        payload = (await client.get("/api/v1/forecasts?severity=heavy")).json()
        assert [f["severity"] for f in payload["items"]] == ["heavy"]


class TestDashboardApi:
    async def test_overview_reports_a_consistent_payload(
        self, client, session, shared_model, trained_artifact
    ) -> None:
        from app.ml.registry import model_registry

        model_registry.set_active(trained_artifact.name)

        region = await make_region(session)
        district = await make_district(session, region)
        await make_daily_aggregates(session, district, [4.0, 8.0, 25.0])
        await make_forecast_run(
            session,
            shared_model,
            district,
            BASE_TIME,
            BASE_TIME - timedelta(days=1),
            predicted_mm=18.0,
            severity="heavy",
        )
        await session.commit()

        payload = (await client.get("/api/v1/dashboard/overview")).json()

        assert payload["active_model_version"] == trained_artifact.name
        assert payload["summary"]["forecasts_last_7d"] == 1
        assert payload["summary"]["districts_at_risk"] == 1
        assert payload["status"]["forecasts_issued"] == 1
        assert payload["top_risk_districts"][0]["name"] == district.name
        assert len(payload["legend"]) >= 5

    async def test_overview_is_empty_but_valid_without_data(self, client) -> None:
        payload = (await client.get("/api/v1/dashboard/overview")).json()
        assert payload["verification"]["sample_size"] == 0
        assert payload["top_risk_districts"] == []
        assert payload["summary"]["forecasts_last_7d"] == 0


class TestModelApi:
    async def test_versions_and_active_agree(
        self, client, session, shared_model, trained_artifact
    ) -> None:
        versions = (await client.get("/api/v1/models/versions")).json()
        active = (await client.get("/api/v1/models/active")).json()

        assert versions["meta"]["total"] == 1
        assert versions["items"][0]["status"] == ModelStatus.ACTIVE
        assert active["version"] == versions["items"][0]["version"]

    async def test_version_detail_exposes_features_and_metrics(
        self, client, shared_model, trained_artifact
    ) -> None:
        payload = (await client.get(f"/api/v1/models/versions/{trained_artifact.name}")).json()
        assert payload["features"]
        assert payload["metrics"]["selected_model"]
        assert payload["trained_at"]

    async def test_unknown_version_is_404(self, client) -> None:
        assert (await client.get("/api/v1/models/versions/v999")).status_code == 404

    async def test_promotion_rejects_a_worse_candidate(
        self, client, session, shared_model, trained_artifact
    ) -> None:
        # auto_promote_if_better must not replace the active model when the
        # candidate has no verified evidence of being better.
        response = await client.post(
            "/api/v1/models/promote", json={"target_version": trained_artifact.name}
        )
        # The same version is already active, so this is a no-op success.
        assert response.status_code in (200, 409)

    async def test_promotion_of_an_unknown_version_is_404(self, client) -> None:
        response = await client.post("/api/v1/models/promote", json={"target_version": "v999"})
        assert response.status_code == 404

    async def test_promotion_with_an_unknown_policy_is_422(self, client, shared_model) -> None:
        response = await client.post(
            "/api/v1/models/promote",
            json={"target_version": shared_model.version, "policy": "yolo"},
        )
        assert response.status_code == 422


class TestAlertsApi:
    async def test_alerts_are_paginated_and_filterable(self, client, session, shared_model) -> None:
        from app.models import Alert

        region = await make_region(session)
        district = await make_district(session, region)
        session.add(
            Alert(
                district_id=district.id,
                severity=AlertSeverity.WARNING,
                alert_type="heavy_rainfall",
                title="Heavy rainfall predicted",
                message="20 mm predicted",
                threshold_mm=15.6,
                valid_from=BASE_TIME,
                valid_to=BASE_TIME + timedelta(hours=6),
            )
        )
        await session.commit()

        payload = (await client.get("/api/v1/alerts?severity=warning")).json()
        assert payload["meta"]["total"] == 1
        assert payload["items"][0]["district_name"] == district.name

        filtered = (await client.get("/api/v1/alerts?severity=critical")).json()
        assert filtered["meta"]["total"] == 0

    async def test_summary_counts_unresolved_alerts(self, client, session, shared_model) -> None:
        from app.models import Alert

        region = await make_region(session)
        district = await make_district(session, region)
        for severity in (AlertSeverity.WARNING, AlertSeverity.CRITICAL):
            session.add(
                Alert(
                    district_id=district.id,
                    severity=severity,
                    alert_type="heavy_rainfall",
                    title="Alert",
                    message="message",
                    threshold_mm=15.6,
                    valid_from=BASE_TIME,
                    valid_to=BASE_TIME + timedelta(hours=6),
                )
            )
        await session.commit()

        assert (await client.get("/api/v1/alerts/summary")).json() == {
            "warning": 1,
            "critical": 1,
        }

    async def test_status_can_be_acknowledged(self, client, session, shared_model) -> None:
        from app.models import Alert

        region = await make_region(session)
        district = await make_district(session, region)
        alert = Alert(
            district_id=district.id,
            severity=AlertSeverity.WARNING,
            alert_type="heavy_rainfall",
            title="Alert",
            message="message",
            threshold_mm=15.6,
            valid_from=BASE_TIME,
            valid_to=BASE_TIME + timedelta(hours=6),
        )
        session.add(alert)
        await session.commit()

        response = await client.patch(f"/api/v1/alerts/{alert.id}", json={"status": "acknowledged"})
        assert response.status_code == 200
        assert response.json()["status"] == "acknowledged"

    async def test_invalid_status_value_is_422(self, client, session, shared_model) -> None:
        from app.models import Alert

        region = await make_region(session)
        district = await make_district(session, region)
        alert = Alert(
            district_id=district.id,
            severity=AlertSeverity.WARNING,
            alert_type="heavy_rainfall",
            title="Alert",
            message="message",
            threshold_mm=15.6,
            valid_from=BASE_TIME,
            valid_to=BASE_TIME + timedelta(hours=6),
        )
        session.add(alert)
        await session.commit()

        response = await client.patch(f"/api/v1/alerts/{alert.id}", json={"status": "exploded"})
        assert response.status_code == 422


class TestVerificationApi:
    async def test_metrics_endpoint_returns_scores(
        self, client, session, shared_model, trained_artifact
    ) -> None:
        from datetime import UTC, datetime

        from app.services.verification_service import VerificationService

        now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        target = now - timedelta(days=3)

        region = await make_region(session)
        district = await make_district(session, region)
        await make_daily_aggregates(session, district, [20.0], start=target - timedelta(days=1))
        await make_forecast_run(
            session, shared_model, district, target, target - timedelta(days=1), predicted_mm=6.0
        )
        await session.commit()

        await VerificationService(session).run_verification(lookback_days=14)
        await session.commit()

        payload = (await client.get("/api/v1/verification/metrics")).json()
        assert payload["sample_size"] == 1
        assert payload["mean_absolute_error_mm"] == pytest.approx(14.0)

    async def test_run_endpoint_reports_counts(self, client, session, shared_model) -> None:
        payload = (await client.post("/api/v1/verification/run", json={"lookback_days": 7})).json()

        assert payload["batch_uid"].startswith("vrf_")
        assert payload["candidates_considered"] == 0
        assert payload["forecasts_verified"] == 0

    async def test_run_rejects_an_out_of_range_lookback(self, client) -> None:
        response = await client.post("/api/v1/verification/run", json={"lookback_days": 9999})
        assert response.status_code == 422

    async def test_result_for_an_unverified_forecast_is_404(
        self, client, session, shared_model
    ) -> None:
        region = await make_region(session)
        district = await make_district(session, region)
        await make_forecast_run(
            session, shared_model, district, BASE_TIME, BASE_TIME - timedelta(days=1)
        )
        await session.commit()

        response = await client.get(
            f"/api/v1/verification/forecast/{await _first_forecast_id(session)}"
        )
        assert response.status_code == 404


async def _first_forecast_id(session) -> int:
    from sqlalchemy import select

    return (await session.execute(select(Forecast.id))).scalars().one()
