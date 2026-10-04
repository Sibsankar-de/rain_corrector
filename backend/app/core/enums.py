"""Domain enums shared by ORM models, schemas and services."""

from __future__ import annotations

from enum import StrEnum


class ModelStatus(StrEnum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    ACTIVE = "active"
    ARCHIVED = "archived"
    REJECTED = "rejected"


class TrainingStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ForecastStatus(StrEnum):
    PENDING = "pending"
    ISSUED = "issued"
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    EXPIRED = "expired"


class VerificationStatus(StrEnum):
    PENDING_OBSERVATION = "pending_observation"
    VERIFIED = "verified"
    MISSING_OBSERVATION = "missing_observation"


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    SEVERE = "severe"
    CRITICAL = "critical"


class AlertStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class DataOrigin(StrEnum):
    OBSERVED = "observed"
    SYNTHETIC = "synthetic"
    EXTERNAL = "external"
