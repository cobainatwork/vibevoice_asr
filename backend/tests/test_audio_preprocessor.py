"""audio_preprocessor.maybe_denoise / maybe_adjust_speed — 全 mock ffmpeg + denoise。"""
from __future__ import annotations

import math
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from app.errors import AppError, ErrorCode
from app.services import audio_preprocessor


def test_maybe_denoise_disabled_returns_original(tmp_path):
    fake_audio = tmp_path / "a.mp3"
    fake_audio.write_bytes(b"fake")
    out_path, was_denoised = audio_preprocessor.maybe_denoise(
        fake_audio, denoise_enabled=False,
    )
    assert out_path == fake_audio
    assert was_denoised is False


def test_maybe_denoise_enabled_writes_temp(tmp_path, monkeypatch):
    fake_audio = tmp_path / "a.mp3"
    fake_audio.write_bytes(b"fake")

    monkeypatch.setattr(
        audio_preprocessor,
        "_load_pcm",
        lambda p: (np.zeros(16000, dtype=np.float32), 16000),
    )
    monkeypatch.setattr(
        audio_preprocessor,
        "denoise",
        lambda waveform, sr: np.zeros_like(waveform),
    )

    # mock _write_denoised_mp3 寫個假檔
    def fake_write(waveform, sr):
        p = tmp_path / "denoised_xxx.mp3"
        p.write_bytes(b"fake denoised")
        return p

    monkeypatch.setattr(audio_preprocessor, "_write_denoised_mp3", fake_write)

    out_path, was_denoised = audio_preprocessor.maybe_denoise(
        fake_audio, denoise_enabled=True, denoise_model="gtcrn",
    )
    assert was_denoised is True
    assert out_path != fake_audio
    assert out_path.exists()


def test_cleanup_denoised_removes_file(tmp_path):
    p = tmp_path / "tmp.mp3"
    p.write_bytes(b"x")
    audio_preprocessor.cleanup_denoised(p)
    assert not p.exists()


def test_cleanup_denoised_missing_file_safe(tmp_path):
    p = tmp_path / "nonexistent.mp3"
    # 不 raise
    audio_preprocessor.cleanup_denoised(p)


# ============================================================
# maybe_adjust_speed tests
# ============================================================


def test_maybe_adjust_speed_noop_when_1_0(tmp_path):
    fake = tmp_path / "a.mp3"
    fake.write_bytes(b"fake")
    out, was = audio_preprocessor.maybe_adjust_speed(fake, playback_speed=1.0)
    assert out == fake
    assert was is False


def test_maybe_adjust_speed_noop_when_close_to_1(tmp_path):
    fake = tmp_path / "a.mp3"
    fake.write_bytes(b"fake")
    out, was = audio_preprocessor.maybe_adjust_speed(fake, playback_speed=1.0005)
    assert was is False  # math.isclose abs_tol=1e-3


def test_maybe_adjust_speed_writes_temp(tmp_path, monkeypatch):
    fake = tmp_path / "a.mp3"
    fake.write_bytes(b"fake")

    # mock get_settings 讓 upload_dir 指向 tmp_path
    class FakeSettings:
        upload_dir = tmp_path

    monkeypatch.setattr(audio_preprocessor, "get_settings", lambda: FakeSettings())

    # mock subprocess.run：成功回傳（returncode=0）、並寫個假 mp3 到 temp_path
    import subprocess as _subprocess

    original_mkstemp = audio_preprocessor.tempfile.mkstemp

    def fake_mkstemp(suffix="", prefix="", dir=None):
        fd, path = original_mkstemp(suffix=suffix, prefix=prefix, dir=dir)
        return fd, path

    # 攔截 subprocess.run，在呼叫前先把 temp file 寫入真實內容（模擬 ffmpeg 成功寫檔）
    def fake_run(cmd, *args, **kwargs):
        # cmd 最後一個 arg 是 output path
        out_path = Path(cmd[-1])
        out_path.write_bytes(b"fake speed adjusted mp3")

        class FakeResult:
            returncode = 0

        return FakeResult()

    monkeypatch.setattr(audio_preprocessor.subprocess, "run", fake_run)

    out, was = audio_preprocessor.maybe_adjust_speed(fake, playback_speed=0.7)
    assert was is True
    assert out != fake
    assert out.exists()


def test_maybe_adjust_speed_out_of_range(tmp_path):
    fake = tmp_path / "a.mp3"
    fake.write_bytes(b"fake")
    with pytest.raises(AppError) as exc:
        audio_preprocessor.maybe_adjust_speed(fake, playback_speed=3.0)
    assert exc.value.code == ErrorCode.INTERNAL_ERROR


def test_cleanup_adjusted_speed_missing_safe(tmp_path):
    p = tmp_path / "nonexistent.mp3"
    audio_preprocessor.cleanup_adjusted_speed(p)  # 不 raise
