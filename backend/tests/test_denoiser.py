"""denoiser ONNX wrapper 行為驗證 — 全 mock onnxruntime，不真載 model file。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.errors import AppError, ErrorCode
from app.services import denoiser


@pytest.fixture(autouse=True)
def _reset_cache():
    """每個 test 清 session cache，避免 test 間污染。"""
    denoiser._session_cache.clear()
    yield
    denoiser._session_cache.clear()


def test_denoise_unknown_model_raises():
    waveform = np.zeros(16000, dtype=np.float32)
    with pytest.raises(AppError) as exc:
        denoiser.denoise(waveform, sr=16000, model_name="unknown")
    assert exc.value.code == ErrorCode.INTERNAL_ERROR


def test_denoise_wrong_sample_rate_raises():
    waveform = np.zeros(48000, dtype=np.float32)
    with pytest.raises(AppError) as exc:
        denoiser.denoise(waveform, sr=48000, model_name="gtcrn")
    assert exc.value.code == ErrorCode.INTERNAL_ERROR


def test_denoise_chunks_and_concatenates():
    """3 chunk 音檔 → 各 chunk session.run → concat 回原長度。

    使用 GTCRN chunk_size=480000 (30s)。
    3 個 chunk = 3 * 480000 = 1,440,000 samples。
    """
    chunk_size = denoiser._MODEL_CONFIGS["gtcrn"]["chunk_size_samples"]
    n_chunks = 3
    total_samples = chunk_size * n_chunks

    fake_session = MagicMock()
    fake_input = MagicMock()
    fake_input.name = "input"
    fake_output = MagicMock()
    fake_output.name = "output"
    fake_session.get_inputs.return_value = [fake_input]
    fake_session.get_outputs.return_value = [fake_output]
    # 每次 run 回 (1, 1, chunk_size) int16 zeros
    fake_session.run.return_value = [
        np.zeros((1, 1, chunk_size), dtype=np.int16)
    ]

    with patch.object(denoiser, "_get_session", return_value=fake_session):
        waveform = np.ones(total_samples, dtype=np.float32) * 0.5
        cleaned = denoiser.denoise(waveform, sr=16000, model_name="gtcrn")

    assert cleaned.shape == waveform.shape
    assert cleaned.dtype == np.float32
    assert fake_session.run.call_count == n_chunks


def test_denoise_last_chunk_padded():
    """音檔長度不是 chunk_size 整數倍時，最後 chunk 被 pad、輸出 trim 回原長度。"""
    chunk_size = denoiser._MODEL_CONFIGS["gtcrn"]["chunk_size_samples"]
    # 1.5 chunks 長度
    total_samples = int(chunk_size * 1.5)

    fake_session = MagicMock()
    fake_input = MagicMock()
    fake_input.name = "input"
    fake_output = MagicMock()
    fake_output.name = "output"
    fake_session.get_inputs.return_value = [fake_input]
    fake_session.get_outputs.return_value = [fake_output]
    fake_session.run.return_value = [
        np.zeros((1, 1, chunk_size), dtype=np.int16)
    ]

    with patch.object(denoiser, "_get_session", return_value=fake_session):
        waveform = np.ones(total_samples, dtype=np.float32) * 0.3
        cleaned = denoiser.denoise(waveform, sr=16000, model_name="gtcrn")

    # 輸出必須與輸入 shape 相同
    assert cleaned.shape == (total_samples,)
    assert cleaned.dtype == np.float32
    # 2 個 chunk (完整 + 短 chunk 被 pad)
    assert fake_session.run.call_count == 2
