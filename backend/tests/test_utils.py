"""Time helpers, geographic filtering and API key hashing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.utils.geo import BoundingBox
from app.utils.security import generate_api_key, hash_api_key, verify_api_key
from app.utils.time import ensure_utc, floor_to_step, hour_range, utcnow


class TestTimeHelpers:
    def test_ensure_utc_attaches_utc_to_naive_timestamps(self) -> None:
        naive = datetime(2026, 9, 28, 6, 0)
        assert ensure_utc(naive).tzinfo == UTC

    def test_ensure_utc_converts_aware_timestamps(self) -> None:
        from datetime import timezone

        other = datetime(2026, 9, 28, 6, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        assert ensure_utc(other).hour == 0

    def test_floor_to_step_six_hours(self) -> None:
        moment = datetime(2026, 9, 28, 14, 37, 12, tzinfo=UTC)
        assert floor_to_step(moment, 6) == datetime(2026, 9, 28, 12, 0, tzinfo=UTC)

    def test_floor_to_step_24_hours_snaps_to_midnight(self) -> None:
        moment = datetime(2026, 9, 28, 14, 37, tzinfo=UTC)
        assert floor_to_step(moment, 24) == datetime(2026, 9, 28, 0, 0, tzinfo=UTC)

    def test_floor_to_zero_hours_is_an_error_risk_guarded_by_callers(self) -> None:
        # step_hours is validated as >= 1 at the schema layer; floor_to_step
        # itself must not silently produce nonsense for step 0.
        with pytest.raises(ZeroDivisionError):
            floor_to_step(datetime(2026, 9, 28, tzinfo=UTC), 0)

    def test_hour_range_is_exclusive_of_the_end(self) -> None:
        start = datetime(2026, 9, 28, 0, 0, tzinfo=UTC)
        end = start + timedelta(hours=12)
        assert hour_range(start, end, 6) == [
            start,
            start + timedelta(hours=6),
        ]

    def test_utcnow_is_timezone_aware(self) -> None:
        assert utcnow().tzinfo is not None


class TestBoundingBox:
    def test_empty_box_adds_no_clauses(self) -> None:
        assert BoundingBox().is_empty() is True

    def test_partial_box_is_not_empty(self) -> None:
        assert BoundingBox(min_lat=10.0).is_empty() is False

    def test_as_dict_exposes_all_bounds(self) -> None:
        box = BoundingBox(min_lat=1.0, min_lon=2.0, max_lat=3.0, max_lon=4.0)
        assert box.as_dict() == {"min_lat": 1.0, "min_lon": 2.0, "max_lat": 3.0, "max_lon": 4.0}


class TestApiKeys:
    def test_hash_is_deterministic_for_verification(self) -> None:
        assert hash_api_key("rck_abc") == hash_api_key("rck_abc")

    def test_different_keys_hash_differently(self) -> None:
        assert hash_api_key("rck_abc") != hash_api_key("rck_abd")

    def test_verify_accepts_the_matching_key(self) -> None:
        assert verify_api_key("rck_abc", hash_api_key("rck_abc")) is True

    def test_verify_rejects_a_different_key(self) -> None:
        assert verify_api_key("rck_other", hash_api_key("rck_abc")) is False

    def test_generated_keys_are_unique_and_prefixed(self) -> None:
        keys = {generate_api_key() for _ in range(50)}
        assert len(keys) == 50
        assert all(key.startswith("rck_") for key in keys)

    def test_hash_does_not_contain_the_raw_key(self) -> None:
        assert "rck_secret" not in hash_api_key("rck_secret")
