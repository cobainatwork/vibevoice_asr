"""
ONNX-based audio denoiser.

兩個模型來自 Audio-Denoiser-ONNX (Apache 2.0):
- GTCRN (輕量、RTF 0.0036、預設): chunk 30s = 480,000 samples
- ZipEnhancer (高品質、RTF 0.32): chunk 6s = 96,000 samples

Input/output shape (upstream 確認):
  input:  (1, 1, chunk_size_samples)  int16  — batch=1, ch=1, variable length
  output: (1, 1, chunk_size_samples)  int16

Upstream 的 normalize_to_int16: scale so max abs value maps to 32767.
This wrapper does the same normalization before session.run, then converts back to float32.

ONNX session 用 module-level cache (Lazy load、跑第一次才 load model file 到 memory)。
"""
from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np

from app.config import get_settings
from app.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)


# Lazy-loaded session cache: { model_name: ort.InferenceSession }
_session_cache: dict[str, Any] = {}
_cache_lock = Lock()


# Model 檔名 / 配置 (對應 vendor/denoiser/ 下檔案)
# chunk_size_samples 來自 upstream inference script:
#   GTCRN: 30s x 16000 = 480000 samples
#   ZipEnhancer: 6s x 16000 = 96000 samples (最小 6s，模型需求)
_MODEL_CONFIGS: dict[str, dict] = {
    "gtcrn": {
        "filename": "GTCRN.onnx",
        "sample_rate": 16000,
        "chunk_size_samples": 480000,  # 30 seconds
    },
    "zipenhancer": {
        "filename": "ZipEnhancer.onnx",
        "sample_rate": 16000,
        "chunk_size_samples": 96000,   # 6 seconds (model minimum)
    },
}


def denoise(waveform: np.ndarray, sr: int, model_name: str = "gtcrn") -> np.ndarray:
    """對 mono float32 waveform 跑 denoise、回 cleaned waveform (same shape)。

    sr 必須與 model 的 sample_rate 一致 (目前兩個模型都 16kHz)。
    waveform shape (n_samples,) float32 [-1, 1]。
    """
    if model_name not in _MODEL_CONFIGS:
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            f"unknown denoise model: {model_name}",
        )
    cfg = _MODEL_CONFIGS[model_name]
    if sr != cfg["sample_rate"]:
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            f"denoise model {model_name} expects sr={cfg['sample_rate']}, got {sr}",
        )

    session = _get_session(model_name)
    chunk_size = cfg["chunk_size_samples"]
    out_chunks: list[np.ndarray] = []

    for start in range(0, len(waveform), chunk_size):
        chunk = waveform[start : start + chunk_size]
        # 對最後一個短 chunk pad 到 chunk_size (使用 white noise 保持 RMS 一致)
        if len(chunk) < chunk_size:
            chunk = _pad_chunk(chunk, chunk_size)
        out = _run_session(session, chunk)
        out_chunks.append(out)

    cleaned = np.concatenate(out_chunks)[: len(waveform)]  # trim padding
    return cleaned.astype(np.float32)


# === Internal helpers ===


def _get_session(model_name: str) -> Any:
    """Lazy-load ONNX InferenceSession，thread-safe。"""
    with _cache_lock:
        if model_name in _session_cache:
            return _session_cache[model_name]
        try:
            import onnxruntime as ort
        except ImportError as e:
            raise AppError(
                ErrorCode.INTERNAL_ERROR,
                "onnxruntime not installed",
            ) from e
        model_path = _model_path(model_name)
        logger.info(
            "denoiser: loading ONNX session model=%s path=%s", model_name, model_path
        )
        session = ort.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"],
        )
        _session_cache[model_name] = session
        return session


def _model_path(model_name: str) -> Path:
    """ONNX model 檔位置。Mount 進 backend container 的 /vendor 路徑 (或 settings 指定)。"""
    settings = get_settings()
    base = Path(settings.denoiser_model_dir)
    cfg = _MODEL_CONFIGS[model_name]
    path = base / cfg["filename"]
    if not path.exists():
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            f"denoise model file not found: {path}. "
            f"Run scripts/download_denoiser_models.sh to download models.",
        )
    return path


def _normalize_to_int16(chunk: np.ndarray) -> np.ndarray:
    """Upstream 規格: scale so max abs value maps to 32767, convert to int16.

    Matches Audio-Denoiser-ONNX/GTCRN/Inference_GTCRN_ONNX.py normalize_to_int16.
    """
    max_val = float(np.max(np.abs(chunk)))
    scaling_factor = 32767.0 / max_val if max_val > 0 else 1.0
    return (chunk * scaling_factor).astype(np.int16)


def _pad_chunk(chunk: np.ndarray, target_size: int) -> np.ndarray:
    """Pad short chunk with white noise matching signal RMS (upstream pattern)."""
    pad_len = target_size - len(chunk)
    rms = float(np.sqrt(np.mean(chunk ** 2))) if len(chunk) > 0 else 1e-6
    noise = np.random.randn(pad_len).astype(np.float32) * rms
    return np.concatenate([chunk, noise])


def _run_session(session: Any, chunk: np.ndarray) -> np.ndarray:
    """Run ONNX inference on a single chunk.

    Upstream input shape: (1, 1, chunk_size_samples)  int16
    Upstream output shape: (1, 1, chunk_size_samples) int16

    Steps:
    1. float32 → int16 via normalize_to_int16
    2. reshape to (1, 1, n_samples)
    3. session.run
    4. reshape output to (n_samples,), convert back to float32 [-1, 1]
    """
    input_name = session.get_inputs()[0].name
    out_name = session.get_outputs()[0].name

    chunk_int16 = _normalize_to_int16(chunk)
    inp = chunk_int16.reshape(1, 1, -1)
    out = session.run([out_name], {input_name: inp})[0]
    # out shape: (1, 1, n_samples) int16 → (n_samples,) float32
    out_flat = out.reshape(-1).astype(np.float32)
    # de-normalize: int16 back to [-1, 1] float32
    return out_flat / 32767.0
