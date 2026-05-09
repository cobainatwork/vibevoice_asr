"""
Dataset label importers — convert various formats to canonical training JSON.

See SPEC.md §9.2.
M3.5 milestone.

Speaker convention:
  - Internal: 1-indexed int (matches user-facing display)
  - Training JSON output: 0-indexed int (matches upstream toy_dataset)
  → conversion happens at import time (decrement by 1)
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)


# ============================================================
# Time parsing
# ============================================================


_TIME_RE_HMS = re.compile(r"^(\d+):(\d{1,2}):(\d{1,2})(?:\.(\d+))?$")
_TIME_RE_MS = re.compile(r"^(\d+):(\d{1,2})(?:\.(\d+))?$")


def parse_time(value: Any) -> float:
    """
    Parse time as float seconds or hh:mm:ss[.ms] or mm:ss[.ms].
    Raises AppError(IMPORT_INVALID_TIME) on bad input.
    """
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        raise AppError(ErrorCode.IMPORT_INVALID_TIME, f"Empty time")
    # Try plain float first
    try:
        return float(s)
    except ValueError:
        pass
    # hh:mm:ss
    if m := _TIME_RE_HMS.match(s):
        h, mi, sec, ms = m.groups()
        return int(h) * 3600 + int(mi) * 60 + int(sec) + (float(f"0.{ms}") if ms else 0)
    # mm:ss
    if m := _TIME_RE_MS.match(s):
        mi, sec, ms = m.groups()
        return int(mi) * 60 + int(sec) + (float(f"0.{ms}") if ms else 0)
    raise AppError(ErrorCode.IMPORT_INVALID_TIME, f"Cannot parse time: {s!r}")


def parse_speaker(value: Any) -> int:
    """
    Parse speaker. Accepts:
      - int (0 or 1+): used as-is, but must be >=0
      - "Speaker 1" / "Sp1" / "S1" / "speaker 0": extract digit, return 0-indexed
      - " 1 " (str digit): used as-is

    NOTE: returned value is the value the USER provided semantically. Caller
    should normalize to 0-indexed for training JSON output.
    """
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if s.isdigit():
        return int(s)
    m = re.search(r"\d+", s)
    if m:
        n = int(m.group())
        # If user wrote "Speaker 1", they mean speaker index 1 (1-based).
        # We assume convention: any string form is 1-indexed → convert to 0-indexed.
        return max(0, n - 1)
    return 0


# ============================================================
# Format-specific parsers
# ============================================================


def parse_xlsx(label_path: Path) -> list[dict]:
    """Parse Excel file. Returns list of segments in TRAINING JSON format (0-indexed)."""
    # TODO(M3.5): use openpyxl
    raise NotImplementedError


def parse_csv(label_path: Path) -> list[dict]:
    """Parse CSV file."""
    # TODO(M3.5): use pandas
    raise NotImplementedError


def parse_srt(label_path: Path) -> list[dict]:
    """Parse SubRip file. Speaker prefix optional ('Speaker N: ...')."""
    # TODO(M3.5): use pysrt
    raise NotImplementedError


def parse_vtt(label_path: Path) -> list[dict]:
    """Parse WebVTT file."""
    # TODO(M3.5): use webvtt-py
    raise NotImplementedError


def parse_json(label_path: Path) -> list[dict]:
    """Parse JSON file (assumed already in training format). Pass-through with validation."""
    data = json.loads(label_path.read_text(encoding="utf-8"))
    segs = data.get("segments")
    if not isinstance(segs, list):
        raise AppError(ErrorCode.IMPORT_PARSE_FAILED, "JSON missing 'segments' list")
    return segs


def parse_txt(label_path: Path) -> list[dict]:
    """
    Parse plain text format. Each line:
        [hh:mm:ss.ms] Speaker N: text
    """
    # TODO(M3.5)
    raise NotImplementedError


# ============================================================
# Top-level entry
# ============================================================


PARSERS = {
    "xlsx": parse_xlsx,
    "csv": parse_csv,
    "srt": parse_srt,
    "vtt": parse_vtt,
    "json": parse_json,
    "txt": parse_txt,
}


def import_label(
    label_path: Path,
    audio_filename: str,
    audio_duration: float,
    format: str,
    project_hotwords: list[str],
) -> dict:
    """
    Top-level: parse → validate → return canonical training JSON dict.

    See SPEC.md §9.1 for format.
    """
    if format not in PARSERS:
        raise AppError(
            ErrorCode.UNSUPPORTED_FORMAT,
            f"Format must be one of {list(PARSERS.keys())}",
        )
    parser = PARSERS[format]
    segments = parser(label_path)
    validate_segments(segments, audio_duration)
    return {
        "audio_duration": audio_duration,
        "audio_path": audio_filename,
        "segments": segments,
        "customized_context": project_hotwords,
    }


def validate_segments(segments: list[dict], audio_duration: float) -> None:
    """
    Sanity checks on parsed segments.
    Raises AppError(IMPORT_PARSE_FAILED) on hard errors.
    """
    if not segments:
        raise AppError(ErrorCode.IMPORT_PARSE_FAILED, "No segments parsed")
    prev_end = -1.0
    for i, seg in enumerate(segments):
        for k in ("speaker", "text", "start", "end"):
            if k not in seg:
                raise AppError(
                    ErrorCode.IMPORT_PARSE_FAILED,
                    f"Segment {i}: missing key {k!r}",
                )
        if seg["start"] >= seg["end"]:
            raise AppError(
                ErrorCode.IMPORT_PARSE_FAILED,
                f"Segment {i}: start >= end ({seg['start']}, {seg['end']})",
            )
        if seg["start"] < prev_end - 0.01:  # allow tiny float jitter
            raise AppError(
                ErrorCode.IMPORT_PARSE_FAILED,
                f"Segment {i}: overlaps previous (start {seg['start']} < prev_end {prev_end})",
            )
        if seg["end"] > audio_duration + 0.5:
            raise AppError(
                ErrorCode.IMPORT_PARSE_FAILED,
                f"Segment {i}: end {seg['end']} exceeds audio duration {audio_duration}",
            )
        prev_end = seg["end"]
