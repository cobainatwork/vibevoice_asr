"""
ASR pre-processing orchestration: denoise (optional).

職責跟 splitter 分離 — splitter 不知道輸入是否 denoised、只接 mp3 path。
這層做 denoise + 寫 temp mp3 file、回 caller 新 path。

Caller (job_runner) 責任清理 temp file。
"""
from __future__ import annotations

import logging
import math
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.constants import (
    ASR_AUDIO_CHANNELS,
    ASR_AUDIO_MP3_QUALITY,
    ASR_AUDIO_SAMPLE_RATE_HZ,
)
from app.errors import AppError, ErrorCode
from app.services.denoiser import denoise

logger = logging.getLogger(__name__)


def maybe_denoise(
    input_path: Path,
    *,
    denoise_enabled: bool,
    denoise_model: str = "gtcrn",
) -> tuple[Path, bool]:
    """若 enabled，denoise 整段音檔到 temp mp3、回 (新 path, True)。

    Disabled 時直接回 (input_path, False)。
    Caller 必須在 job 結束後刪除 temp file（若 True）。
    """
    if not denoise_enabled:
        return input_path, False

    # 1. ffmpeg → 16kHz mono PCM int16 → numpy float32
    waveform, sr = _load_pcm(input_path)

    # 2. denoise (純 noisereduce，不需要 model_name)
    logger.info(
        "denoiser: starting on %s (%.1fs audio)",
        input_path.name,
        len(waveform) / sr,
    )
    cleaned = denoise(waveform, sr)
    logger.info("denoiser: finished")

    # 3. 寫 cleaned waveform 回 temp mp3 (同 ASR 標準格式 16kHz mono)
    temp_path = _write_denoised_mp3(cleaned, sr)
    return temp_path, True


def cleanup_denoised(temp_path: Path) -> None:
    """刪除 temp denoised file (safe — 失敗不 raise)。"""
    try:
        if temp_path.exists():
            temp_path.unlink()
    except OSError as e:
        logger.warning(
            "cleanup denoised temp file failed: %s (%s)", temp_path, e
        )


def maybe_normalize_format(input_path: Path) -> tuple[Path, bool]:
    """確保音檔是 16kHz mono mp3、否則 ffmpeg 強制轉。

    vibevoice 訓練資料為 16kHz mono、直接送 8kHz 電話音檔(QC 場景常見)
    會讓模型「幻想」內容(辨識結果跟原音完全無關)。
    無論 audio 長短、ASR 推論前都跑這個 normalize stage。

    回 (新 path, True) 若有轉、(原 path, False) 若已是 16kHz mono。
    Caller 必須在 job 結束後刪除 temp file(若 True)。
    """
    sr, channels = _probe_audio_format(input_path)
    target_sr = ASR_AUDIO_SAMPLE_RATE_HZ
    target_ch = ASR_AUDIO_CHANNELS

    if sr == target_sr and channels == target_ch:
        return input_path, False

    settings = get_settings()
    fd, temp_str = tempfile.mkstemp(
        suffix=".mp3", prefix="normalized_", dir=str(settings.upload_dir),
    )
    os.close(fd)
    temp_path = Path(temp_str)

    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(input_path),
        "-vn",
        "-ar", str(target_sr),
        "-ac", str(target_ch),
        "-c:a", "libmp3lame",
        "-q:a", str(ASR_AUDIO_MP3_QUALITY),
        str(temp_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=600)
    except subprocess.CalledProcessError as e:
        temp_path.unlink(missing_ok=True)
        stderr = e.stderr.decode("utf-8", errors="replace")[-500:] if e.stderr else ""
        raise AppError(
            ErrorCode.AUDIO_UNREADABLE,
            f"ffmpeg normalize failed: {stderr}",
        ) from e

    logger.info(
        "format: normalized %s (%dHz/%dch → %dHz/%dch)",
        input_path.name, sr, channels, target_sr, target_ch,
    )
    return temp_path, True


def cleanup_normalized(temp_path: Path) -> None:
    """刪除 temp normalized file (safe — 失敗不 raise)。"""
    try:
        if temp_path.exists():
            temp_path.unlink()
    except OSError as e:
        logger.warning(
            "cleanup normalized temp file failed: %s (%s)", temp_path, e
        )


