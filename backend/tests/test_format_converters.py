"""
Tests for utils.format_converters — speaker indexing conversion.
"""
from __future__ import annotations

from app.utils.format_converters import (
    segments_to_training_json,
    training_json_to_segments,
)


def test_round_trip_indexing():
    """1-indexed (internal) → 0-indexed (training) → 1-indexed."""
    internal = [
        {"start_time": 0.0, "end_time": 3.45, "speaker_id": 1, "text": "a"},
        {"start_time": 3.45, "end_time": 7.20, "speaker_id": 2, "text": "b"},
    ]
    label = segments_to_training_json(internal, "test.mp3", 7.20, ["hot"])
    assert label["segments"][0]["speaker"] == 0  # 1-indexed → 0-indexed
    assert label["segments"][1]["speaker"] == 1
    assert label["audio_path"] == "test.mp3"
    assert label["customized_context"] == ["hot"]

    back = training_json_to_segments(label)
    assert back[0]["speaker_id"] == 1
    assert back[1]["speaker_id"] == 2
