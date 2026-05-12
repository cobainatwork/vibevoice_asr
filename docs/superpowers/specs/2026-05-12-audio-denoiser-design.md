# Audio Denoiser 設計

> **For agentic workers:** REQUIRED SUB-SKILL: 後續用 `superpowers:writing-plans` 寫實作計畫,再用 `superpowers:subagent-driven-development` 派 subagent 執行。

**目標:** Backend 整合 Audio-Denoiser-ONNX(Apache 2.0)為 ASR 前處理。QC / admin upload / YouTube 來的音檔在進 vLLM 之前可選降噪、提升精度。Dataset 落地用原始音檔(不破 LoRA 訓練料的 noise robustness)。

**架構:** 新增 `app/services/denoiser.py`(ONNX runtime wrapper、cache 兩個模型 GTCRN + ZipEnhancer)。新增 `app/services/audio_preprocessor.py`(orchestration:若 project.denoise_enabled、把音檔 denoise 寫到 temp path、回該 path 給 splitter)。`job_runner.run_transcribe` 在切段前先 call preprocessor。`Project` 加 `denoise_enabled` + `denoise_model` 兩個欄位。Admin UI 在 project 編輯頁加 toggle + 下拉。

**Tech Stack:** onnxruntime(CPU、新依賴)+ numpy(已有)+ ffmpeg(已有)+ Audio-Denoiser-ONNX 模型(Apache 2.0,vendor 進來)。

---

## 1. 動機

### 1.1 Use case

- QC 系統推來的音檔錄製環境品質不一(收音設備 / 背景噪音 / mic 距離等)
- ASR 模型對乾淨音檔精度高、對 noisy 退化
- 加入 denoise pre-processing,讓 vLLM 看到 clean 版、提升辨識精度

### 1.2 為什麼 dataset source 用原始而非 denoised

LoRA fine-tune 的目的是讓 model 學會「對你的領域音檔」的辨識。若 dataset 全是 denoised 乾淨音檔、訓出的 model 對真實 noisy 場景反而退化。**原則:訓練料保留真實聲音分佈**。Denoise 只是 inference-time 前處理。

---

## 2. 範圍

### 2.1 In scope

- Backend ONNX runtime 整合(CPU)
- 2 個模型 vendor 落地:GTCRN(輕量、預設)+ ZipEnhancer(高品質、選用)
- `Project` 加 `denoise_enabled: bool`(預設 False)+ `denoise_model: str`(預設 "gtcrn")
- Alembic migration `0004_project_denoise_settings.py`
- `ProjectIn` / `ProjectPatch` / `ProjectOut` 加欄位
- `app/services/denoiser.py`:ONNX wrapper、`denoise(waveform, sr, model_name)`
- `app/services/audio_preprocessor.py`:orchestration,若 enabled 寫 temp denoised file
- `job_runner.run_transcribe`:呼叫 preprocessor、傳 denoised path 給 splitter
- temp denoised file 清理(job 結束後刪)
- Frontend `ProjectFormModal` 加 toggle + 下拉
- frontend types ProjectOut + ProjectIn + ProjectPatch 同步

### 2.2 Out of scope

- v1 API 端 per-request metadata override(現在 v1 還沒實作、未來再升級成 Hybrid)
- 動態 SNR 偵測決定要不要 denoise
- 模型 ≥ 3 個的選擇空間(目前兩個夠)
- Frontend 端 ONNX Runtime Web(QC 來的音檔不會走 frontend、無意義)
- denoise 結果 audio file 保留(temp file 推論完即刪)
- 對 dataset source 套 denoise(明確 out:dataset 用原始,user 確認)
- denoise 模型 fine-tune(直接用 upstream 預訓練模型)

---

## 3. 決定(已 user 確認)

| # | 議題 | 決定 |
|---|---|---|
| 1 | 整合層 | A:Backend ONNX(覆蓋 QC / admin / YouTube 全部來源) |
| 2 | 啟用策略 | a:預設 off、user 顯式啟用 |
| 3 | Dataset source | i:原始音檔(denoise 只給 vLLM 推論) |
| 4 | 模型選擇 | 兩個都裝:GTCRN(預設、快)+ ZipEnhancer(高品質、選用) |
| 5 | 設定位置 | A:Project 層(`denoise_enabled` + `denoise_model`) |

---

## 4. Data Model

### 4.1 `backend/app/models.py`

`Project` class 加(放在 `webhook_url` / `webhook_secret` 之後):

```python
    denoise_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default=text("0"),
    )
    denoise_model: Mapped[str] = mapped_column(
        String(20), default="gtcrn", nullable=False, server_default=text("'gtcrn'"),
    )
```

