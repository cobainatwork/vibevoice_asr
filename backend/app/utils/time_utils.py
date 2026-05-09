"""
Time format converters: float seconds ↔ "hh:mm:ss.ms" / "mm:ss" / SRT timestamp.
"""
from __future__ import annotations

import re


def seconds_to_srt(seconds: float) -> str:
    """3.45 → '00:00:03,450' (SRT format with comma-ms)."""
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    ms = int(round((s - int(s)) * 1000))
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{ms:03d}"


def seconds_to_vtt(seconds: float) -> str:
    """3.45 → '00:00:03.450' (VTT format with dot-ms)."""
    return seconds_to_srt(seconds).replace(",", ".")


def seconds_to_hms(seconds: float, with_ms: bool = True) -> str:
    """3.45 → '00:00:03.45' (display)."""
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if with_ms:
        return f"{int(h):02d}:{int(m):02d}:{s:05.2f}"
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"


_SRT_RE = re.compile(r"^(\d+):(\d+):(\d+)[,.](\d+)$")


def srt_to_seconds(stamp: str) -> float:
    """'00:00:03,450' or '00:00:03.450' → 3.45"""
    m = _SRT_RE.match(stamp.strip())
    if not m:
        raise ValueError(f"Bad timestamp: {stamp!r}")
    h, mi, s, ms = m.groups()
    return int(h) * 3600 + int(mi) * 60 + int(s) + int(ms) / 1000.0