def _probe_audio_format(input_path: Path) -> tuple[int, int]:
    """ffprobe 拿 (sample_rate, channels)。"""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=sample_rate,channels",
        "-of", "default=noprint_wrappers=1:nokey=0",
        str(input_path),
    ]
    out = subprocess.check_output(cmd, timeout=30).decode("utf-8").strip()
    sr = 0
    ch = 0
    for line in out.splitlines():
        if line.startswith("sample_rate="):
            sr = int(line.split("=", 1)[1])
        elif line.startswith("channels="):
            ch = int(line.split("=", 1)[1])
    return sr, ch


def maybe_adjust_speed(
    input_path: Path,
    *,
    playback_speed: float,
) -> tuple[Path, bool]:
    """若 playback_speed 不為 1.0，用 ffmpeg atempo 調速到 temp mp3、回 (新 path, True)。

    speed ≈ 1.0（abs_tol=1e-3）視為 no-op，直接回 (input_path, False)。
    Caller 必須在 job 結束後刪除 temp file（若 True）。

    Raises AppError(INTERNAL_ERROR) 若 playback_speed 超出 [0.5, 2.0] 範圍。
    """
    if math.isclose(playback_speed, 1.0, abs_tol=1e-3):
        return input_path, False

    if not (0.5 <= playback_speed <= 2.0):
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            f"playback_speed {playback_speed} out of range [0.5, 2.0]",
        )

    settings = get_settings()
    fd, temp_str = tempfile.mkstemp(
        suffix=".mp3", prefix="speed_", dir=str(settings.upload_dir),
    )
    os.close(fd)
    temp_path = Path(temp_str)

    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(input_path),
        "-filter:a", f"atempo={playback_speed}",
        str(temp_path),
    ]
    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            timeout=600,
        )
    except subprocess.CalledProcessError as e:
        temp_path.unlink(missing_ok=True)
        stderr = e.stderr.decode("utf-8", errors="replace")[-500:] if e.stderr else ""
        raise AppError(
            ErrorCode.AUDIO_UNREADABLE,
            f"ffmpeg atempo failed: {stderr}",
        ) from e

    logger.info(
        "speed: adjusted %s → %s @ %s×",
        input_path.name, temp_path.name, playback_speed,
    )
    return temp_path, True


def cleanup_adjusted_speed(temp_path: Path) -> None:
    """刪除 temp speed-adjusted file (safe — 失敗不 raise)。"""
    try:
        if temp_path.exists():
            temp_path.unlink()
    except OSError as e:
        logger.warning(
            "cleanup speed temp file failed: %s (%s)", temp_path, e
        )


# === Helpers ===


def _load_pcm(input_path: Path) -> tuple[np.ndarray, int]:
    """ffmpeg → PCM int16 → numpy float32。

    獨立寫在此模組，不 import audio_splitter private function。
    """
    sr = ASR_AUDIO_SAMPLE_RATE_HZ
    cmd = [
        "ffmpeg", "-v", "error",
        "-i", str(input_path),
        "-vn", "-ar", str(sr), "-ac", "1", "-f", "s16le", "-",
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, timeout=600)
    pcm = np.frombuffer(result.stdout, dtype=np.int16)
    return pcm.astype(np.float32) / 32768.0, sr


def _write_denoised_mp3(waveform: np.ndarray, sr: int) -> Path:
    """numpy float32 → PCM int16 → ffmpeg → mp3 temp file。"""
    settings = get_settings()
    fd, temp_str = tempfile.mkstemp(
        suffix=".mp3", prefix="denoised_", dir=str(settings.upload_dir),
    )
    # close fd immediately; ffmpeg will write
    os.close(fd)
    temp_path = Path(temp_str)

    pcm_int16 = np.clip(waveform * 32768.0, -32768, 32767).astype(np.int16)

    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "s16le", "-ar", str(sr), "-ac", str(ASR_AUDIO_CHANNELS),
        "-i", "-",  # stdin
        "-c:a", "libmp3lame", "-q:a", str(ASR_AUDIO_MP3_QUALITY),
        str(temp_path),
    ]
    try:
        subprocess.run(
            cmd,
            input=pcm_int16.tobytes(),
            check=True,
            capture_output=True,
            timeout=300,
        )
    except subprocess.CalledProcessError as e:
        temp_path.unlink(missing_ok=True)
        stderr = e.stderr.decode("utf-8", errors="replace")[-500:] if e.stderr else ""
        raise AppError(
            ErrorCode.AUDIO_UNREADABLE,
            f"ffmpeg denoise encode failed: {stderr}",
        ) from e
    return temp_path