### 4.2 Alembic migration `0004_project_denoise_settings.py`

```python
"""project_denoise_settings

Project 加 denoise_enabled + denoise_model 欄位,
讓 admin 在 UI 為每個 project 決定是否啟用 ASR 前處理 denoise + 用哪個模型。

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "denoise_enabled", sa.Boolean(),
            server_default=sa.text("0"), nullable=False,
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "denoise_model", sa.String(20),
            server_default=sa.text("'gtcrn'"), nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "denoise_model")
    op.drop_column("projects", "denoise_enabled")
```

### 4.3 Schema `backend/app/schemas.py`

定義 model 名單(constant、避免散亂):
```python
ALLOWED_DENOISE_MODELS = ("gtcrn", "zipenhancer")
```

`ProjectIn` / `ProjectPatch` 加:
```python
    denoise_enabled: bool | None = None  # ProjectIn 預設 False, ProjectPatch optional
    denoise_model: str | None = None
```

`ProjectOut` 加:
```python
    denoise_enabled: bool
    denoise_model: str
```

驗證:`ProjectIn.denoise_model` 若 set,必須在 `ALLOWED_DENOISE_MODELS`(用 pydantic validator)。

### 4.4 Frontend types

`frontend/src/api/types.ts`:
```typescript
export type DenoiseModel = "gtcrn" | "zipenhancer";

export interface ProjectOut {
  // ... 既有欄位
  denoise_enabled: boolean;
  denoise_model: DenoiseModel;
}

export interface ProjectIn {
  // ... 既有欄位
  denoise_enabled?: boolean;
  denoise_model?: DenoiseModel;
}

export interface ProjectPatch {
  // ... 既有欄位
  denoise_enabled?: boolean;
  denoise_model?: DenoiseModel;
}
```

---

## 5. Service Layer

### 5.1 `app/services/denoiser.py`(新建)

```python
"""
ONNX-based audio denoiser.

兩個模型來自 Audio-Denoiser-ONNX(Apache 2.0):
- GTCRN(輕量、RTF 0.0036、預設)
- ZipEnhancer(高品質、RTF 0.32)

ONNX session 用 module-level cache(Lazy load、跑第一次才 load model file 到 memory)。
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


# Model 檔名 / 配置(對應 vendor/denoiser/ 下檔案)
_MODEL_CONFIGS = {
    "gtcrn": {
        "filename": "gtcrn.onnx",
        "sample_rate": 16000,
        "chunk_size_samples": 16000,  # 1 second chunks
    },
    "zipenhancer": {
        "filename": "zipenhancer.onnx",
        "sample_rate": 16000,
        "chunk_size_samples": 16000,
    },
}


def denoise(waveform: np.ndarray, sr: int, model_name: str = "gtcrn") -> np.ndarray:
    """對 mono float32 waveform 跑 denoise、回 cleaned waveform(same shape)。

    sr 必須與 model 的 sample_rate 一致(目前兩個模型都 16kHz)。
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
    # 分 chunk 跑(模型 STFT 內建處理 boundary)
    chunk_size = cfg["chunk_size_samples"]
    out_chunks = []
    for start in range(0, len(waveform), chunk_size):
        chunk = waveform[start : start + chunk_size]
        # 對最後一個短 chunk pad 到 chunk_size
        if len(chunk) < chunk_size:
            chunk = np.pad(chunk, (0, chunk_size - len(chunk)))
        out = _run_session(session, chunk)
        out_chunks.append(out)
    cleaned = np.concatenate(out_chunks)[: len(waveform)]  # trim padding
    return cleaned.astype(np.float32)


# === Internal helpers ===


def _get_session(model_name: str) -> Any:
    """Lazy-load ONNX InferenceSession,thread-safe。"""
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
        logger.info("denoiser: loading ONNX session model=%s path=%s", model_name, model_path)
        session = ort.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"],
        )
        _session_cache[model_name] = session
        return session


def _model_path(model_name: str) -> Path:
    """ONNX model 檔位置。Mount 進 backend container 的 /vendor 路徑(或 settings 指定)。"""
    settings = get_settings()
    base = Path(settings.denoiser_model_dir)
    cfg = _MODEL_CONFIGS[model_name]
    path = base / cfg["filename"]
    if not path.exists():
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            f"denoise model file not found: {path}",
        )
    return path


def _run_session(session: Any, chunk: np.ndarray) -> np.ndarray:
    """Run ONNX inference on a single chunk。

    每個模型 input/output 名稱不一定相同、用 session.get_inputs() 取。
    """
    input_name = session.get_inputs()[0].name
    # ONNX 通常吃 shape (1, n_samples) — batch=1
    out = session.run(None, {input_name: chunk.reshape(1, -1)})
    return out[0].reshape(-1)
```

