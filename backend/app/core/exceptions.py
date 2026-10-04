"""Domain exceptions mapped to HTTP responses by the API layer."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for every expected failure raised by the application."""

    status_code: int = 500
    code: str = "internal_error"
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = details
        super().__init__(self.message)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details is not None:
            payload["details"] = self.details
        return payload


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "The requested resource does not exist."


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"
    message = "The supplied parameters are invalid."


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message = "The resource conflicts with the current state."


class ModelUnavailableError(AppError):
    status_code = 503
    code = "model_unavailable"
    message = "No model is currently loaded for inference."


class PredictionError(AppError):
    status_code = 500
    code = "prediction_failed"
    message = "The model failed to produce a prediction."


class ProviderError(AppError):
    status_code = 502
    code = "provider_error"
    message = "An upstream data provider request failed."


class AuthenticationError(AppError):
    status_code = 401
    code = "unauthorized"
    message = "Authentication is required."
