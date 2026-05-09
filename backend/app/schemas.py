"""
Pydantic schemas for request/response bodies.

Convention:
- *In:    request body (POST/PUT)
- *Out:   response body
- *Patch: partial update (PUT supporting None for not-changed)

See SPEC.md §7.3 (admin) and §17 (v1) for endpoint specs.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models import (
    DatasetSource,
    JobSource,
    JobStatus,
    ModelType,
    TrainingStatus,
    WebhookDeliveryStatus,
)


# ============================================================
# Common
# ============================================================


class Segment(BaseModel):
    """Internal canonical segment format (1-indexed speaker, float seconds)."""
    start_time: float
    end_time: float
    speaker_id: int
    text: str


class ErrorOut(BaseModel):
    code: str
    detail: str


# ============================================================
# Project
# ============================================================


class ProjectIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    hotwords: list[str] = Field(default_factory=list)
    webhook_url: str | None = None


class ProjectPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    hotwords: list[str] | None = None
    webhook_url: str | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str | None
    hotwords: list[str]
    active_model_id: int | None
    webhook_url: str | None
    created_at: datetime
    updated_at: datetime


# ============================================================
# API Key
# ============================================================


class ApiKeyIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    expires_at: datetime | None = None


class ApiKeyOut(BaseModel):
    """Without plain key. Use ApiKeyCreatedOut for creation response."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    name: str
    key_prefix: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None


class ApiKeyCreatedOut(ApiKeyOut):
    """Returned ONLY on creation/rotation (contains plain key)."""
    key: str


# ============================================================
# Webhook
# ============================================================


class WebhookSettingsIn(BaseModel):
    url: HttpUrl
    rotate_secret: bool = False


class WebhookSettingsOut(BaseModel):
    url: str | None
    secret_prefix: str | None = None  # 前 8 碼，full secret 不回


class WebhookSecretCreatedOut(BaseModel):
    secret: str   # full secret，僅在 rotate 時回


class WebhookTestResult(BaseModel):
    success: bool
    response_code: int | None
    response_body: str | None
    elapsed_ms: int
    error: str | None = None


# ============================================================
# Job
# ============================================================


class TranscribeIn(BaseModel):
    """For sync POST /api/v1/transcribe/sync. Files come via multipart."""
    metadata: dict[str, Any] | None = None


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: int
    source: JobSource
    filename: str
    duration_sec: float | None
    status: JobStatus
    progress: float
    chunks_total: int
    chunks_done: int
    segments: list[dict] | None
    raw_text: str | None
    error: str | None
    used_hotwords: list[str]
    used_model_id: int | None
    callback_url: str | None
    metadata_extra: dict | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobCreatedOut(BaseModel):
    job_id: str


class SegmentsPatchIn(BaseModel):
    segments: list[Segment]


# ============================================================
# Dataset
# ============================================================


class DatasetItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    audio_path: str
    label: dict
    duration_sec: float
    source: DatasetSource
    source_job_id: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class DatasetItemPatch(BaseModel):
    label: dict | None = None
    notes: str | None = None


class DatasetFromJobIn(BaseModel):
    notes: str | None = None


# ============================================================
# Training
# ============================================================


class TrainingHyperparams(BaseModel):
    """Training hyperparams. Defaults match upstream lora_finetune.py."""
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    lr: float = 1e-4
    epochs: int = 3
    batch_size: int = 1
    grad_accum: int = 4
    warmup_ratio: float = 0.1
    weight_decay: float = 0.01
    max_audio_length: float | None = None


class TrainingRunIn(BaseModel):
    project_id: int
    dataset_item_ids: list[int] = Field(..., min_length=1)
    hyperparams: TrainingHyperparams = Field(default_factory=TrainingHyperparams)


class TrainingRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: int
    status: TrainingStatus
    hyperparams: dict
    dataset_item_ids: list[int]
    output_path: str | None
    merged_path: str | None
    log_path: str
    metrics: dict | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


# ============================================================
# Model Version
# ============================================================


class ModelVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int | None
    name: str
    type: ModelType
    path: str
    training_run_id: str | None
    size_gb: float | None
    created_at: datetime


class SetActiveModelIn(BaseModel):
    model_version_id: int | None  # null = revert to base


# ============================================================
# System / Status
# ============================================================


class HealthOut(BaseModel):
    ok: bool
    vllm_status: str
    redis_status: str
    db_status: str


class VllmStatusOut(BaseModel):
    status: str  # ready | loading | down
    model: str | None
    uptime_sec: int | None


class GpuInfo(BaseModel):
    index: int
    name: str
    memory_used_mb: int
    memory_total_mb: int
    utilization: int
    temperature: int


class QueueInfo(BaseModel):
    pending: int
    running: int
    workers: int
    oldest_age_sec: int


# ============================================================
# v1 API (external)
# ============================================================


class V1JobStatusOut(BaseModel):
    """Stable schema for QC integration. DO NOT add/remove fields without API version bump."""
    job_id: str
    status: str       # pending | queued | running | done | failed | cancelled
    progress: float
    duration_sec: float | None
    created_at: str   # ISO 8601
    started_at: str | None
    metadata: dict | None


class V1JobResultOut(BaseModel):
    """Stable schema. DO NOT modify."""
    job_id: str
    status: str
    duration_sec: float
    elapsed_sec: float
    model: str
    hotwords_used: list[str]
    segments: list[Segment]
    warnings: list[str]
    metadata: dict | None


class V1SyncResultOut(V1JobResultOut):
    pass


# ============================================================
# Integration Call (audit log)
# ============================================================


class IntegrationCallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    api_key_id: int | None
    project_id: int
    job_id: str | None
    endpoint: str
    method: str
    status_code: int
    duration_ms: int
    source_ip: str | None
    user_agent: str | None
    error: str | None
    created_at: datetime
