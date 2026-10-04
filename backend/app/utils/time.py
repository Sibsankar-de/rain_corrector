"""Time helpers. All timestamps are timezone-aware UTC."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def floor_to_step(value: datetime, step_hours: int) -> datetime:
    ensure_utc(value)
    total_minutes = step_hours * 60
    minutes = value.hour * 60 + value.minute
    floored = (minutes // total_minutes) * total_minutes
    return value.replace(hour=floored // 60, minute=floored % 60, second=0, microsecond=0)


def hour_range(start: datetime, end: datetime, step_hours: int = 6) -> list[datetime]:
    current = floor_to_step(start, step_hours)
    out: list[datetime] = []
    while current < ensure_utc(end):
        out.append(current)
        current += timedelta(hours=step_hours)
    return out
