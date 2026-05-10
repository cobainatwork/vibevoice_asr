"""
Long-audio splitter & merger.

When audio > AUTO_SPLIT_THRESHOLD_SEC, split into fixed-duration chunks with
overlap; after per-chunk inference, merge results back to a single timeline.

M5 minimal viable implementation（M3.5 後修補）：
  - 固定時間切段（不做 silence detection），靠 overlap 容錯詞被切斷的情況
  - chunk file 同時做 16kHz mono MP3 轉碼（vLLM 標準輸入規格）
  - 不做 speaker re-mapping（跨 chunk 同一說話人 ID 可能不一致，由 user 在
    editor 手動對齊；長遠由 M5 完整版 backlog 處理）
  - 不並行（序列呼 vLLM）— vLLM 內部已 batch；序列也避免本地 connection pool
    複雜度。並行優化排 backlog

See SPEC.md §6.4.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from app.config import get_settings
from app.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)


# 跨 chunk overlap 去重門檻：兩 segment 文字相似度 >= 此值視為同一段
OVERLAP_DUP_SIMILARITY = 0.7

# 切段後音訊規格（ASR 標準輸入）
SPLIT_SAMPLE_RATE = 16000
SPLIT_CHANNELS = 1
SPLIT_QUALITY = 4  # libmp3lame -q:a 4 ≈ 128 kbps VBR
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
    overlap_sec: int | None = None,
    threshold_sec: int | None = None,
) -> list[Chunk]:
    """切長音檔為多段 chunk file。

    duration <= threshold_sec → 回單 chunk（path 指原檔，is_split=False）
    duration >  threshold_sec → ffmpeg 切多 chunk 寫到 output_dir/chunk_NNN.mp3，
                                每段 max_chunk_sec 長、overlap_sec 重疊。

    切點純時間（不做 silence detection），靠 overlap 在「詞被切斷時」由相鄰
    chunk cover。
    """
    settings = get_settings()
    max_chunk_sec = max_chunk_sec or settings.split_chunk_duration_sec
    overlap_sec = overlap_sec if overlap_sec is not None else settings.split_overlap_sec
    threshold_sec = threshold_sec or settings.auto_split_threshold_sec

    duration = get_duration_sec(input_path)
    if duration <= threshold_sec:
        return [Chunk(
            path=input_path,
            start_offset_sec=0.0,
            end_offset_sec=duration,
            is_split=False,
        )]

    if max_chunk_sec <= overlap_sec:
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            f"split_chunk_duration_sec ({max_chunk_sec}) must be > "
            f"split_overlap_sec ({overlap_sec})",
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    step = max_chunk_sec - overlap_sec
    chunks: list[Chunk] = []
    i = 0
    start = 0.0
    while start < duration - 0.01:
        end = min(duration, start + max_chunk_sec)
        chunk_path = output_dir / f"chunk_{i:03d}.mp3"
        _ffmpeg_extract_chunk(input_path, chunk_path, start, end - start, i, output_dir)
        chunks.append(Chunk(
            path=chunk_path,
            start_offset_sec=start,
            end_offset_sec=end,
            is_split=True,
        ))
        if end >= duration:
            break
        start += step
        i += 1

    logger.info(
        "split_long_audio: %s (%.1fs) → %d chunks (chunk=%ds, overlap=%ds)",
        input_path.name, duration, len(chunks), max_chunk_sec, overlap_sec,
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
                "-ar", str(SPLIT_SAMPLE_RATE),
                "-ac", str(SPLIT_CHANNELS),
                "-c:a", "libmp3lame",
                "-q:a", str(SPLIT_QUALITY),
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
    overlap_sec: float | None = None,
) -> list[dict]:
    """合併各 chunk 的 segments 為單一時間軸。

    步驟：
      1. 每個 chunk 的 segments 加 chunk.start_offset_sec
      2. 跨 chunk overlap 區內、文字相似度 >= OVERLAP_DUP_SIMILARITY 的 segment
         保留前者（前 chunk 結尾），丟棄後 chunk 開頭的重複
      3. Sort by start_time

    speaker_id 不做 re-mapping —— 跨 chunk 同一說話人 ID 可能不一致，由 user
    在 editor 手動對齊（M5 完整版 backlog）。
    """
    if len(chunks) != len(chunk_segments):
        raise ValueError(
            f"chunks={len(chunks)} segments={len(chunk_segments)} length mismatch"
        )
    if not chunks:
        return []
    if len(chunks) == 1:
        return list(chunk_segments[0])

    if overlap_sec is None:
        overlap_sec = float(get_settings().split_overlap_sec)

    out: list[dict] = []
    for chunk, segs in zip(chunks, chunk_segments, strict=False):
        for s in segs:
            offset_seg = {
                **s,
                "start_time": s["start_time"] + chunk.start_offset_sec,
                "end_time": s["end_time"] + chunk.start_offset_sec,
            }
            if out and _is_overlap_duplicate(out[-1], offset_seg, overlap_sec):
                continue
            out.append(offset_seg)

    out.sort(key=lambda s: s["start_time"])
    return out


# ============================================================
# Pure helpers
# ============================================================


def _is_overlap_duplicate(prev: dict, cur: dict, overlap_sec: float) -> bool:
    """判斷 cur 是否在 prev 的 overlap 範圍內、且文字大致相同。"""
    if cur["start_time"] > prev["end_time"] + overlap_sec:
        return False
    if cur["start_time"] < prev["start_time"] - overlap_sec:
        return False
    return _text_similarity(prev.get("text", ""), cur.get("text", "")) >= OVERLAP_DUP_SIMILARITY


def _text_similarity(a: str, b: str) -> float:
    """SequenceMatcher.ratio() — 對中文 OK、回 0-1。"""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()
