"""
Audio denoiser — noisereduce wrapper。

純 numpy + scipy，無 ONNX model file。對 QC 場景的穩定背景噪音
(office / 訪談 / 空調聲)效果好；極端突發雜音不在範圍。

替換原 ONNX path(audio-denoiser-onnx) — 該方案實機 ONNX input spec
跟 wrapper 假設不符、放棄。詳見
docs/superpowers/specs/2026-05-12-denoise-noisereduce-design.md §1.1。
"""
from __future__ import annotations

import logging

import numpy as np

from app.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)


def denoise(waveform: np.ndarray, sr: int, model_name: str | None = None) -> np.ndarray:
    """對 mono float32 waveform 跑 noisereduce、回 cleaned waveform。

    model_name 參數保留向後相容(原 ONNX path 簽名)，目前忽略 —
    只有單一 noisereduce 實作。
    """
    try:
        import noisereduce as nr
    except ImportError as e:
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            "noisereduce not installed",
        ) from e

    if waveform.ndim != 1:
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            f"denoise expects mono 1D waveform, got shape {waveform.shape}",
        )

    cleaned = nr.reduce_noise(
        y=waveform,
        sr=sr,
        stationary=False,
    )
    return cleaned.astype(np.float32)
