"""
Audio utilities: ffprobe duration, MIME guessing, video → audio extraction.

See SPEC.md §6.2 (MIME map).
M2 milestone（extract_audio_to_mp3 為 M3.5 後修補：上游 vLLM processor 對
MP4 等 video container 解碼不穩定，backend 端預先 demux 規避）。
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from app.constants import VIDEO_EXTENSIONS, guess_mime
from app.errors import AppError, ErrorCode

# 預設抽音規格：16kHz mono MP3（ASR 標準輸入；MP3 已實證 vLLM 端讀得下）
EXTRACT_SAMPLE_RATE = 16000
EXTRACT_CHANNELS = 1
EXTRACT_QUALITY = 4  # libmp3lame -q:a 4 ≈ 128 kbps VBR
EXTRACT_TIMEOUT_SEC = 300


def get_duration_sec(path: Path) -> float:
    """ffprobe wrapper. Raises AppError(AUDIO_UNREADABLE) on failure."""
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            stderr=subprocess.STDOUT,
            timeout=30,
        )
        return float(out.decode().strip())
    except Exception as e:
        raise AppError(ErrorCode.AUDIO_UNREADABLE, f"ffprobe failed: {e}") from e


def is_video_file(filename: str) -> bool:
    return os.path.splitext(filename)[1].lower() in VIDEO_EXTENSIONS


def get_mime(filename: str) -> str:
    return guess_mime(filename)


def extract_audio_to_mp3(input_path: Path) -> bytes:
    """從 video container（MP4 / MOV / WebM 等）抽 audio stream → 16kHz mono MP3 bytes。

    為何抽 audio：上游 VibeVoice processor 對 MP4 容器 demux 不穩定，會出現
    `zero-size array to reduction operation maximum` 內部錯誤。Backend 預先
    抽乾淨 MP3 規避，呼叫端把 mime 改 `audio/mpeg` 後續走標準音訊路徑。

    上層應先判斷 is_video_file() 再呼叫，避免對純音訊檔做不必要的轉碼。
    """
    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", str(input_path),
                "-vn",                      # 丟視訊軌
                "-ar", str(EXTRACT_SAMPLE_RATE),
                "-ac", str(EXTRACT_CHANNELS),
                "-f", "mp3",
                "-c:a", "libmp3lame",
                "-q:a", str(EXTRACT_QUALITY),
                "pipe:1",
            ],
            input=b"",
            capture_output=True,
            timeout=EXTRACT_TIMEOUT_SEC,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise AppError(
            ErrorCode.AUDIO_UNREADABLE,
            f"ffmpeg timeout after {EXTRACT_TIMEOUT_SEC}s: {input_path.name}",
        ) from e
    except FileNotFoundError as e:
        raise AppError(
            ErrorCode.AUDIO_UNREADABLE, f"ffmpeg binary missing: {e}"
        ) from e

    if proc.returncode != 0 or not proc.stdout:
        stderr_tail = proc.stderr.decode("utf-8", errors="replace")[-500:] if proc.stderr else ""
        raise AppError(
            ErrorCode.AUDIO_UNREADABLE,
            f"ffmpeg extract failed (rc={proc.returncode}): {stderr_tail}",
        )
    return proc.stdout
