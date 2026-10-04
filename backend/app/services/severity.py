"""Rainfall severity classification.

Thresholds follow IMD-style heavy rainfall categories for 24h accumulations.
They are configuration, not magic numbers, and are exposed through the API so
the UI legend and the alert rules stay in sync.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.enums import AlertSeverity

# (upper bound in mm, label, severity, colour token used by the map legend)
SEVERITY_BANDS: tuple[tuple[float, str, str, str], ...] = (
    (0.1, "no_rain", "none", "#e2e8f0"),
    (2.5, "light", "light", "#60a5fa"),
    (7.6, "moderate", "moderate", "#2563eb"),
    (15.6, "heavy", "heavy", "#7c3aed"),
    (31.8, "very_heavy", "very_heavy", "#c026d3"),
    (float("inf"), "extremely_heavy", "extreme", "#b91c1c"),
)

SEVERITY_TO_ALERT: dict[str, AlertSeverity] = {
    "light": AlertSeverity.INFO,
    "moderate": AlertSeverity.INFO,
    "heavy": AlertSeverity.WARNING,
    "very_heavy": AlertSeverity.SEVERE,
    "extreme": AlertSeverity.CRITICAL,
    "none": AlertSeverity.INFO,
}


@dataclass(frozen=True)
class SeverityBand:
    label: str
    severity: str
    color: str
    min_mm: float
    max_mm: float | None


def classify(rainfall_mm: float) -> str:
    value = max(float(rainfall_mm), 0.0)
    for upper, _label, severity, _color in SEVERITY_BANDS:
        if value < upper:
            return severity
    return "extreme"


def band_for(rainfall_mm: float) -> SeverityBand:
    value = max(float(rainfall_mm), 0.0)
    lower = 0.0
    for upper, label, severity, color in SEVERITY_BANDS:
        if value < upper:
            ceiling = None if upper == float("inf") else upper
            return SeverityBand(label, severity, color, lower, ceiling)
        lower = upper
    return SeverityBand("extremely_heavy", "extreme", "#b91c1c", lower, None)


def legend() -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    lower = 0.0
    for upper, label, severity, color in SEVERITY_BANDS:
        entries.append(
            {
                "label": label,
                "severity": severity,
                "color": color,
                "min_mm": lower,
                "max_mm": None if upper == float("inf") else upper,
            }
        )
        lower = upper
    return entries
