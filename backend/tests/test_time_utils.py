"""
Tests for utils.time_utils — seconds ↔ SRT / VTT / hh:mm:ss formats.

M2 milestone：純函式，無外部相依。
"""
from __future__ import annotations

import pytest

from app.utils.time_utils import (
    seconds_to_hms,
    seconds_to_srt,
    seconds_to_vtt,
    srt_to_seconds,
)


# === seconds_to_srt ===


@pytest.mark.parametrize("seconds,expected", [
    (0.0,           "00:00:00,000"),
    (3.45,          "00:00:03,450"),
    (90.5,          "00:01:30,500"),
    (3661.123,      "01:01:01,123"),
    (3600.0,        "01:00:00,000"),
])
def test_seconds_to_srt_basic(seconds, expected):
    assert seconds_to_srt(seconds) == expected


def test_seconds_to_srt_rounding_overflow():
    """3.9999 秒 ms 取整為 1000，必須進位至下一秒，不可寫成 ',1000'。"""
    assert seconds_to_srt(3.9999) == "00:00:04,000"


def test_seconds_to_srt_rounding_overflow_minute_boundary():
    """59.9999 秒進位後應跨分鐘。"""
    assert seconds_to_srt(59.9999) == "00:01:00,000"


# === seconds_to_vtt ===


@pytest.mark.parametrize("seconds,expected", [
    (0.0,           "00:00:00.000"),
    (3.45,          "00:00:03.450"),
    (3661.123,      "01:01:01.123"),
])
def test_seconds_to_vtt_uses_dot(seconds, expected):
    assert seconds_to_vtt(seconds) == expected


# === seconds_to_hms ===


def test_seconds_to_hms_with_ms():
    assert seconds_to_hms(3.45) == "00:00:03.45"
    assert seconds_to_hms(90.5) == "00:01:30.50"
    assert seconds_to_hms(0.0) == "00:00:00.00"


def test_seconds_to_hms_without_ms():
    assert seconds_to_hms(3.45, with_ms=False) == "00:00:03"
    assert seconds_to_hms(90.5, with_ms=False) == "00:01:30"


def test_seconds_to_hms_rounding_overflow():
    """59.9999 秒以 cs 精度 round 後應跨分鐘進位。"""
    assert seconds_to_hms(59.9999) == "00:01:00.00"
    assert seconds_to_hms(3599.9999) == "01:00:00.00"


# === srt_to_seconds ===


@pytest.mark.parametrize("stamp,expected", [
    ("00:00:03,450",    3.45),
    ("00:00:03.450",    3.45),       # dot 也接受
    ("00:01:30,500",    90.5),
    ("01:23:45,678",    3600 + 23 * 60 + 45.678),
    ("00:00:00,000",    0.0),
])
def test_srt_to_seconds(stamp, expected):
    assert abs(srt_to_seconds(stamp) - expected) < 1e-9


def test_srt_to_seconds_strips_whitespace():
    assert srt_to_seconds("  00:00:03,450  ") == 3.45


def test_srt_to_seconds_invalid():
    with pytest.raises(ValueError):
        srt_to_seconds("not a timestamp")
    with pytest.raises(ValueError):
        srt_to_seconds("00:00:03")  # 無 ms 段
