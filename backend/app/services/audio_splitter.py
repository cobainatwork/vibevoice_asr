"""
Long-audio splitter & merger.

When audio > AUTO_SPLIT_THRESHOLD_SEC, split at silence boundaries with
overlap; after parallel inference, merge results back to a single timeline.

See SPEC.md §6.4.
M5 milestone.
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)


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


def find_silence_points(path: Path, target_sec: float, tolerance_sec: float = 30.0) -> list[float]:
    """
    Use ffmpeg silencedetect to find silence boundaries near target times.

    Returns list of timestamps (sec) usable as split points.
    """
    # TODO(M5):
    # cmd = ["ffmpeg", "-i", str(path), "-af", "silencedetect=n=-30dB:d=0.5",
    #        "-f", "null", "-"]
    # Parse stderr lines: "silence_end: <time> | silence_duration: ..."
    # Pick the silence_end nearest to target_sec within tolerance
    raise NotImplementedError


def split_long_audio(
    input_path: Path,
    output_dir: Path,
    max_chunk_sec: int | None = None,
    overlap_sec: int | None = None,
    threshold_sec: int | None = None,
) -> list[Chunk]:
    """
    Split a long audio file into chunks.

    If duration <= threshold_sec: returns [single chunk].
    Else: splits at silence boundaries, with overlap_sec overlap.

    Output files written to output_dir.
    """
    settings = get_settings()
    max_chunk_sec = max_chunk_sec or settings.split_chunk_duration_sec
    overlap_sec = overlap_sec or settings.split_overlap_sec
    threshold_sec = threshold_sec or settings.auto_split_threshold_sec

    duration = get_duration_sec(input_path)
    if duration <= threshold_sec:
        return [Chunk(path=input_path, start_offset_sec=0.0,
                      end_offset_sec=duration, is_split=False)]

    # TODO(M5):
    # 1. split_points = find_silence_points(input_path, target_sec=max_chunk_sec, ...)
    # 2. for each (start, end): ffmpeg -ss start -t (end-start+overlap) -i ... output_dir/chunk_N.mp3
    # 3. return list[Chunk]
    raise NotImplementedError


def merge_chunk_results(
    chunks: list[Chunk],
    chunk_segments: list[list[dict]],
    overlap_sec: float = 5.0,
) -> list[dict]:
    """
    Merge per-chunk segment lists into a single timeline.

    Steps:
      1. For each chunk's segments, add chunk.start_offset_sec to start_time / end_time
      2. Within overlap regions: dedupe segments whose text mostly matches between adjacent chunks
      3. Best-effort speaker re-mapping: heuristic alignment across overlap
      4. Sort by start_time

    Returns the merged segment list.
    """
    # TODO(M5)
    raise NotImplementedError