**重要實作細節**:
- 兩個模型的 ONNX input/output shape 可能不同,subagent 實作時要用 WebFetch 拿 upstream 的 Python wrapper 例子確認(`get_inputs()[0].shape` / `name`),必要時針對 model 寫不同 `_run_session_for_<model>` 函式。
- chunk size / overlap 也可能依模型不同(GTCRN 1 秒,ZipEnhancer 可能不同)— 先用 1 秒、benchmark 後再調。

### 5.2 `app/services/audio_preprocessor.py`(新建)

```python
"""
ASR pre-processing orchestration: denoise (optional)。

職責跟 splitter 分離 — splitter 不知道輸入是否 denoised、只接 mp3 path。
這層做 denoise + 寫 temp mp3 file、回 caller 新 path。

Caller(job_runner)責任清理 temp file。
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.constants import (
    ASR_AUDIO_CHANNELS, ASR_AUDIO_MP3_QUALITY, ASR_AUDIO_SAMPLE_RATE_HZ,
)
from app.errors import AppError, ErrorCode
from app.services.denoiser import denoise

logger = logging.getLogger(__name__)


def maybe_denoise(
    input_path: Path,
    *,
    denoise_enabled: bool,
    denoise_model: str = "gtcrn",
) -> tuple[Path, bool]:
    """若 enabled,denoise 整段音檔到 temp mp3、回 (新 path, True)。

    Disabled 時直接回 (input_path, False)。
    Caller 必須在 job 結束後刪除 temp file(若 True)。
    """
    if not denoise_enabled:
        return input_path, False

    # 1. ffmpeg → 16kHz mono PCM int16 → numpy float32
    waveform, sr = _load_pcm(input_path)

    # 2. denoise(可能 30s-1hr 視 model + audio 長度)
    logger.info("denoiser: starting %s on %s (%.1fs audio)",
                denoise_model, input_path.name, len(waveform) / sr)
    cleaned = denoise(waveform, sr, model_name=denoise_model)
    logger.info("denoiser: finished %s", denoise_model)

    # 3. 寫 cleaned waveform 回 temp mp3(同 ASR 標準格式 16kHz mono)
    temp_path = _write_denoised_mp3(cleaned, sr)
    return temp_path, True


def cleanup_denoised(temp_path: Path) -> None:
    """刪除 temp denoised file(safe — 失敗不 raise)。"""
    try:
        if temp_path.exists():
            temp_path.unlink()
    except OSError as e:
        logger.warning("cleanup denoised temp file failed: %s (%s)", temp_path, e)


# === Helpers ===


def _load_pcm(input_path: Path) -> tuple[np.ndarray, int]:
    """ffmpeg → PCM int16 → numpy float32。共用 splitter 邏輯。"""
    sr = ASR_AUDIO_SAMPLE_RATE_HZ
    cmd = [
        "ffmpeg", "-v", "error",
        "-i", str(input_path),
        "-vn", "-ar", str(sr), "-ac", "1", "-f", "s16le", "-",
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, timeout=600)
    pcm = np.frombuffer(result.stdout, dtype=np.int16)
    return pcm.astype(np.float32) / 32768.0, sr


def _write_denoised_mp3(waveform: np.ndarray, sr: int) -> Path:
    """numpy float32 → PCM int16 → ffmpeg → mp3 temp file。"""
    settings = get_settings()
    fd, temp_str = tempfile.mkstemp(
        suffix=".mp3", prefix="denoised_", dir=str(settings.upload_dir),
    )
    # close fd immediately;ffmpeg will write
    import os
    os.close(fd)
    temp_path = Path(temp_str)

    pcm_int16 = np.clip(waveform * 32768.0, -32768, 32767).astype(np.int16)

    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "s16le", "-ar", str(sr), "-ac", str(ASR_AUDIO_CHANNELS),
        "-i", "-",  # stdin
        "-c:a", "libmp3lame", "-q:a", str(ASR_AUDIO_MP3_QUALITY),
        str(temp_path),
    ]
    try:
        subprocess.run(
            cmd, input=pcm_int16.tobytes(),
            check=True, capture_output=True, timeout=300,
        )
    except subprocess.CalledProcessError as e:
        temp_path.unlink(missing_ok=True)
        stderr = e.stderr.decode("utf-8", errors="replace")[-500:] if e.stderr else ""
        raise AppError(
            ErrorCode.AUDIO_UNREADABLE,
            f"ffmpeg denoise encode failed: {stderr}",
        ) from e
    return temp_path
```

