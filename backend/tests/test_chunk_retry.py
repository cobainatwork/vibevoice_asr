"""Tests for chunk-level retry logic in job_runner."""
from __future__ import annotations

from pathlib import Path

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
