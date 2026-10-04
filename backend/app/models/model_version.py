"""Model registry and training run bookkeeping."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import ModelStatus, TrainingStatus


class ModelVersion(Base):
    """One immutable trained model artifact.

    The `status` column encodes the promotion lifecycle
    (candidate -> validated -> active -> archived) and is the single source of
    truth for which model the API serves.
    """

    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    status: Mapped[ModelStatus] = mapped_column(
        Enum(ModelStatus, name="model_status"),
        default=ModelStatus.CANDIDATE,
        nullable=False,
        index=True,
    )
    artifact_path: Mapped[str] = mapped_column(String(512), nullable=False)
    framework_version: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    hyperparameters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    features: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    training_data_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    training_data_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    training_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("training_runs.id", ondelete="SET NULL"), index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TrainingRun(Base):
    """One execution of the training pipeline, successful or not."""

    __tablename__ = "training_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    status: Mapped[TrainingStatus] = mapped_column(
        Enum(TrainingStatus, name="training_status"),
        default=TrainingStatus.PENDING,
        nullable=False,
        index=True,
    )
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    dataset_path: Mapped[str | None] = mapped_column(String(512))
    dataset_rows: Mapped[int | None] = mapped_column(Integer)
    candidate_results: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    best_model_name: Mapped[str | None] = mapped_column(String(128))
    best_metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    baseline_metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_model_version: Mapped[str | None] = mapped_column(String(32))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    is_reproducible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
