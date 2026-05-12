"""
Long-audio splitter & merger（silence-based 切點版）。

When audio > AUTO_SPLIT_THRESHOLD_SEC, use silence detection (vendored
audio-slicer) to find natural句邊界, then accumulate adjacent silence-bounded
segments into chunks ≤ chunk_duration_sec. 每 chunk 在 silence 處切斷、無
overlap、merge 階段不需要文字 dedup。

Replaces M5 minimal viable implementation（固定時間切 + overlap + SequenceMatcher dedup）。

See SPEC.md §6.4 and docs/superpowers/specs/2026-05-12-silence-slicer-design.md。
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.constants import (
    ASR_AUDIO_CHANNELS,
    ASR_AUDIO_MP3_QUALITY,
    ASR_AUDIO_SAMPLE_RATE_HZ,
)
from app.errors import AppError, ErrorCode
from app.utils.silence_slicer import SilenceSlicer

logger = logging.getLogger(__name__)


# splitter 內 ffmpeg subprocess 的超時（單 chunk 最多 600s 處理時間）。
SPLIT_TIMEOUT_SEC = 600


@dataclass
class Chunk:
    path: Path
    start_offset_sec: float  # absolute time in original audio
    end_offset_sec: float
    is_split: bool


def get_duration_sec(path: Path) -> float:
    """ffprobe wrapper. Raises CalledProcessError on failure."""
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        stderr=subprocess.STDOUT,
    )
    return float(out.decode().strip())


def split_long_audio(
    input_path: Path,
    output_dir: Path,
    max_chunk_sec: int | None = None,
    threshold_sec: int | None = None,
) -> list[Chunk]:
    """切長音檔為多段 chunk file（silence-based 切點）。

    duration <= threshold_sec → 回單 chunk（path 指原檔、is_split=False）
    duration >  threshold_sec → ffmpeg 切多 chunk 寫到 output_dir/chunk_NNN.mp3,
                                切點來自 SilenceSlicer 找到的 silence-bounded ranges,
                                累計到 max_chunk_sec 為上限。

    沒 silence 切點時（極端罕見、整段連續講話 / 純樂器）→ fallback 固定時間切。
    """
    settings = get_settings()
    max_chunk_sec_val = max_chunk_sec or settings.split_chunk_duration_sec
    threshold_sec_val = threshold_sec or settings.auto_split_threshold_sec

    duration = get_duration_sec(input_path)
    if duration <= threshold_sec_val:
        return [Chunk(
            path=input_path,
            start_offset_sec=0.0,
            end_offset_sec=duration,
            is_split=False,
        )]

    # 1. ffmpeg → 16kHz mono PCM → numpy
    waveform, sr = _load_pcm_mono_16k(input_path)

    # 2. silence slicer 找切點
    slicer = SilenceSlicer(
        sr=sr,
        threshold=settings.silence_threshold_db,
        min_length=settings.silence_min_length_ms,
        min_interval=settings.silence_min_interval_ms,
        hop_size=settings.silence_hop_size_ms,
        max_sil_kept=settings.silence_max_kept_ms,
    )
    sample_ranges = slicer.slice_ranges(waveform)

    if not sample_ranges:
        return _fallback_fixed_split(
            input_path, output_dir, duration, float(max_chunk_sec_val),
        )

    # 3. 累計成 chunk
    chunk_time_ranges = _accumulate_to_chunks(
        sample_ranges, sr, float(max_chunk_sec_val),
    )

    # 4. ffmpeg 切實體 mp3
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[Chunk] = []
    for i, (start_sec, end_sec) in enumerate(chunk_time_ranges):
        chunk_path = output_dir / f"chunk_{i:03d}.mp3"
        _ffmpeg_extract_chunk(
            input_path, chunk_path, start_sec, end_sec - start_sec, i, output_dir,
        )
        chunks.append(Chunk(
            path=chunk_path,
            start_offset_sec=start_sec,
            end_offset_sec=end_sec,
            is_split=True,
        ))

    logger.info(
        "split_long_audio: %s (%.1fs) → %d chunks (silence-based, max_chunk=%ds)",
        input_path.name, duration, len(chunks), max_chunk_sec_val,
    )
    return chunks


def _load_pcm_mono_16k(input_path: Path) -> tuple[np.ndarray, int]:
    """ffmpeg → 16kHz mono PCM stdout → numpy float32 array。"""
    sr = ASR_AUDIO_SAMPLE_RATE_HZ
    cmd = [
        "ffmpeg", "-v", "error",
        "-i", str(input_path),
        "-vn",
        "-ar", str(sr),
        "-ac", "1",
        "-f", "s16le",
        "-",
    ]
    try:
        result = subprocess.run(
            cmd, check=True, capture_output=True, timeout=SPLIT_TIMEOUT_SEC,
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="replace")[-500:] if e.stderr else ""
        raise AppError(
            ErrorCode.AUDIO_UNREADABLE,
            f"ffmpeg PCM decode failed: {stderr}",
        ) from e
    except subprocess.TimeoutExpired as e:
        raise AppError(
            ErrorCode.AUDIO_UNREADABLE,
            "ffmpeg PCM decode timeout",
        ) from e

    pcm_int16 = np.frombuffer(result.stdout, dtype=np.int16)
    waveform = pcm_int16.astype(np.float32) / 32768.0
    return waveform, sr


def _accumulate_to_chunks(
    sample_ranges: list[tuple[int, int]],
    sr: int,
    max_chunk_sec: float,
) -> list[tuple[float, float]]:
    """把連續 silence-bounded 片累計成 ≤ max_chunk_sec 的 chunk。

    每個 sample range 是一段非靜音內容、合併到下個 silence 切點之前。
    我們累計到下個 range 加進去會超過 max_chunk_sec 為止，先 commit、開新 chunk。

    回時間秒 (start_sec, end_sec)。
    """
    if not sample_ranges:
        return []

    max_samples = int(max_chunk_sec * sr)
    chunks: list[tuple[float, float]] = []
    current_start = sample_ranges[0][0]
    current_end = sample_ranges[0][1]

    for begin, end in sample_ranges[1:]:
        if end - current_start <= max_samples:
            current_end = end
        else:
            chunks.append((current_start / sr, current_end / sr))
            current_start = begin
            current_end = end

    chunks.append((current_start / sr, current_end / sr))
    return chunks


def _fallback_fixed_split(
    input_path: Path,
    output_dir: Path,
    duration: float,
    max_chunk_sec: float,
) -> list[Chunk]:
    """整段無 silence 切點時的 fallback：固定時間切、無 overlap。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[Chunk] = []
    i = 0
    start = 0.0
    while start < duration - 0.01:
        end = min(duration, start + max_chunk_sec)
        chunk_path = output_dir / f"chunk_{i:03d}.mp3"
        _ffmpeg_extract_chunk(
            input_path, chunk_path, start, end - start, i, output_dir,
        )
        chunks.append(Chunk(
            path=chunk_path,
            start_offset_sec=start,
            end_offset_sec=end,
            is_split=True,
        ))
        start = end
        i += 1
    logger.warning(
        "split_long_audio fallback: %s (%.1fs) → %d fixed-time chunks (no silence detected)",
        input_path.name, duration, len(chunks),
    )
    return chunks


