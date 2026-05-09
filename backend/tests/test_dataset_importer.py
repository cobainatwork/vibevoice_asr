"""
Tests for services.dataset_importer.

Covers parse_time, parse_speaker, validate_segments + per-format parsers.
M3.5 milestone.
"""
from __future__ import annotations

import pytest

from app.errors import AppError, ErrorCode
from app.services.dataset_importer import parse_speaker, parse_time, validate_segments


# === parse_time ===


@pytest.mark.parametrize("input,expected", [
    (3.45, 3.45),
    (0, 0.0),
    ("3.45", 3.45),
    ("0:00:03.45", 3.45),
    ("0:01:30", 90.0),
    ("01:30", 90.0),
    ("1:23:45.123", 3600 + 23 * 60 + 45.123),
])
def test_parse_time_valid(input, expected):
    assert abs(parse_time(input) - expected) < 1e-6


@pytest.mark.parametrize("input", ["abc", "", " ", "1:2:3:4"])
def test_parse_time_invalid(input):
    with pytest.raises(AppError) as ei:
        parse_time(input)
    assert ei.value.code == ErrorCode.IMPORT_INVALID_TIME


# === parse_speaker ===


@pytest.mark.parametrize("input,expected", [
    (0, 0),
    (1, 1),
    ("0", 0),
    ("Speaker 1", 0),  # 1-indexed → 0-indexed
    ("Speaker 2", 1),
    ("Sp3", 2),
    ("S5", 4),
])
def test_parse_speaker(input, expected):
    assert parse_speaker(input) == expected


# === validate_segments ===


def test_validate_ok():
    segs = [
        {"speaker": 0, "text": "a", "start": 0.0, "end": 1.0},
        {"speaker": 1, "text": "b", "start": 1.0, "end": 2.0},
    ]
    validate_segments(segs, audio_duration=2.0)  # no raise


def test_validate_empty():
    with pytest.raises(AppError) as ei:
        validate_segments([], 10.0)
    assert ei.value.code == ErrorCode.IMPORT_PARSE_FAILED


def test_validate_overlap():
    segs = [
        {"speaker": 0, "text": "a", "start": 0.0, "end": 2.0},
        {"speaker": 0, "text": "b", "start": 1.5, "end": 3.0},
    ]
    with pytest.raises(AppError):
        validate_segments(segs, 10.0)


def test_validate_negative_duration():
    segs = [{"speaker": 0, "text": "x", "start": 5.0, "end": 4.0}]
    with pytest.raises(AppError):
        validate_segments(segs, 10.0)


def test_validate_exceeds_audio():
    segs = [{"speaker": 0, "text": "x", "start": 0.0, "end": 100.0}]
    with pytest.raises(AppError):
        validate_segments(segs, 10.0)
