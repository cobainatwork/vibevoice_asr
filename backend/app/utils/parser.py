"""
Parse vLLM transcription output → canonical Segment list.

Source ref: vendor/VibeVoice/vibevoice/processor/vibevoice_asr_processor.py:490-565

Behavior layers (M3.5 後增強):
  1. Markdown wrapper strip
  2. Balanced bracket extract；unbalanced 時 salvage 已完成的 inner objects
     （vLLM 串流結尾被截斷的常見 case）
  3. Per-segment normalize：key mapping、type coerce、缺 key skip
  4. 簡體 → 繁體（s2tw，台灣慣用詞）後處理；raw_text 保留原樣作為模型行為
     證據與後續 LoRA fine-tune 對照基準

See SPEC.md §6.3 and §7.5.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.constants import OUTPUT_KEY_MAPPING

logger = logging.getLogger(__name__)


# ============================================================
# 簡體 → 繁體後處理（s2tw — 簡轉繁 + 台灣慣用詞）
# 上游 VibeVoice 訓練資料偏簡體，本層強制轉繁。OpenCC 未裝時 fallback noop
# 不擋啟動，但會 log warning 提醒安裝。
# ============================================================

try:
    from opencc import OpenCC
    _OPENCC: OpenCC | None = OpenCC("s2tw")
except Exception as e:  # noqa: BLE001 — OpenCC 任何 import / init 失敗都 fallback
    _OPENCC = None
    logger.warning("OpenCC unavailable; transcription text will not be converted to Traditional: %s", e)


def _to_traditional(text: str) -> str:
    """Convert simplified → traditional (s2tw)；OpenCC 缺失時原樣回傳。"""
    if _OPENCC is None:
        return text
    # OpenCC 套件無 type stub、convert() 推為 Any → 顯式 str() 包確保回傳型別正確
    return str(_OPENCC.convert(text))


# ============================================================
# Top-level entry
# ============================================================


def parse_transcription(raw_text: str) -> tuple[list[dict], dict]:
    """
    Parse vLLM raw output into canonical segments.

    Returns:
        (segments, debug_info)

        segments: list of dicts with keys:
            - start_time: float (seconds)
            - end_time: float
            - speaker_id: int (1-indexed, internal canonical)
            - text: str（已轉繁體）

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

    # 2. Find first [ or { and matching close（unbalanced 時 salvage）
    json_str, salvaged = _extract_json_object(cleaned)
    if json_str is None:
        return [], {**debug, "validation_warnings": ["no_json_found"]}
    if salvaged:
        debug["validation_warnings"].append("truncated_json_salvaged")

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

        # Type coercion + traditional Chinese conversion
        try:
            normalized["start_time"] = _to_seconds(normalized["start_time"])
            normalized["end_time"] = _to_seconds(normalized["end_time"])
            normalized["speaker_id"] = _to_int_speaker(normalized["speaker_id"])
            normalized["text"] = _to_traditional(str(normalized["text"]))
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


# ============================================================
# JSON extraction
# ============================================================


def _extract_json_object(text: str) -> tuple[str | None, bool]:
    """
    回傳 (json_str, salvaged)：
      - balanced bracket pair 找到 → (text, False)
      - unbalanced（截斷）→ 嘗試從 array 內 salvage 完整 inner objects → (rebuilt, True)
      - 都失敗 → (None, False)
    """
    starts = [text.find("["), text.find("{")]
    starts = [s for s in starts if s != -1]
    if not starts:
        return None, False
    start = min(starts)

    balanced = _find_balanced_pair(text, start)
    if balanced is not None:
        return balanced, False

    # Unbalanced（vLLM 串流結尾被截在某 segment 中間）：salvage
    salvaged = _salvage_truncated_array(text, start)
    return salvaged, salvaged is not None


def _find_balanced_pair(text: str, start: int) -> str | None:
    """從 start 位置找 balanced bracket pair，正確處理 string literal。"""
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _salvage_truncated_array(text: str, array_start: int) -> str | None:
    """
    用 json.JSONDecoder.raw_decode 從 array 內逐個解出完整 inner object，
    遇到截斷或語法錯誤就停。把成功解出的物件重新 dumps 成合法 array。
    只對 [...] 形式 salvage（{...} 不適用）。
    """
    if text[array_start] != "[":
        return None
    decoder = json.JSONDecoder()
    objs: list[Any] = []
    i = array_start + 1
    n = len(text)
    while i < n:
        # Skip 空白與分隔逗號
        while i < n and text[i] in " ,\t\n\r":
            i += 1
        if i >= n or text[i] == "]":
            break
        try:
            obj, end = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            break  # 第 N 個 object 截斷或格式錯
        objs.append(obj)
        i = end
    return json.dumps(objs) if objs else None


# ============================================================
# Type coercion
# ============================================================


def _to_seconds(value: Any) -> float:
    """Convert time str or number to float seconds."""
    if isinstance(value, int | float):
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