def _ffmpeg_extract_chunk(
    input_path: Path,
    chunk_path: Path,
    start_sec: float,
    duration_sec: float,
    chunk_index: int,
    cleanup_dir: Path,
) -> None:
    """ffmpeg `-ss start -t duration -i ... -vn -ar 16k -ac 1 -c:a libmp3lame chunk.mp3`。"""
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss", str(start_sec),
                "-t", str(duration_sec),
                "-i", str(input_path),
                "-vn",
                "-ar", str(ASR_AUDIO_SAMPLE_RATE_HZ),
                "-ac", str(ASR_AUDIO_CHANNELS),
                "-c:a", "libmp3lame",
                "-q:a", str(ASR_AUDIO_MP3_QUALITY),
                str(chunk_path),
            ],
            check=True,
            capture_output=True,
            timeout=SPLIT_TIMEOUT_SEC,
        )
    except subprocess.CalledProcessError as e:
        shutil.rmtree(cleanup_dir, ignore_errors=True)
        stderr = e.stderr.decode("utf-8", errors="replace")[-500:] if e.stderr else ""
        raise AppError(
            ErrorCode.AUDIO_UNREADABLE,
            f"ffmpeg split chunk {chunk_index} failed: {stderr}",
        ) from e
    except subprocess.TimeoutExpired as e:
        shutil.rmtree(cleanup_dir, ignore_errors=True)
        raise AppError(
            ErrorCode.AUDIO_UNREADABLE,
            f"ffmpeg split chunk {chunk_index} timeout after {SPLIT_TIMEOUT_SEC}s",
        ) from e
    if not chunk_path.exists():
        shutil.rmtree(cleanup_dir, ignore_errors=True)
        raise AppError(
            ErrorCode.AUDIO_UNREADABLE,
            f"ffmpeg produced no output for chunk {chunk_index}",
        )


