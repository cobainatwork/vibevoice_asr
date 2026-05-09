"""
Audio utilities: ffprobe duration, MIME guessing.

See SPEC.md §6.2 (MIME map).
M2 milestone.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from app.constants import VIDEO_EXTENSIONS, guess_mime
from app.errors import AppError, ErrorCode


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
    import os
    return os.path.splitext(filename)[1].lower() in VIDEO_EXTENSIONS


def get_mime(filename: str) -> str:
    return guess_mime(filename)
