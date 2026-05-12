"""denoiser noisereduce wrapper 行為驗證。"""
from __future__ import annotations

import numpy as np
import pytest

from app.errors import AppError, ErrorCode
from app.services import denoiser


def test_denoise_mono_waveform():
    """1D float32 waveform → cleaned same shape float32。"""
    waveform = np.random.randn(16000).astype(np.float32)  # 1 sec @ 16kHz
    cleaned = denoiser.denoise(waveform, sr=16000)
    assert cleaned.shape == waveform.shape
    assert cleaned.dtype == np.float32


def test_denoise_zeros_returns_zeros():
    """全零 waveform → 仍是全零(or 接近、不 raise)。"""
    waveform = np.zeros(16000, dtype=np.float32)
    cleaned = denoiser.denoise(waveform, sr=16000)
    assert cleaned.shape == waveform.shape


def test_denoise_rejects_multichannel():
    """2D waveform → AppError(我們設計 mono only)。"""
    waveform = np.zeros((2, 16000), dtype=np.float32)
    with pytest.raises(AppError) as exc:
        denoiser.denoise(waveform, sr=16000)
    assert exc.value.code == ErrorCode.INTERNAL_ERROR


def test_denoise_model_name_ignored():
    """model_name 參數接受但 ignored(向後相容簽名)。"""
    waveform = np.random.randn(16000).astype(np.float32)
    cleaned1 = denoiser.denoise(waveform, sr=16000)
    cleaned2 = denoiser.denoise(waveform, sr=16000, model_name="gtcrn")
    cleaned3 = denoiser.denoise(waveform, sr=16000, model_name="zipenhancer")
    # 三者應該完全相同(model_name 無作用)
    np.testing.assert_array_equal(cleaned1, cleaned2)
    np.testing.assert_array_equal(cleaned1, cleaned3)