def merge_chunk_results(
    chunks: list[Chunk],
    chunk_segments: list[list[dict]],
) -> list[dict]:
    """合併各 chunk 的 segments 為單一時間軸。

    silence-based 切點下 chunk 之間無 overlap → 直接加 offset、sort、不 dedup。

    speaker_id 不做 re-mapping（由 user 在 editor 手動對齊、M+1 backlog）。
    """
    if len(chunks) != len(chunk_segments):
        raise ValueError(
            f"chunks={len(chunks)} segments={len(chunk_segments)} length mismatch"
        )
    if not chunks:
        return []
    if len(chunks) == 1:
        return list(chunk_segments[0])

    out: list[dict] = []
    for chunk, segs in zip(chunks, chunk_segments, strict=False):
        for s in segs:
            out.append({
                **s,
                "start_time": s["start_time"] + chunk.start_offset_sec,
                "end_time": s["end_time"] + chunk.start_offset_sec,
            })

    out.sort(key=lambda s: s["start_time"])
    return out


# === Sub-chunk helper（給 transcribe_with_retry 用、不受切點演算法影響）===


def split_chunk_in_half_metadata(
    parent: Chunk,
    overlap_sec: float = 5.0,
) -> list[Chunk]:
    """把 parent chunk metadata 切半（不真的執行 ffmpeg）。

    retry sub-chunk 用，維持跟原版 chunk-level retry 相容。
    """
    parent_dur = parent.end_offset_sec - parent.start_offset_sec
    if parent_dur <= 0:
        raise ValueError(f"parent chunk has non-positive duration: {parent_dur}")

    safe_overlap = min(overlap_sec, parent_dur / 3)

    mid = parent.start_offset_sec + parent_dur / 2
    sub_a_start = parent.start_offset_sec
    sub_a_end = mid + safe_overlap / 2
    sub_b_start = mid - safe_overlap / 2
    sub_b_end = parent.end_offset_sec

    return [
        Chunk(
            path=parent.path,
            start_offset_sec=sub_a_start,
            end_offset_sec=sub_a_end,
            is_split=True,
        ),
        Chunk(
            path=parent.path,
            start_offset_sec=sub_b_start,
            end_offset_sec=sub_b_end,
            is_split=True,
        ),
    ]


def split_chunk_in_half(
    parent: Chunk,
    sub_dir: Path,
    depth: int,
    overlap_sec: float = 5.0,
) -> list[Chunk]:
    """把 parent chunk 切半成兩個實體 sub MP3 file。"""
    sub_metas = split_chunk_in_half_metadata(parent, overlap_sec=overlap_sec)
    sub_dir.mkdir(parents=True, exist_ok=True)
    out: list[Chunk] = []
    for i, meta in enumerate(sub_metas):
        sub_path = sub_dir / f"chunk_{int(parent.start_offset_sec)}_sub_{i}.mp3"
        relative_start = meta.start_offset_sec - parent.start_offset_sec
        relative_dur = meta.end_offset_sec - meta.start_offset_sec
        _ffmpeg_extract_chunk(
            parent.path, sub_path, relative_start, relative_dur,
            chunk_index=i, cleanup_dir=sub_dir,
        )
        out.append(Chunk(
            path=sub_path,
            start_offset_sec=meta.start_offset_sec,
            end_offset_sec=meta.end_offset_sec,
            is_split=True,
        ))
    return out
