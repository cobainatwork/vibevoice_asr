"""
VTT / SRT 字幕解析 + s2tw 正規化。

YouTube 下載字幕的兩個格式:
- VTT(WebVTT)— yt-dlp 預設、含豐富 cue settings
- SRT(SubRip)— fallback 格式

解析後 Segment 結構與 ASR 一致(start_time / end_time / speaker_id / text),
方便 Editor 對照模式直接拿來比對。

YT 字幕沒 speaker 資訊 → speaker_id 固定 0(內部 0-indexed 慣例)。
"""
from __future__ import annotations

import re

from app.utils.parser import _to_traditional

_TIMESTAMP_RE = re.compile(
    r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})"
)
_INLINE_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RUN_RE = re.compile(r"\s+")


def parse_vtt(text: str) -> list[dict]:
    """解析 WEBVTT 內容為 segment list。"""
    return _parse_cues(text)


def parse_srt(text: str) -> list[dict]:
    """解析 SubRip 內容為 segment list。"""
    return _parse_cues(text)


def normalize_subtitle(segments: list[dict]) -> list[dict]:
    """OpenCC s2tw + 空白壓縮 + trim。"""
    out: list[dict] = []
    for s in segments:
        cleaned = _WHITESPACE_RUN_RE.sub(" ", s["text"]).strip()
        out.append({
            "start_time": s["start_time"],
            "end_time": s["end_time"],
            "speaker_id": s["speaker_id"],
            "text": _to_traditional(cleaned),
        })
    return out


# === Helpers ===


def _parse_cues(text: str) -> list[dict]:
    """共用 cue 解析。timestamp regex 同時接受 ',' (SRT) 與 '.' (VTT) 分隔符。"""
    segments: list[dict] = []
    blocks = re.split(r"\n\s*\n", text.strip())
    for block in blocks:
        seg = _parse_one_cue(block)
        if seg is not None:
            segments.append(seg)
    return segments


def _parse_one_cue(block: str) -> dict | None:
    lines = [ln for ln in block.splitlines() if ln.strip()]
    if not lines:
        return None

    # 找含 "-->" 的時間軸行
    time_line_idx = next(
        (i for i, ln in enumerate(lines) if "-->" in ln),
        None,
    )
    if time_line_idx is None:
        return None

    try:
        start, end = _parse_time_range(lines[time_line_idx])
    except ValueError:
        return None

    text_lines = lines[time_line_idx + 1:]
    if not text_lines:
        return None

    # 移除 inline tags(WebVTT 的 <v>, <i>, <b> 等)
    text = " ".join(text_lines)
    text = _INLINE_TAG_RE.sub("", text)
    text = _WHITESPACE_RUN_RE.sub(" ", text).strip()
    if not text:
        return None

    return {
        "start_time": start,
        "end_time": end,
        "speaker_id": 0,
        "text": text,
    }


def _parse_time_range(line: str) -> tuple[float, float]:
    """解析 "HH:MM:SS.mmm --> HH:MM:SS.mmm" 或 "MM:SS.mmm --> ...";SRT 用 ','。"""
    # 把「-->」前後切開,各自 parse
    parts = line.split("-->")
    if len(parts) != 2:
        raise ValueError(f"bad time range: {line}")
    return _parse_timestamp(parts[0]), _parse_timestamp(parts[1])


def _parse_timestamp(ts: str) -> float:
    """支援 HH:MM:SS.mmm / MM:SS.mmm / HH:MM:SS,mmm(SRT)。"""
    ts = ts.strip().split()[0]  # 去掉 cue settings 等 trailing 內容
    m = _TIMESTAMP_RE.match(ts)
    if m is None:
        raise ValueError(f"bad timestamp: {ts}")
    h = int(m.group(1) or 0)
    mm = int(m.group(2))
    s = int(m.group(3))
    ms_str = m.group(4)
    ms = int(ms_str.ljust(3, "0")[:3])
    return h * 3600 + mm * 60 + s + ms / 1000
