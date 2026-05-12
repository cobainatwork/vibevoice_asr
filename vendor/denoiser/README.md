# Denoiser ONNX Models

ONNX 模型來自 [Audio-Denoiser-ONNX](https://github.com/DakeQQ/Audio-Denoiser-ONNX)
(Apache 2.0)。本目錄不 commit 模型本體 (file 大、50-200 MB)，需 setup 時下載。

## Models

| File | Source | Size (approx) | License |
|---|---|---|---|
| `GTCRN.onnx` | 需手動從 upstream 取得，放至本目錄。見下方說明。 | ~10-50 MB | Apache 2.0 (wrapper)；model weights 依原始論文 |
| `ZipEnhancer.onnx` | 需手動從 upstream 取得，放至本目錄。見下方說明。 | ~50-200 MB | Apache 2.0 (wrapper)；model weights 依原始論文 |

> **WARNING**: `https://github.com/DakeQQ/Audio-Denoiser-ONNX` 目前無 GitHub release
> 也無公開 HuggingFace 直連 URL。需手動 export 或聯絡 upstream 取得 ONNX 檔。

## 取得方式

### 方法 1：從 upstream repo export (推薦)

```bash
git clone https://github.com/DakeQQ/Audio-Denoiser-ONNX.git /tmp/audio-denoiser
# GTCRN
cd /tmp/audio-denoiser/GTCRN
pip install onnxruntime onnx
python Export_GTCRN.py
cp GTCRN_Optimized/GTCRN.onnx /path/to/vibevoice_asr/vendor/denoiser/GTCRN.onnx
# ZipEnhancer
cd /tmp/audio-denoiser/ZipEnhancer
python Export_ZipEnhancer.py
cp ZipEnhancer_Optimized/ZipEnhancer.onnx /path/to/vibevoice_asr/vendor/denoiser/ZipEnhancer.onnx
```

### 方法 2：使用 download script (若 URL 可取得時)

```bash
bash scripts/download_denoiser_models.sh
```

目前 script 內 URL 為 placeholder，需在 upstream 提供直連 URL 後更新。

## Model 技術規格

| 項目 | GTCRN | ZipEnhancer |
|---|---|---|
| Sample rate | 16000 Hz | 16000 Hz |
| Input shape | (1, 1, n_samples) int16 | (1, 1, n_samples) int16 |
| Chunk size | 480,000 samples (30s) | 96,000 samples (6s) |
| RTF (CPU) | ~0.0036 | ~0.32 |
| 用途 | 輕量預設、快速 | 高品質、較慢 |

## License

Apache 2.0 — 見 `LICENSES/audio-denoiser.LICENSE.md`
