"""
Tests for utils.parser — vLLM output parsing.

These run against expected upstream output formats and edge cases.
M2 milestone（M3.5 後增 truncation salvage + OpenCC s2tw 後處理）。
"""
from __future__ import annotations

import pytest

from app.utils.parser import parse_transcription


def _opencc_unavailable() -> bool:
    """OpenCC 沒裝 / init 失敗時 parser fallback noop，相關 test skip。"""
    from app.utils.parser import _OPENCC
    return _OPENCC is None


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


# === Truncation recovery（vLLM 串流結尾被截案例）===


def test_parse_truncated_array_salvages_complete_objects():
    """vLLM 串流結尾被截在 segment 中間時，parser 應該救出已完整的前段。

    模擬實際觀察到的 c4aa8900 case：
      [{"Start":0,"End":2.37,"Content":"[Silence]"},  ← 缺 Speaker → skip
       {"Start":2.37,"End":14.43,"Speaker":0,"Content":"hello"},  ← 完整
       {"Start":14.43,"End":21.19,"Speaker":0,"Content":  ← 截斷

    舊版 _extract_json_object 找不到 balanced bracket → 整個 raw 丟掉、segments=[]。
    新版 salvage 已完成的 inner objects 並組成新 array。
    """
    raw = (
        '[{"Start":0,"End":2.37,"Content":"[Silence]"},'
        '{"Start":2.37,"End":14.43,"Speaker":0,"Content":"hello"},'
        '{"Start":14.43,"End":21.19,"Speaker":0,"Content":'
    )
    segs, dbg = parse_transcription(raw)
    assert len(segs) == 1
    assert segs[0]["start_time"] == 2.37
    assert segs[0]["text"] == "hello"
    assert "truncated_json_salvaged" in dbg["validation_warnings"]
    assert any("missing_keys" in w for w in dbg["validation_warnings"])


def test_parse_balanced_array_does_not_trigger_salvage():
    """完整 JSON 不應誤觸 salvage 路徑（debug 不該有 truncated 標記）。"""
    raw = '[{"Start":0,"End":1,"Speaker":0,"Content":"x"}]'
    _, dbg = parse_transcription(raw)
    assert "truncated_json_salvaged" not in dbg["validation_warnings"]


def test_parse_balanced_with_string_containing_brackets():
    """字串內含 { } [ ] 不應干擾 balanced bracket 計數（之前 _extract_json_object 沒處理）。"""
    raw = '[{"Start":0,"End":1,"Speaker":0,"Content":"text with {brace} and [bracket]"}]'
    segs, dbg = parse_transcription(raw)
    assert len(segs) == 1
    # 簡體轉繁不影響英文，原樣保留
    assert "{brace}" in segs[0]["text"]
    assert "truncated_json_salvaged" not in dbg["validation_warnings"]


# === 簡體 → 繁體後處理（OpenCC s2tw）===


@pytest.mark.skipif(
    _opencc_unavailable(),
    reason="OpenCC not installed (parser falls back to noop)",
)
def test_parse_simplified_chinese_converted_to_traditional():
    """上游 VibeVoice 偏簡體輸出；parser 應 s2tw 轉繁體。"""
    raw = '[{"Start":0,"End":1,"Speaker":0,"Content":"WhyVoice发布了新模型"}]'
    segs, _ = parse_transcription(raw)
    assert len(segs) == 1
    text = segs[0]["text"]
    # 簡體「发」必須已被轉換（OpenCC 任何 s2* 規則都會處理）
    assert "发" not in text, f"expected '发' to be converted, got {text!r}"
    # 英文與「新模型」（簡繁同形）穩定保留
    assert "WhyVoice" in text
    assert "新模型" in text
