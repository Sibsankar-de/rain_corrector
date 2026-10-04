"""Application configuration loaded from environment / .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Rain Corrector"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    api_version: str = "v1"

    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    log_level: str = "INFO"
    log_format: Literal["text", "json"] = "text"

    database_url: str = Field(
        default="postgresql+psycopg://rain:rain_dev_password@localhost:55432/rain_corrector"
    )
    async_database_url: str = Field(
        default="postgresql+asyncpg://rain:rain_dev_password@localhost:55432/rain_corrector"
    )
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False

    cors_origins: str = "http://localhost:3000"
    secret_key: str = "change-me-before-deploying"
    api_key_header: str = "X-API-Key"
    enable_api_key_auth: bool = False

    model_artifact_path: Path = REPO_ROOT / "ml" / "artifacts"
    model_version: str | None = None
    model_load_on_startup: bool = True
    model_inference_timeout_seconds: float = 10.0

    ml_random_seed: int = 42
    ml_training_data_path: Path = REPO_ROOT / "data" / "processed"
    ml_raw_data_path: Path = REPO_ROOT / "data" / "raw"
    ml_artifact_output_path: Path = REPO_ROOT / "ml" / "artifacts"

    data_provider: str = "local_csv"
    open_meteo_base_url: str = "https://api.open-meteo.com/v1/forecast"
    open_meteo_timeout_seconds: float = 20.0
    enable_external_ingestion: bool = False
    default_ingest_latitude: float = 19.2183
    default_ingest_longitude: float = 72.9781

    verification_grace_period_hours: int = 6
    retraining_min_interval_hours: int = 168
    default_forecast_horizon_hours: int = 24
    default_promotion_policy: str = "auto_promote_if_better"

    @field_validator(
        "ml_training_data_path",
        "ml_raw_data_path",
        "ml_artifact_output_path",
        "model_artifact_path",
        mode="before",
    )
    @classmethod
    def _resolve_path(cls, value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else (REPO_ROOT / path).resolve()

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def sync_database_url(self) -> str:
        """Async driver swapped for the sync driver used by Alembic and ML tooling."""
        return self.async_database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
