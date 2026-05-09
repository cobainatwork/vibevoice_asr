"""
Tests for utils.parser — vLLM output parsing.

These run against expected upstream output formats and edge cases.
M2 milestone.
"""
from __future__ import annotations

import pytest

from app.utils.parser import parse_transcription


def test_parse_clean_array():
    raw = '[{"Start time": "0.00", "End time": "3.45", "Speaker ID": "1", "Content": "hello"}]'
    segs, dbg = parse_transcription(raw)
    assert len(segs) == 1
    assert segs[0]["start_time"] == 0.0
    assert segs[0]["end_time"] == 3.45
    assert segs[0]["speaker_id"] == 1
    assert segs[0]["text"] == "hello"
    assert dbg["has_markdown_wrapper"] is False


def test_parse_with_markdown_wrapper():
    raw = """```json
[{"Start time": "0.00", "End time": "3.45", "Speaker ID": "2", "Content": "world"}]
```"""
    segs, dbg = parse_transcription(raw)
    assert len(segs) == 1
    assert segs[0]["text"] == "world"
    assert dbg["has_markdown_wrapper"] is True


def test_parse_short_keys_alias():
    """Output sometimes uses 'Start' / 'End' / 'Speaker' instead."""
    raw = '[{"Start": 1.0, "End": 2.0, "Speaker": "3", "Content": "x"}]'
    segs, _ = parse_transcription(raw)
    assert segs[0]["speaker_id"] == 3


def test_parse_hh_mm_ss_time():
    raw = '[{"Start time": "0:01:30.5", "End time": "0:02:00", "Speaker ID": "1", "Content": "x"}]'
    segs, _ = parse_transcription(raw)
    assert segs[0]["start_time"] == 90.5
    assert segs[0]["end_time"] == 120.0


def test_parse_invalid_json_returns_empty():
    raw = "not json at all"
    segs, dbg = parse_transcription(raw)
    assert segs == []
    assert "no_json_found" in dbg["validation_warnings"]


def test_parse_segments_sorted():
    raw = """[
        {"Start time": 5.0, "End time": 7.0, "Speaker ID": "1", "Content": "b"},
        {"Start time": 1.0, "End time": 3.0, "Speaker ID": "2", "Content": "a"}
    ]"""
    segs, _ = parse_transcription(raw)
    assert segs[0]["text"] == "a"
    assert segs[1]["text"] == "b"


# === 邊界 case ===


def test_parse_empty_array():
    segs, dbg = parse_transcription("[]")
    assert segs == []
    assert dbg["validation_warnings"] == []


def test_parse_empty_string():
    segs, dbg = parse_transcription("")
    assert segs == []
    assert "no_json_found" in dbg["validation_warnings"]


def test_parse_whitespace_only():
    segs, dbg = parse_transcription("   \n  ")
    assert segs == []
    assert "no_json_found" in dbg["validation_warnings"]


def test_parse_dict_root_wrapped_to_list():
    """單一 segment 以 dict 表示時，應自動視為 list of one。"""
    raw = '{"Start time": "0", "End time": "1", "Speaker ID": "1", "Content": "x"}'
    segs, _ = parse_transcription(raw)
    assert len(segs) == 1
    assert segs[0]["text"] == "x"


def test_parse_segment_missing_keys_skipped():
    raw = """[
        {"Start time": "0", "End time": "1", "Speaker ID": "1", "Content": "ok"},
        {"Start time": "1", "Speaker ID": "1", "Content": "missing end"}
    ]"""
    segs, dbg = parse_transcription(raw)
    assert len(segs) == 1
    assert segs[0]["text"] == "ok"
    assert any("missing_keys" in w for w in dbg["validation_warnings"])


def test_parse_speaker_id_as_int():
    raw = '[{"Start time": 0, "End time": 1, "Speaker ID": 5, "Content": "x"}]'
    segs, _ = parse_transcription(raw)
    assert segs[0]["speaker_id"] == 5


def test_parse_speaker_id_with_prefix_string():
    """'Speaker 3' 字串應 fallback 抽出數字。"""
    raw = '[{"Start time": 0, "End time": 1, "Speaker ID": "Speaker 3", "Content": "x"}]'
    segs, _ = parse_transcription(raw)
    assert segs[0]["speaker_id"] == 3


def test_parse_negative_duration_warned_but_kept():
    """end < start：仍納入 segments，但 warnings 留紀錄。"""
    raw = '[{"Start time": 5, "End time": 3, "Speaker ID": "1", "Content": "x"}]'
    segs, dbg = parse_transcription(raw)
    assert len(segs) == 1
    assert any("zero_or_negative_duration" in w for w in dbg["validation_warnings"])


def test_parse_non_dict_element_skipped():
    """list 內的非 dict element（壞資料）skip 並 warn。"""
    raw = '[{"Start": 0, "End": 1, "Speaker": "1", "Content": "ok"}, "not_a_dict"]'
    segs, dbg = parse_transcription(raw)
    assert len(segs) == 1
    assert any("not_dict" in w for w in dbg["validation_warnings"])


def test_parse_root_neither_list_nor_dict():
    """root 為 string / number → 視為非法，回空 list + warning。"""
    raw = '"just a string"'
    segs, dbg = parse_transcription(raw)
    assert segs == []
    # 字串會被 _extract_json_object 找不到 [ 或 { → no_json_found
    assert dbg["validation_warnings"]
