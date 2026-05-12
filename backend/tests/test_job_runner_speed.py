"""_scale_segments unit tests — segments 時間戳 scale 回原 timeline。"""
from __future__ import annotations

import pytest

from app.services.job_runner import _scale_segments


def test_scale_segments_slow():
    """playback_speed=0.7、segments × 0.7 還原原 timeline。"""
    segs = [
        {"start_time": 10.0, "end_time": 20.0, "speaker_id": 1, "text": "a"},
    ]
    out = _scale_segments(segs, 0.7)
    assert out[0]["start_time"] == pytest.approx(7.0)
    assert out[0]["end_time"] == pytest.approx(14.0)


def test_scale_segments_fast():
    """playback_speed=1.5、segments × 1.5。"""
    segs = [
        {"start_time": 10.0, "end_time": 20.0, "speaker_id": 1, "text": "a"},
    ]
    out = _scale_segments(segs, 1.5)
    assert out[0]["start_time"] == pytest.approx(15.0)
    assert out[0]["end_time"] == pytest.approx(30.0)


def test_scale_segments_preserves_other_fields():
    segs = [{"start_time": 0.0, "end_time": 1.0, "speaker_id": 2, "text": "hello"}]
    out = _scale_segments(segs, 0.5)
    assert out[0]["speaker_id"] == 2
    assert out[0]["text"] == "hello"


def test_scale_segments_empty():
    assert _scale_segments([], 0.7) == []