### 5.3 `app/services/job_runner.py` 整合點

`run_transcribe` 入口附近(取 job + project 之後、call splitter 之前):

```python
async def run_transcribe(job_id: str) -> None:
    async with db_session() as db:
        job = await db.get(Job, job_id)
        # ... 既有取 job + project + 標 RUNNING

    # 新加:audio preprocessing(denoise)
    from app.services.audio_preprocessor import maybe_denoise, cleanup_denoised
    asr_audio_path, was_denoised = maybe_denoise(
        Path(job.audio_path),
        denoise_enabled=project.denoise_enabled,
        denoise_model=project.denoise_model,
    )

    try:
        # splitter / vLLM / merge 都用 asr_audio_path(可能是 denoised temp)
        chunks = split_long_audio(asr_audio_path, ...)
        # ... 既有 transcribe 流程
    finally:
        if was_denoised:
            cleanup_denoised(asr_audio_path)
```

**dataset source 安全保證**:`job.audio_path` 不變、永遠指原始音檔。Dataset 從 job 建立時(`POST /datasets/from_job/{job_id}`)用 `job.audio_path`、不會碰到 denoised 版本。

### 5.4 Settings `app/config.py`

加:
```python
# Audio Denoiser
denoiser_model_dir: str = "/vendor/denoiser"  # docker container 內掛載路徑
```

Docker compose 修 backend / worker service 加 mount:
```yaml
volumes:
  - ./vendor/denoiser:/vendor/denoiser:ro
```

---

## 6. Model File 落地

### 6.1 取得來源

從 `https://github.com/DakeQQ/Audio-Denoiser-ONNX` repo 找 ONNX 檔案(可能放 release / HF / repo 內):
- `gtcrn.onnx`
- `zipenhancer.onnx`

Subagent 實作 task 時要先 WebFetch 確認檔案位置(repo `models/` 子目錄 / HuggingFace mirror / release asset)、取得 download URL。

### 6.2 儲存位置

`vendor/denoiser/gtcrn.onnx` 跟 `vendor/denoiser/zipenhancer.onnx`,**不 commit 進 git**(file 大、可能 50-200MB)。寫 `vendor/denoiser/README.md` 紀錄取得方式 + Apache 2.0 attribution、`.gitignore` 排除 `*.onnx`。

```
vendor/denoiser/
├── README.md          # commit
├── .gitignore         # commit, ignore *.onnx
├── gtcrn.onnx         # not committed
└── zipenhancer.onnx   # not committed
```

`scripts/download_denoiser_models.sh`(commit):wget / curl 從 upstream 拉 model file 到 `vendor/denoiser/`,user setup 跑一次。

### 6.3 License

Audio-Denoiser-ONNX Apache 2.0、`LICENSES/audio-denoiser.LICENSE.md` 紀錄 attribution(類似前面 audio-slicer 處理)。

Model 自己的 license 需個別確認(model 通常 follow 訓練資料 license、不一定跟 wrapper code 同):
- GTCRN — 原 paper / 上游 model
- ZipEnhancer — 原 paper / 上游 model

subagent 實作時順便確認每個 model 的 origin + license,寫進 README。

---

## 7. Dependencies

### 7.1 Backend pyproject.toml

```toml
onnxruntime = "^1.18.0"
```

CPU 版(`onnxruntime`)、不裝 `onnxruntime-gpu`(訓練要 GPU、推論 CPU 跑 denoise 是設計)。

### 7.2 影響 backend image size

- `onnxruntime`(CPU)約 30-40 MB
- Model files mount(`-v` 不進 image)、image 不變大
- 整體 backend image 預估 +50 MB(onnxruntime + dependencies)

---

## 8. Frontend `ProjectFormModal`

Read 既有 `frontend/src/components/ProjectFormModal.tsx` 看結構。加兩個 form field:

```tsx
{/* 啟用降噪 toggle */}
<label className="flex items-center gap-2">
  <input
    type="checkbox"
    checked={formData.denoise_enabled ?? false}
    onChange={(e) => setFormData({ ...formData, denoise_enabled: e.target.checked })}
  />
  <span className="text-sm">啟用降噪(ASR 前處理)</span>
</label>

{/* 模型選擇下拉(僅在 denoise_enabled 時顯示)*/}
{formData.denoise_enabled && (
  <div>
    <label className="block text-sm">降噪模型</label>
    <select
      value={formData.denoise_model ?? "gtcrn"}
      onChange={(e) => setFormData({
        ...formData, denoise_model: e.target.value as DenoiseModel,
      })}
      className="block w-full mt-1 border rounded px-2 py-1 text-sm"
    >
      <option value="gtcrn">GTCRN(輕量、快、品質基本可用)</option>
      <option value="zipenhancer">ZipEnhancer(高品質、慢約 100×)</option>
    </select>
    <p className="text-xs text-slate-500 mt-1">
      預設關閉。降噪僅用於 ASR 推論、不影響 dataset 落地的原始音檔。
    </p>
  </div>
)}
```

