"""Tests for chunk-level retry logic in job_runner."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


def test_chunk_outcome_dataclass_shape():
    from app.services.job_runner import ChunkOutcome

    o = ChunkOutcome(
        segments=[{"start_time": 0.0, "end_time": 1.0, "speaker_id": 1, "text": "x"}],
        raw_text='[{"Start":0,"End":1,"Speaker":0,"Content":"x"}]',
        partial=False,
        depth_reached=0,
        attempts=1,
    )
    assert o.partial is False
    assert o.depth_reached == 0
    assert o.attempts == 1
    assert len(o.segments) == 1


@pytest.fixture
def chunk_factory(tmp_path):
    """建一個 fake chunk + 對應 file（內容是空 mp3 header、ffmpeg 不會真的跑）。"""
    def _make(start: float, end: float, content: bytes = b""):
        from app.services.audio_splitter import Chunk
        f = tmp_path / f"chunk_{int(start)}.mp3"
        f.write_bytes(content)
        return Chunk(
            path=f, start_offset_sec=start, end_offset_sec=end, is_split=True,
        )
    return _make


@pytest.mark.asyncio
async def test_no_retry_when_partial_false(chunk_factory):
    """vLLM 回 partial=False → 不 retry、depth_reached=0。"""
    from app.services.job_runner import transcribe_with_retry

    chunk = chunk_factory(0, 55)
    sem = asyncio.Semaphore(1)
    fake_vllm = AsyncMock(return_value={
        "raw_text": '[{"Start":0,"End":1,"Speaker":0,"Content":"hello"}]',
        "elapsed_sec": 0.1, "attempts": 1, "partial": False,
    })

    with patch("app.services.job_runner.VllmClient") as MockClient:
        MockClient.return_value.transcribe = fake_vllm
        outcome = await transcribe_with_retry(
            chunk, depth=0, max_depth=2, sem=sem,
            vllm_base_url="http://mock", hotwords=[],
        )

    assert outcome.partial is False
    assert outcome.depth_reached == 0
    assert outcome.attempts == 1
    assert len(outcome.segments) == 1


@pytest.mark.asyncio
async def test_retry_once_then_success(chunk_factory):
    """depth 0 partial → depth 1 兩個 sub 都 success → outcome.partial=False。"""
    from app.services.job_runner import transcribe_with_retry

    chunk = chunk_factory(0, 55)
    sem = asyncio.Semaphore(2)

    call_count = {"n": 0}
    async def vllm_mock(audio_bytes, mime, dur, hotwords):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # depth 0: partial
            return {"raw_text": '[]', "elapsed_sec": 0.1, "attempts": 3, "partial": True}
        # depth 1 sub_a / sub_b: success
        return {
            "raw_text": '[{"Start":0,"End":1,"Speaker":0,"Content":"sub"}]',
            "elapsed_sec": 0.1, "attempts": 1, "partial": False,
        }

    # 同時 mock split_chunk_in_half 不真的呼 ffmpeg
    fake_subs = [chunk_factory(0, 30), chunk_factory(25, 55)]
    with patch("app.services.job_runner.VllmClient") as MockClient, \
         patch("app.services.job_runner.split_chunk_in_half", return_value=fake_subs):
        MockClient.return_value.transcribe = AsyncMock(side_effect=vllm_mock)
        outcome = await transcribe_with_retry(
            chunk, depth=0, max_depth=2, sem=sem,
            vllm_base_url="http://mock", hotwords=[],
        )

    assert outcome.partial is False
    assert outcome.depth_reached == 1
    assert outcome.attempts == 3  # depth 0 fail (1) + depth 1 sub_a (1) + sub_b (1)


@pytest.mark.asyncio
async def test_retry_twice_reaches_max_depth(chunk_factory):
    """所有層都 partial → 達 max_depth、partial=True、不再 retry。"""
    from app.services.job_runner import transcribe_with_retry

    chunk = chunk_factory(0, 55)
    sem = asyncio.Semaphore(4)
    always_partial = AsyncMock(return_value={
        "raw_text": '[]', "elapsed_sec": 0.1, "attempts": 3, "partial": True,
    })
    fake_subs_d1 = [chunk_factory(0, 30), chunk_factory(25, 55)]
    fake_subs_d2 = [chunk_factory(0, 17), chunk_factory(13, 30)]

    def split_side_effect(parent, sub_dir, depth, overlap_sec=5.0):
        return fake_subs_d1 if depth == 1 else fake_subs_d2

    with patch("app.services.job_runner.VllmClient") as MockClient, \
         patch("app.services.job_runner.split_chunk_in_half", side_effect=split_side_effect):
        MockClient.return_value.transcribe = always_partial
        outcome = await transcribe_with_retry(
            chunk, depth=0, max_depth=2, sem=sem,
            vllm_base_url="http://mock", hotwords=[],
        )

    assert outcome.partial is True
    assert outcome.depth_reached == 2  # 達上限 2
