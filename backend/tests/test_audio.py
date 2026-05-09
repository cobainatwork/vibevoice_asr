"""
Tests for utils.audio — MIME / video detection（純函式）。

`get_duration_sec` 需 ffprobe，留 integration test 階段測。
"""
from __future__ import annotations

from app.utils.audio import get_mime, is_video_file


# === is_video_file ===


def test_is_video_file_true():
    assert is_video_file("foo.mp4") is True
    assert is_video_file("foo.mov") is True
    assert is_video_file("foo.webm") is True
    assert is_video_file("foo.avi") is True
    assert is_video_file("foo.mkv") is True


def test_is_video_file_case_insensitive():
    assert is_video_file("FOO.MP4") is True
    assert is_video_file("Foo.Mov") is True


def test_is_video_file_false():
    assert is_video_file("foo.wav") is False
    assert is_video_file("foo.mp3") is False
    assert is_video_file("noext") is False
    assert is_video_file("") is False


# === get_mime ===


def test_get_mime_audio():
    assert get_mime("a.wav") == "audio/wav"
    assert get_mime("a.mp3") == "audio/mpeg"
    assert get_mime("a.flac") == "audio/flac"


def test_get_mime_video():
    assert get_mime("a.mp4") == "video/mp4"
    assert get_mime("a.mov") == "video/mp4"


def test_get_mime_case_insensitive():
    assert get_mime("a.MP3") == "audio/mpeg"
    assert get_mime("a.WAV") == "audio/wav"


def test_get_mime_unknown_returns_octet_stream():
    assert get_mime("a.xyz") == "application/octet-stream"
    assert get_mime("noext") == "application/octet-stream"
