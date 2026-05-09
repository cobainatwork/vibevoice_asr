"""
Centralized error code catalog.

Used by both /api/admin/* and /api/v1/*. The same code is used in:
- HTTP response bodies: {"code": "...", "detail": "..."}
- WebSocket error frames: {"type": "error", "code": "...", "detail": "..."}
- Webhook callbacks: {"event": "transcription.failed", "error_code": "..."}

See SPEC.md §17.3 (error code catalog).
"""
from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    # === Authentication / Authorization ===
    INVALID_API_KEY = "invalid_api_key"
    MISSING_AUTH = "missing_auth"

    # === Rate limiting / quota ===
    QUOTA_EXCEEDED = "quota_exceeded"

    # === Idempotency ===
    IDEMPOTENCY_REPLAY = "idempotency_replay"

    # === Request validation ===
    INVALID_METADATA = "invalid_metadata"
    INVALID_HOTWORDS = "invalid_hotwords"
    INVALID_PROJECT = "invalid_project"

    # === Audio errors ===
    AUDIO_TOO_LONG = "audio_too_long"
    AUDIO_TOO_SHORT = "audio_too_short"
    AUDIO_UNREADABLE = "audio_unreadable"
    UNSUPPORTED_FORMAT = "unsupported_format"

    # === Upload errors ===
    UPLOAD_TOO_LARGE = "upload_too_large"
    UPLOAD_TIMEOUT = "upload_timeout"
    UPLOAD_INTERRUPTED = "upload_interrupted"

    # === Service availability ===
    VLLM_UNAVAILABLE = "vllm_unavailable"
    REDIS_UNAVAILABLE = "redis_unavailable"

    # === Job errors ===
    JOB_NOT_FOUND = "job_not_found"
    JOB_CANCELLED = "job_cancelled"
    JOB_FAILED = "job_failed"

    # === Inference errors ===
    REPETITION_LOOP = "repetition_loop"  # auto-recovery exhausted
    PARSE_FAILED = "parse_failed"        # could not parse vLLM output

    # === Training errors ===
    TRAINING_OOM = "training_oom"
    TRAINING_FAILED = "training_failed"
    DATASET_EMPTY = "dataset_empty"

    # === Format errors (dataset import) ===
    IMPORT_MISSING_COLUMNS = "import_missing_columns"
    IMPORT_INVALID_TIME = "import_invalid_time"
    IMPORT_PARSE_FAILED = "import_parse_failed"

    # === Generic ===
    INTERNAL_ERROR = "internal_error"


# HTTP status code mapping
HTTP_STATUS_FOR_CODE: dict[ErrorCode, int] = {
    ErrorCode.INVALID_API_KEY: 401,
    ErrorCode.MISSING_AUTH: 401,
    ErrorCode.QUOTA_EXCEEDED: 429,
    ErrorCode.IDEMPOTENCY_REPLAY: 409,
    ErrorCode.INVALID_METADATA: 400,
    ErrorCode.INVALID_HOTWORDS: 400,
    ErrorCode.INVALID_PROJECT: 400,
    ErrorCode.AUDIO_TOO_LONG: 400,
    ErrorCode.AUDIO_TOO_SHORT: 400,
    ErrorCode.AUDIO_UNREADABLE: 400,
    ErrorCode.UNSUPPORTED_FORMAT: 400,
    ErrorCode.UPLOAD_TOO_LARGE: 413,
    ErrorCode.UPLOAD_TIMEOUT: 408,
    ErrorCode.UPLOAD_INTERRUPTED: 400,
    ErrorCode.VLLM_UNAVAILABLE: 503,
    ErrorCode.REDIS_UNAVAILABLE: 503,
    ErrorCode.JOB_NOT_FOUND: 404,
    ErrorCode.JOB_CANCELLED: 410,
    ErrorCode.JOB_FAILED: 500,
    ErrorCode.REPETITION_LOOP: 500,
    ErrorCode.PARSE_FAILED: 500,
    ErrorCode.TRAINING_OOM: 500,
    ErrorCode.TRAINING_FAILED: 500,
    ErrorCode.DATASET_EMPTY: 400,
    ErrorCode.IMPORT_MISSING_COLUMNS: 400,
    ErrorCode.IMPORT_INVALID_TIME: 400,
    ErrorCode.IMPORT_PARSE_FAILED: 400,
    ErrorCode.INTERNAL_ERROR: 500,
}


class AppError(Exception):
    """Application-level error carrying an ErrorCode and detail message."""

    def __init__(self, code: ErrorCode, detail: str = "", **extra):
        self.code = code
        self.detail = detail or code.value
        self.extra = extra
        super().__init__(f"{code.value}: {detail}")

    @property
    def http_status(self) -> int:
        return HTTP_STATUS_FOR_CODE.get(self.code, 500)

    def to_dict(self) -> dict:
        d = {"code": self.code.value, "detail": self.detail}
        d.update(self.extra)
        return d
