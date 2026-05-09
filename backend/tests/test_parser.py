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
