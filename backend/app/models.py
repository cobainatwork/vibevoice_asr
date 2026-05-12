"""
SQLAlchemy ORM models.

See SPEC.md §7.2 for schema definition. Keep in sync with migrations/versions/.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# ============================================================
# Enums
# ============================================================


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobSource(str, enum.Enum):
    ADMIN_UPLOAD = "admin_upload"
    YOUTUBE_FETCH = "youtube_fetch"
    V1_API_ASYNC = "v1_api_async"
    V1_API_SYNC = "v1_api_sync"
    V1_API_WS = "v1_api_ws"


class TrainingStatus(str, enum.Enum):
    PENDING = "pending"
    PREPARING = "preparing"
    TRAINING = "training"
    MERGING = "merging"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModelType(str, enum.Enum):
    BASE = "base"
    MERGED = "merged"
    LORA = "lora"


class DatasetSource(str, enum.Enum):
    UPLOADED = "uploaded"
    FROM_TRANSCRIPTION = "from_transcription"
    IMPORTED_XLSX = "imported_xlsx"
    IMPORTED_CSV = "imported_csv"
    IMPORTED_SRT = "imported_srt"
    IMPORTED_VTT = "imported_vtt"
    IMPORTED_TXT = "imported_txt"
    IMPORTED_JSON = "imported_json"


class WebhookDeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    GIVEN_UP = "given_up"


# ============================================================
# Tables
# ============================================================


def _uuid() -> str:
    return str(uuid.uuid4())


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    hotwords: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    active_model_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL")
    )
    webhook_url: Mapped[str | None] = mapped_column(String(500))
    webhook_secret: Mapped[str | None] = mapped_column(String(128))
    denoise_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default=text("0"),
    )
    playback_speed: Mapped[float] = mapped_column(
        Float, default=1.0, nullable=False, server_default=text("1.0"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    key_prefix: Mapped[str] = mapped_column(String(8), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)


class IntegrationCall(Base):
    __tablename__ = "integration_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id", ondelete="SET NULL"))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    endpoint: Mapped[str] = mapped_column(String(100), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    source_ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(200))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    source: Mapped[JobSource] = mapped_column(SAEnum(JobSource), nullable=False)
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id", ondelete="SET NULL"))
    idempotency_key: Mapped[str | None] = mapped_column(String(100), index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    audio_path: Mapped[str] = mapped_column(String(500), nullable=False)
    duration_sec: Mapped[float | None] = mapped_column(Float)
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus), default=JobStatus.PENDING, nullable=False
    )
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    chunks_total: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    chunks_done: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    segments: Mapped[list[dict] | None] = mapped_column(JSON)
    raw_text: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    used_hotwords: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    used_model_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL")
    )
    callback_url: Mapped[str | None] = mapped_column(String(500))
    metadata_extra: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    source_url: Mapped[str | None] = mapped_column(String(500))
    reference_subtitles: Mapped[list[dict] | None] = mapped_column(JSON)
    reference_subtitle_lang: Mapped[str | None] = mapped_column(String(16))
    is_corrected: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default=text("0"),
    )

    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key", name="uq_job_idempotency"),
    )


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[WebhookDeliveryStatus] = mapped_column(
        SAEnum(WebhookDeliveryStatus), default=WebhookDeliveryStatus.PENDING, nullable=False
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    last_response_code: Mapped[int | None] = mapped_column(Integer)
    last_response_body: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)


class DatasetItem(Base):
    __tablename__ = "dataset_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    audio_path: Mapped[str] = mapped_column(String(500), nullable=False)
    label: Mapped[dict] = mapped_column(JSON, nullable=False)
    duration_sec: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[DatasetSource] = mapped_column(SAEnum(DatasetSource), nullable=False)
    source_job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class TrainingRun(Base):
    __tablename__ = "training_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    status: Mapped[TrainingStatus] = mapped_column(
        SAEnum(TrainingStatus), default=TrainingStatus.PENDING, nullable=False
    )
    hyperparams: Mapped[dict] = mapped_column(JSON, nullable=False)
    dataset_item_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    output_path: Mapped[str | None] = mapped_column(String(500))
    merged_path: Mapped[str | None] = mapped_column(String(500))
    log_path: Mapped[str] = mapped_column(String(500), nullable=False)
    metrics: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )  # null = global base
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[ModelType] = mapped_column(SAEnum(ModelType), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    training_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("training_runs.id", ondelete="SET NULL")
    )
    size_gb: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
