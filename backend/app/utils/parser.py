"""
Parse vLLM transcription output → canonical Segment list.

Source ref: vendor/VibeVoice/vibevoice/processor/vibevoice_asr_processor.py:490-565

See SPEC.md §6.3 and §7.5.
M2 milestone — implement first; well unit-tested.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.constants import OUTPUT_KEY_MAPPING

logger = logging.getLogger(__name__)


def parse_transcription(raw_text: str) -> tuple[list[dict], dict]:
    """
    Parse vLLM raw output into canonical segments.

    Returns:
        (segments, debug_info)

        segments: list of dicts with keys:
            - start_time: float (seconds)
            - end_time: float
            - speaker_id: int (1-indexed, internal canonical)
            - text: str

        debug_info: {
            "has_markdown_wrapper": bool,
            "validation_warnings": list[str],
        }
    """
    debug: dict[str, Any] = {
        "has_markdown_wrapper": False,
        "validation_warnings": [],
    }

    cleaned = raw_text.strip()

    # 1. Strip ```json ... ``` markdown wrapper
    if "```json" in cleaned:
        debug["has_markdown_wrapper"] = True
        start = cleaned.find("```json") + len("```json")
        end = cleaned.find("```", start)
        if end > start:
            cleaned = cleaned[start:end].strip()

    # 2. Find first [ or { and matching close
    json_str = _extract_json_object(cleaned)
    if json_str is None:
        return [], {**debug, "validation_warnings": ["no_json_found"]}

    # 3. Parse
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return [], {**debug, "validation_warnings": [f"json_decode_error: {e}"]}

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return [], {**debug, "validation_warnings": ["root_not_list"]}

    # 4. Normalize each segment
    out: list[dict] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            debug["validation_warnings"].append(f"segment[{i}]_not_dict")
            continue
        normalized: dict[str, Any] = {}
        for raw_key, val in item.items():
            mapped = OUTPUT_KEY_MAPPING.get(raw_key)
            if mapped:
                normalized[mapped] = val
        if not all(k in normalized for k in ("start_time", "end_time", "speaker_id", "text")):
            debug["validation_warnings"].append(f"segment[{i}]_missing_keys")
            continue

        # Type coercion
        try:
            normalized["start_time"] = _to_seconds(normalized["start_time"])
            normalized["end_time"] = _to_seconds(normalized["end_time"])
            normalized["speaker_id"] = _to_int_speaker(normalized["speaker_id"])
            normalized["text"] = str(normalized["text"])
        except Exception as e:
            debug["validation_warnings"].append(f"segment[{i}]_coerce_error: {e}")
            continue

        out.append(normalized)

    # 5. Sort and validate
    out.sort(key=lambda s: s["start_time"])
    for i, s in enumerate(out):
        if s["start_time"] >= s["end_time"]:
            debug["validation_warnings"].append(f"segment[{i}]_zero_or_negative_duration")

    return out, debug


def _extract_json_object(text: str) -> str | None:
    """Find first [...] or {...} balanced bracket pair."""
    starts = [text.find("["), text.find("{")]
    starts = [s for s in starts if s != -1]
    if not starts:
        return None
    start = min(starts)
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None  # unbalanced


def _to_seconds(value: Any) -> float:
    """Convert time str or number to float seconds."""
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    # plain number
    try:
        return float(s)
    except ValueError:
        pass
    # hh:mm:ss[.ms]
    m = re.match(r"^(\d+):(\d{1,2}):(\d{1,2})(?:\.(\d+))?$", s)
    if m:
        h, mi, sec, ms = m.groups()
        return int(h) * 3600 + int(mi) * 60 + int(sec) + (float(f"0.{ms}") if ms else 0)
    raise ValueError(f"Cannot parse time: {s!r}")


def _to_int_speaker(value: Any) -> int:
    """
    vLLM output speaker_id is "1", "2", ... (1-indexed str).
    We keep 1-indexed int internally.
    """
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if s.isdigit():
        return int(s)
    # fallback: extract first digit run
    m = re.search(r"\d+", s)
    if m:
        return int(m.group())
    return 1  # default
