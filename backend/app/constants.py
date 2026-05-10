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
# ASR audio extraction format
# vLLM 標準輸入：16kHz mono MP3。所有 ffmpeg 抽 audio / 切段共用同一規格、
# 集中於此避免 audio.py 跟 audio_splitter.py 各維護一份漂移。
# ============================================================

ASR_AUDIO_SAMPLE_RATE_HZ = 16000
ASR_AUDIO_CHANNELS = 1
ASR_AUDIO_MP3_QUALITY = 4  # libmp3lame -q:a (4 ≈ 128 kbps VBR)


# ============================================================
# Repetition loop detection
# Source: vendor/VibeVoice/vllm_plugin/tests/test_api_auto_recover.py
# ============================================================

# 之前 200 / 10 / 3 對中文商業對話過於敏感：「就是」「我們」「品項」「易發票」
# 短時間密集重複會誤判 repetition loop，導致長音檔每段都 partial 漏大量內容。
# 放寬到 300 / 15 / 4：要更長重複片段、更多次出現才算。真正的 vLLM 無限生成
# 同 phrase 仍能 catch（loop 通常一觸發就大量重複，window 拉長仍超標）；
# 只是過濾掉中文自然重複的 false positive。
REPETITION_WINDOW_CHARS = 300
REPETITION_MIN_SUBSTRING_LEN = 15
REPETITION_MIN_OCCURRENCES = 4
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
# Dataset format catalogs (M3.5)
# ============================================================
# 匯入：可上傳的標註檔格式（spec §1.2 已排除 csv / vtt）
# 匯出：可下載的格式（routes/admin/datasets.py 與 dataset_exporter 共用）
# 範本：可下載的範本檔格式（與 LABEL_FORMATS 相同 — 範本與匯入是雙向對稱）
DATASET_LABEL_FORMATS: tuple[str, ...] = ("json", "xlsx", "srt", "txt")
DATASET_EXPORT_FORMATS: tuple[str, ...] = ("json", "srt", "xlsx")
DATASET_TEMPLATE_FORMATS: tuple[str, ...] = DATASET_LABEL_FORMATS


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
