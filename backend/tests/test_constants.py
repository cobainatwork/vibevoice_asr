"""
Tests for app.constants — prompt / MIME / repetition thresholds（純函式 / 常數）。
"""
from __future__ import annotations

from app.constants import (
    MAX_VLLM_RETRIES,
    REPETITION_MIN_OCCURRENCES,
    REPETITION_MIN_SUBSTRING_LEN,
    REPETITION_WINDOW_CHARS,
    RETRY_TEMPERATURES,
    SHOW_KEYS,
    SYSTEM_PROMPT,
    WS_CLOSE_AUTH_FAILED,
    WS_CLOSE_NORMAL,
    build_user_prompt,
    guess_mime,
)


# === guess_mime ===


def test_guess_mime_known_audio():
    assert guess_mime("a.wav") == "audio/wav"
    assert guess_mime("a.mp3") == "audio/mpeg"
    assert guess_mime("a.m4a") == "audio/mp4"
    assert guess_mime("a.flac") == "audio/flac"
    assert guess_mime("a.ogg") == "audio/ogg"
    assert guess_mime("a.opus") == "audio/ogg"


def test_guess_mime_known_video():
    assert guess_mime("a.mp4") == "video/mp4"
    assert guess_mime("a.mov") == "video/mp4"
    assert guess_mime("a.webm") == "video/mp4"


def test_guess_mime_case_insensitive():
    assert guess_mime("foo.WAV") == "audio/wav"
    assert guess_mime("foo.Mp3") == "audio/mpeg"


def test_guess_mime_unknown():
    assert guess_mime("foo.xyz") == "application/octet-stream"
    assert guess_mime("noext") == "application/octet-stream"


def test_guess_mime_full_path():
    """應只看副檔名，不在意目錄。"""
    assert guess_mime("/data/uploads/abc/audio.mp3") == "audio/mpeg"


# === build_user_prompt ===


def test_build_user_prompt_no_hotwords():
    text = build_user_prompt(60.0, None)
    assert "60.00 seconds audio" in text
    assert "with extra info" not in text
    for key in SHOW_KEYS:
        assert key in text


def test_build_user_prompt_empty_hotwords_treated_as_none():
    """空 list 與 None 行為應一致：不出現 'with extra info'。"""
    text = build_user_prompt(60.0, [])
    assert "with extra info" not in text


def test_build_user_prompt_with_hotwords():
    text = build_user_prompt(60.0, ["foo", "bar"])
    assert "60.00 seconds audio" in text
    assert "with extra info: foo,bar" in text


def test_build_user_prompt_single_hotword():
    text = build_user_prompt(30.0, ["microsoft"])
    assert "with extra info: microsoft" in text


def test_build_user_prompt_chinese_hotwords():
    text = build_user_prompt(15.0, ["糖尿病", "胰島素"])
    assert "with extra info: 糖尿病,胰島素" in text


def test_build_user_prompt_duration_format():
    """duration 一律以 .2f 顯示。"""
    assert "351.73 seconds" in build_user_prompt(351.73, None)
    assert "0.50 seconds" in build_user_prompt(0.5, None)


# === Repetition thresholds（sanity check 常數有效）===


def test_repetition_thresholds_are_positive():
    assert REPETITION_WINDOW_CHARS > 0
    assert REPETITION_MIN_SUBSTRING_LEN > 0
    assert REPETITION_MIN_OCCURRENCES >= 2
    assert (
        REPETITION_WINDOW_CHARS
        >= REPETITION_MIN_SUBSTRING_LEN * REPETITION_MIN_OCCURRENCES
    ), "window 必須至少容得下 N 個 K-字 substring，否則永遠偵測不到 repetition"


def test_retry_temperatures_have_enough_for_max_retries():
    """RETRY_TEMPERATURES 須至少有 MAX_VLLM_RETRIES 個值。"""
    assert len(RETRY_TEMPERATURES) >= MAX_VLLM_RETRIES


def test_retry_temperatures_first_is_zero():
    """第一次 attempt 用 temperature=0（deterministic）。"""
    assert RETRY_TEMPERATURES[0] == 0.0


def test_ws_close_codes_disjoint():
    """RFC 6455 標準碼與自訂碼不可衝突。"""
    assert WS_CLOSE_NORMAL == 1000
    assert WS_CLOSE_AUTH_FAILED >= 4000  # 4000+ 為私有範圍
