"""audio_preprocessor.maybe_denoise — 全 mock ffmpeg + denoise。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

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