---

## 9. 測試策略

### 9.1 Backend

| 檔 | 範圍 |
|---|---|
| `test_denoiser.py`(新)| mock `onnxruntime.InferenceSession`、驗 denoise() chunk + concat 邏輯;invalid model name 拋 AppError;sr 不匹配拋 AppError |
| `test_audio_preprocessor.py`(新)| mock `denoise()` + ffmpeg subprocess;驗 disabled 直接回原 path;enabled 寫 temp file 回新 path;cleanup_denoised 安全刪 |
| `test_routes_projects.py`(改 / 既有)| ProjectIn / ProjectOut 加欄位後驗 POST / PATCH 帶 denoise_enabled + denoise_model 正確存進 DB |
| `test_models_project.py`(可能新)| Project.denoise_enabled default False / denoise_model default "gtcrn" |

### 9.2 Integration test

mock denoiser、整段 `run_transcribe` 走通:project.denoise_enabled=True 時 splitter 接到 temp denoised path、job 完後 temp file 刪掉。

### 9.3 Frontend

- typecheck + lint 0 errors
- 無 unit test 框架(既往)、實機看 ProjectFormModal 兩個欄位顯示正確

---

## 10. 邊界 case

| 情境 | 處理 |
|---|---|
| Model file 不存在(setup 沒下載)| `_model_path` raise AppError、job 標 FAILED、UI 看到錯誤 |
| Onnxruntime import 失敗(image build 漏裝)| `_get_session` raise AppError |
| denoise 中 onnx session run 失敗(模型 input shape 不對)| ONNX exception 包 AppError raise、job FAILED |
| denoise 後音檔極小 / 全靜音 | 仍寫 temp file、splitter 走 fallback 固定切 |
| temp file 寫到一半 process kill | 重啟後 stale temp 在 `data/uploads/` 內、需要 startup cleanup job 或無視(file 大但少) |
| project.denoise_model 設成不存在的值 | schema validator 擋(ALLOWED_DENOISE_MODELS)、API 400 |
| 既有 Project 沒 denoise_enabled / denoise_model 欄位 | server_default 補預設 (`False` / `"gtcrn"`) |

---

## 11. 完成條件

- [ ] `Project` 加 2 欄位 + Alembic migration 0004
- [ ] `ProjectIn` / `ProjectPatch` / `ProjectOut` schema 加欄位 + validator
- [ ] `app/services/denoiser.py` 新建、含 GTCRN + ZipEnhancer 推論邏輯
- [ ] `app/services/audio_preprocessor.py` 新建、含 maybe_denoise + cleanup_denoised
- [ ] `job_runner.run_transcribe` 整合 preprocessor
- [ ] `app/config.py` 加 denoiser_model_dir
- [ ] `docker-compose.yml` backend / worker 加 `./vendor/denoiser` mount
- [ ] `vendor/denoiser/README.md` + `.gitignore` 紀錄取得方式
- [ ] `scripts/download_denoiser_models.sh` 自動下載 model file
- [ ] `LICENSES/audio-denoiser.LICENSE.md` Apache 2.0 attribution
- [ ] `backend/pyproject.toml` 加 onnxruntime
- [ ] `frontend/src/api/types.ts` ProjectOut / ProjectIn / ProjectPatch 加欄位
- [ ] `frontend/src/components/ProjectFormModal.tsx` 加 toggle + 下拉
- [ ] backend pytest / ruff / mypy / bandit 全綠
- [ ] frontend typecheck / lint 0 errors
- [ ] 實機:disable 時 ASR 行為不變;enable + noisy 音檔時 ASR 精度有提升

---

## 12. 不變條件(Non-Goals)

- 不影響 dataset 落地音檔(Job.audio_path 永遠指原始)
- 不改 vLLM client / parser / merge 邏輯
- 不對 dataset training pipeline 套 denoise
- v1 API metadata override 暫不做(留將來)
- 不對既有 silence_slicer 路徑造成 regression(denoise 是 splitter 之前的獨立 stage)
- onnxruntime-gpu 不裝(降低 image 複雜度)
