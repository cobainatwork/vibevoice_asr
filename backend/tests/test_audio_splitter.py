"""
Tests for services.audio_splitter — 長音檔切段 + 多 chunk merge。

split_long_audio 的 ffmpeg 切段路徑需要 ffmpeg + 真實音檔 fixture，這層
透過實際 prod 上傳測試。本檔聚焦純算法邏輯：
  - merge_chunk_results：offset 加總 + overlap dedup + sort
  - _is_overlap_duplicate / _text_similarity：邊界 case

M5 milestone（minimal viable）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.audio_splitter import (
    Chunk,
    _is_overlap_duplicate,
    _text_similarity,
    merge_chunk_results,
)


def _seg(start: float, end: float, sp: int, text: str) -> dict:
    return {"start_time": start, "end_time": end, "speaker_id": sp, "text": text}


def _chunk(start: float, end: float, is_split: bool = True) -> Chunk:
    return Chunk(
        path=Path(f"/tmp/chunk_{start:.0f}.mp3"),
        start_offset_sec=start,
        end_offset_sec=end,
        is_split=is_split,
    )


# ============================================================
# merge_chunk_results
# ============================================================


def test_merge_empty_input():
    assert merge_chunk_results([], []) == []


def test_merge_single_chunk_passthrough():
    chunks = [_chunk(0, 60, is_split=False)]
    segs = [[_seg(1.0, 2.0, 1, "a"), _seg(3.0, 4.0, 1, "b")]]
    result = merge_chunk_results(chunks, segs)
    assert result == segs[0]


def test_merge_offset_added_to_chunk_segments():
    """每個 chunk 的 segments time 應加上 chunk.start_offset_sec。"""
    chunks = [_chunk(0, 50), _chunk(45, 95)]
    segs = [
        [_seg(0.0, 5.0, 1, "first")],
        [_seg(2.0, 8.0, 1, "second")],  # 在 chunk 2 內 0-50s 區間 → 全域 47-53s
    ]
    result = merge_chunk_results(chunks, segs, overlap_sec=5.0)
    assert len(result) == 2
    assert result[0]["start_time"] == 0.0
    assert result[0]["text"] == "first"
    assert result[1]["start_time"] == 47.0
    assert result[1]["end_time"] == 53.0
    assert result[1]["text"] == "second"


def test_merge_overlap_dedup_removes_duplicate_text():
    """前 chunk 結尾與後 chunk 開頭文字相似 → 後者被視為重複丟棄。"""
    chunks = [_chunk(0, 50), _chunk(45, 95)]
    segs = [
        [
            _seg(40.0, 47.0, 1, "你好世界這是測試文字"),  # 全域 40-47s
        ],
        [
            _seg(0.0, 2.0, 1, "你好世界這是測試文字"),  # 全域 45-47s（chunk 2 offset 加完）
            _seg(5.0, 10.0, 1, "後面新的內容"),         # 全域 50-55s
        ],
    ]
    result = merge_chunk_results(chunks, segs, overlap_sec=5.0)
    assert len(result) == 2  # 第二段被去重
    assert result[0]["text"] == "你好世界這是測試文字"
    assert result[1]["text"] == "後面新的內容"


def test_merge_overlap_dedup_keeps_distinct_text():
    """文字不同 → 即使在 overlap 區也保留。"""
    chunks = [_chunk(0, 50), _chunk(45, 95)]
    segs = [
        [_seg(40.0, 47.0, 1, "完全不同的內容 A")],
        [_seg(0.0, 2.0, 1, "另一段獨立的話 B")],
    ]
    result = merge_chunk_results(chunks, segs, overlap_sec=5.0)
    assert len(result) == 2


def test_merge_chunks_segments_length_mismatch_raises():
    chunks = [_chunk(0, 50)]
    with pytest.raises(ValueError, match="length mismatch"):
        merge_chunk_results(chunks, [[], []])


def test_merge_sorted_by_start_time():
    """即使 chunk 順序怪、merge 結果應 sort by start_time。"""
    chunks = [_chunk(50, 100), _chunk(0, 50)]
    segs = [
        [_seg(0.0, 5.0, 1, "later")],   # 全域 50-55s
        [_seg(0.0, 5.0, 1, "earlier")],  # 全域 0-5s
    ]
    result = merge_chunk_results(chunks, segs)
    assert result[0]["text"] == "earlier"
    assert result[1]["text"] == "later"


# ============================================================
# Pure helpers
# ============================================================


def test_text_similarity_identical_returns_1():
    assert _text_similarity("你好世界", "你好世界") == 1.0


def test_text_similarity_completely_different_low():
    assert _text_similarity("abc", "xyz") < 0.5


def test_text_similarity_empty_returns_0():
    assert _text_similarity("", "anything") == 0.0
    assert _text_similarity("anything", "") == 0.0


def test_is_overlap_duplicate_far_apart_not_dup():
    """時間相距遠 → 即使文字相同也不視為 overlap 重複。"""
    prev = _seg(0.0, 5.0, 1, "hello world")
    cur = _seg(100.0, 105.0, 1, "hello world")
    assert _is_overlap_duplicate(prev, cur, overlap_sec=5.0) is False


def test_is_overlap_duplicate_close_and_similar_text():
    prev = _seg(0.0, 5.0, 1, "你好世界")
    cur = _seg(3.0, 8.0, 1, "你好世界")  # 在 overlap 範圍內
    assert _is_overlap_duplicate(prev, cur, overlap_sec=5.0) is True


def test_is_overlap_duplicate_close_but_different_text():
    prev = _seg(0.0, 5.0, 1, "你好世界")
    cur = _seg(3.0, 8.0, 1, "完全不同的話")
    assert _is_overlap_duplicate(prev, cur, overlap_sec=5.0) is False
