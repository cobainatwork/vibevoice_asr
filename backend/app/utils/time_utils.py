"""
Time format converters: float seconds ↔ "hh:mm:ss.ms" / "mm:ss" / SRT timestamp.
"""
from __future__ import annotations

import re


def seconds_to_srt(seconds: float) -> str:
    """
    3.45 → '00:00:03,450' (SRT format with comma-ms)。

    先 round 到整體 ms 再拆 hh/mm/ss/ms，避免「.9999 秒 ms 取 1000」
    產生 ',1000' 之類的非法格式（會跨秒進位）。
    """
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def seconds_to_vtt(seconds: float) -> str:
    """3.45 → '00:00:03.450' (VTT format with dot-ms)."""
    return seconds_to_srt(seconds).replace(",", ".")


def seconds_to_hms(seconds: float, with_ms: bool = True) -> str:
    """
    3.45 → '00:00:03.45' (display)。

    with_ms=True 時以 centisecond 精度先 round，再拆 hh/mm/ss/cs，
    避免 59.9999 顯示為 '00:00:60.00'。
    """
    if with_ms:
        total_cs = int(round(seconds * 100))
        h, rem = divmod(total_cs, 360_000)
        m, rem = divmod(rem, 6_000)
        s, cs = divmod(rem, 100)
        return f"{h:02d}:{m:02d}:{s:02d}.{cs:02d}"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"


_SRT_RE = re.compile(r"^(\d+):(\d+):(\d+)[,.](\d+)$")


def srt_to_seconds(stamp: str) -> float:
    """'00:00:03,450' or '00:00:03.450' → 3.45"""
    m = _SRT_RE.match(stamp.strip())
    if not m:
        raise ValueError(f"Bad timestamp: {stamp!r}")
    h, mi, s, ms = m.groups()
    return int(h) * 3600 + int(mi) * 60 + int(s) + int(ms) / 1000.0
