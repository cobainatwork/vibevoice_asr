"""
Tests for services.audio_splitter — 長音檔切段 + 多 chunk merge。

silence-based 切點版：
  - merge_chunk_results：offset 加總 + sort（無 dedup）
  - _accumulate_to_chunks：累計邏輯
  - _fallback_fixed_split：無 silence 切點 fallback
  - split_long_audio：整體路徑（mock ffmpeg / SilenceSlicer）

保留 split_chunk_in_half_metadata（retry helper、不受切點演算法影響）。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.services.audio_splitter import (
    Chunk,
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
# split_chunk_in_half_metadata
# ============================================================


def test_split_chunk_in_half_offsets_correct():
    """parent 55s chunk 切半 → 兩個 sub-chunks，offset 在 parent 全域時間軸內。"""
    from app.services.audio_splitter import Chunk, split_chunk_in_half_metadata

    parent = Chunk(
        path=Path("/tmp/parent.mp3"),
        start_offset_sec=100.0,
        end_offset_sec=155.0,
        is_split=True,
    )
    subs = split_chunk_in_half_metadata(parent, overlap_sec=5.0)
    assert len(subs) == 2

    # 第一個 sub: 100 → 130（30s 含 5s overlap 進入第二段）
    assert subs[0].start_offset_sec == 100.0
    assert subs[0].end_offset_sec == 130.0
    # 第二個 sub: 125 → 155（5s overlap）
    assert subs[1].start_offset_sec == 125.0
    assert subs[1].end_offset_sec == 155.0
    # 兩段覆蓋整個 parent 範圍
    assert subs[0].end_offset_sec >= subs[1].start_offset_sec  # 有 overlap
    assert subs[1].end_offset_sec == parent.end_offset_sec


def test_split_chunk_in_half_min_duration_clamps_overlap():
    """parent 太短（譬如 8s）時 overlap 不能超過 chunk_dur，否則 sub 無意義。"""
    from app.services.audio_splitter import Chunk, split_chunk_in_half_metadata

    parent = Chunk(
        path=Path("/tmp/short.mp3"),
        start_offset_sec=0.0,
        end_offset_sec=8.0,
        is_split=True,
    )
    subs = split_chunk_in_half_metadata(parent, overlap_sec=5.0)
    # 8s parent、5s overlap 不合理 → 自動降 overlap 到 chunk_dur 的 1/3 以下
    # sub 1: 0-5、sub 2: 3-8（overlap 2s）
    assert len(subs) == 2
    assert subs[0].end_offset_sec - subs[1].start_offset_sec >= 1.0  # overlap >= 1s
    assert subs[0].end_offset_sec - subs[0].start_offset_sec >= 4.0  # sub 不會太短


# ============================================================
# _accumulate_to_chunks
# ============================================================


def test_accumulate_to_chunks_basic():
    """3 個 silence-bounded ranges、累計成 1 個 chunk（全部加起來 < max）。"""
    from app.services.audio_splitter import _accumulate_to_chunks
    sr = 16000
    # 三段：0-2s / 3-5s / 6-8s，total 8s 沒超過 max 30s
    sample_ranges = [
        (0, 2 * sr), (3 * sr, 5 * sr), (6 * sr, 8 * sr),
    ]
    chunks = _accumulate_to_chunks(sample_ranges, sr, max_chunk_sec=30.0)
    assert len(chunks) == 1
    start, end = chunks[0]
    assert start == pytest.approx(0.0)
    assert end == pytest.approx(8.0)


def test_accumulate_to_chunks_overflow():
    """3 個 ranges 個別 20s、max 30s → 應該切成 3 chunks（各自太大無法合併）。"""
    from app.services.audio_splitter import _accumulate_to_chunks
    sr = 16000
    sample_ranges = [
        (0, 20 * sr),       # 0-20s
        (25 * sr, 45 * sr), # 25-45s，加進去 = 45s > 30 → 切
        (50 * sr, 70 * sr), # 50-70s，加進去 = 45s > 30 → 切
    ]
    chunks = _accumulate_to_chunks(sample_ranges, sr, max_chunk_sec=30.0)
    assert len(chunks) == 3


def test_accumulate_to_chunks_empty():
    from app.services.audio_splitter import _accumulate_to_chunks
    assert _accumulate_to_chunks([], 16000, 30.0) == []


# ============================================================
# merge_chunk_results（新版：no dedup）
# ============================================================


def test_merge_chunk_results_no_dedup():
    """新版 merge 不做 dedup、相同文字的 segments 都保留（由 editor 處理）。"""
    chunks = [
        Chunk(path=Path("/tmp/c0.mp3"), start_offset_sec=0.0, end_offset_sec=10.0, is_split=True),
        Chunk(path=Path("/tmp/c1.mp3"), start_offset_sec=10.0, end_offset_sec=20.0, is_split=True),
    ]
    chunk_segments = [
        [{"start_time": 0.0, "end_time": 3.0, "speaker_id": 1, "text": "hello"}],
        # chunk 1 開頭（global 10.0s）假設碰巧文字跟 chunk 0 結尾相同 — 新版不 dedup、都保留
        [{"start_time": 0.0, "end_time": 3.0, "speaker_id": 1, "text": "world"}],
    ]
    merged = merge_chunk_results(chunks, chunk_segments)
    assert len(merged) == 2
    assert merged[0]["start_time"] == 0.0
    assert merged[1]["start_time"] == 10.0
    assert merged[1]["text"] == "world"


def test_merge_chunk_results_sort_by_start_time():
    """merge 結果按 start_time 排序。"""
    chunks = [
        Chunk(path=Path("/tmp/c0.mp3"), start_offset_sec=0.0, end_offset_sec=5.0, is_split=True),
        Chunk(path=Path("/tmp/c1.mp3"), start_offset_sec=5.0, end_offset_sec=10.0, is_split=True),
    ]
    chunk_segments = [
        [{"start_time": 4.0, "end_time": 5.0, "speaker_id": 1, "text": "b"}],
        [{"start_time": 0.0, "end_time": 1.0, "speaker_id": 1, "text": "a"}],  # global 5-6s
    ]
    merged = merge_chunk_results(chunks, chunk_segments)
    assert merged[0]["text"] == "b"  # global 4-5s
    assert merged[1]["text"] == "a"  # global 5-6s


# ============================================================
# split_long_audio（mock ffmpeg + SilenceSlicer）
# ============================================================


def test_fallback_fixed_split_when_no_silence(tmp_path, monkeypatch):
    """slice_ranges 回空 → fallback 固定時間切。"""
    from app.services.audio_splitter import split_long_audio
    import app.services.audio_splitter as splitter_mod

    # mock get_duration_sec 回 120s（超過 threshold 60s）
    monkeypatch.setattr(splitter_mod, "get_duration_sec", lambda p: 120.0)
    # mock _load_pcm_mono_16k 回任意 numpy + sr
    monkeypatch.setattr(
        splitter_mod, "_load_pcm_mono_16k",
        lambda p: (np.zeros(120 * 16000, dtype=np.float32), 16000),
    )
    # mock SilenceSlicer.slice_ranges 回空 → 觸發 fallback
    monkeypatch.setattr(
        splitter_mod.SilenceSlicer, "slice_ranges",
        lambda self, w: [],
    )
    # mock _ffmpeg_extract_chunk 不真的跑 ffmpeg
    monkeypatch.setattr(
        splitter_mod, "_ffmpeg_extract_chunk",
        lambda *args, **kwargs: None,
    )

    # 假音檔（不會真讀）
    fake_audio = tmp_path / "fake.mp3"
    fake_audio.write_bytes(b"fake")

    chunks = split_long_audio(
        fake_audio, tmp_path / "chunks",
        max_chunk_sec=30, threshold_sec=60,
    )
    # fallback 切 120s / 30s = 4 chunks
    assert len(chunks) == 4
    assert all(c.is_split for c in chunks)
    # 第一個 chunk 0-30s
    assert chunks[0].start_offset_sec == 0.0
    assert chunks[0].end_offset_sec == 30.0
    # 最後一個 chunk 90-120s
    assert chunks[-1].start_offset_sec == 90.0
    assert chunks[-1].end_offset_sec == 120.0


def test_split_long_audio_silence_based(tmp_path, monkeypatch):
    """silence-based 切點正常路徑：slicer 回 ranges → 切多 chunk。"""
    from app.services.audio_splitter import split_long_audio
    import app.services.audio_splitter as splitter_mod

    sr = 16000
    monkeypatch.setattr(splitter_mod, "get_duration_sec", lambda p: 120.0)
    monkeypatch.setattr(
        splitter_mod, "_load_pcm_mono_16k",
        lambda p: (np.zeros(120 * sr, dtype=np.float32), sr),
    )
    # mock slice_ranges 回 3 段、各 30s 內合理可累計
    monkeypatch.setattr(
        splitter_mod.SilenceSlicer, "slice_ranges",
        lambda self, w: [
            (0, 25 * sr),
            (30 * sr, 55 * sr),
            (60 * sr, 110 * sr),
        ],
    )
    monkeypatch.setattr(
        splitter_mod, "_ffmpeg_extract_chunk",
        lambda *args, **kwargs: None,
    )

    fake_audio = tmp_path / "fake.mp3"
    fake_audio.write_bytes(b"fake")

    chunks = split_long_audio(
        fake_audio, tmp_path / "chunks",
        max_chunk_sec=60, threshold_sec=60,
    )
    # 30s+25s = 55s <= 60s 可合；再加 50s → 105s > 60s 切
    # 預期 2 個 chunks：[(0, 55), (60, 110)]
    assert len(chunks) == 2
    assert chunks[0].start_offset_sec == pytest.approx(0.0)
    assert chunks[0].end_offset_sec == pytest.approx(55.0)
    assert chunks[1].start_offset_sec == pytest.approx(60.0)
    assert chunks[1].end_offset_sec == pytest.approx(110.0)


def test_split_long_audio_short_passes_through(tmp_path, monkeypatch):
    """duration < threshold → 不切、回單 chunk path 指原檔。"""
    from app.services.audio_splitter import split_long_audio
    import app.services.audio_splitter as splitter_mod

    monkeypatch.setattr(splitter_mod, "get_duration_sec", lambda p: 30.0)
    fake_audio = tmp_path / "short.mp3"
    fake_audio.write_bytes(b"fake")

    chunks = split_long_audio(
        fake_audio, tmp_path / "chunks",
        max_chunk_sec=55, threshold_sec=60,
    )
    assert len(chunks) == 1
    assert chunks[0].path == fake_audio
    assert chunks[0].is_split is False
    assert chunks[0].start_offset_sec == 0.0
    assert chunks[0].end_offset_sec == 30.0
