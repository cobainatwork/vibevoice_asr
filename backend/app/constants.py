"""
Centralized constants. All values referenced by ≥2 modules go here.

See SPEC.md §6.2 (prompt template), §6.3 (key mapping), and §17.3 (WS protocol).
"""
from __future__ import annotations

# ============================================================
# vLLM prompt template
# Source: vendor/VibeVoice/vibevoice/processor/vibevoice_asr_processor.py:340-370
# ============================================================

SYSTEM_PROMPT = (
    "You are a helpful assistant that transcribes audio input into text output in JSON format."
)

SHOW_KEYS = ["Start time", "End time", "Speaker ID", "Content"]


def build_user_prompt(duration_sec: float, hotwords: list[str] | None = None) -> str:
    """Build the user prompt text following the upstream training format."""
    keys_str = ", ".join(SHOW_KEYS)
    if hotwords:
        ctx = ",".join(hotwords)
        return (
            f"This is a {duration_sec:.2f} seconds audio, with extra info: {ctx}\n\n"
            f"Please transcribe it with these keys: {keys_str}"
        )
    return (
        f"This is a {duration_sec:.2f} seconds audio, please transcribe it with these keys: "
        f"{keys_str}"
    )


# ============================================================
# Output key normalization
# Source: vendor/VibeVoice/vibevoice/processor/vibevoice_asr_processor.py:541-549
# ============================================================

OUTPUT_KEY_MAPPING: dict[str, str] = {
    "Start time": "start_time",
    "Start": "start_time",
    "End time": "end_time",
    "End": "end_time",
    "Speaker ID": "speaker_id",
    "Speaker": "speaker_id",
    "Content": "text",
}


# ============================================================
# MIME type mapping (file extension → MIME)
# Source: vendor/VibeVoice/vllm_plugin/tests/test_api.py:32-44
# ============================================================

MIME_MAP: dict[str, str] = {
    ".wav":  "audio/wav",
    ".mp3":  "audio/mpeg",
    ".m4a":  "audio/mp4",
    ".mp4":  "video/mp4",
    ".m4v":  "video/mp4",
    ".mov":  "video/mp4",
    ".webm": "video/mp4",
    ".flac": "audio/flac",
    ".ogg":  "audio/ogg",
    ".opus": "audio/ogg",
}

VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".webm", ".avi", ".mkv"}


def guess_mime(filename: str) -> str:
    """Guess MIME from filename extension."""
    import os
    ext = os.path.splitext(filename)[1].lower()
    return MIME_MAP.get(ext, "application/octet-stream")


# ============================================================
# Repetition loop detection
# Source: vendor/VibeVoice/vllm_plugin/tests/test_api_auto_recover.py
# ============================================================

REPETITION_WINDOW_CHARS = 200
REPETITION_MIN_SUBSTRING_LEN = 10
REPETITION_MIN_OCCURRENCES = 3
RETRY_TEMPERATURES = [0.0, 0.2, 0.3, 0.4]
MAX_VLLM_RETRIES = 3


# ============================================================
# WebSocket protocol message types (v1 API)
# See SPEC.md §17.3
# ============================================================

class WsClientMsg:
    START = "start"
    EOF = "eof"
    CANCEL = "cancel"


class WsServerMsg:
    READY = "ready"
    ACK = "ack"
    PROGRESS = "progress"
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


# Close codes (RFC 6455 + custom)
WS_CLOSE_NORMAL = 1000
WS_CLOSE_AUTH_FAILED = 4001  # custom
WS_CLOSE_UPLOAD_TIMEOUT = 4002
WS_CLOSE_BAD_REQUEST = 4003
WS_CLOSE_INTERNAL_ERROR = 4500


# ============================================================
# Webhook signing
# See SPEC.md §17.6
# ============================================================

WEBHOOK_SIG_HEADER = "X-Webhook-Signature"
WEBHOOK_TS_HEADER = "X-Webhook-Timestamp"
WEBHOOK_EVENT_HEADER = "X-Webhook-Event"
WEBHOOK_DELIVERY_HEADER = "X-Webhook-Delivery"
WEBHOOK_TIMESTAMP_TOLERANCE_SEC = 300

WEBHOOK_RETRY_DELAYS_SEC = [30, 300, 1800, 7200, 21600, 43200]  # 7 attempts total


# ============================================================
# Speaker indexing convention
# ============================================================
# Inference output:  "1", "2", ... (1-indexed, str)
# Training data:     0, 1, ... (0-indexed, int)
# Internal canonical: 1-indexed, int (matches user-facing display)
#
# Conversion happens at:
#   - parser.py: vLLM output → internal (str→int, no shift since output is already 1-indexed)
#   - dataset_importer.py: training JSON → internal (0-indexed → 1-indexed)
#   - dataset exporter: internal → training JSON (1-indexed → 0-indexed)
