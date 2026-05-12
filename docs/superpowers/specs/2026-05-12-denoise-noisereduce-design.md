# Denoise 改用 noisereduce 設計

> **For agentic workers:** REQUIRED SUB-SKILL: 後續用 `superpowers:writing-plans` 寫 plan、再用 `superpowers:subagent-driven-development` 派 subagent 執行。
>
> **Supersedes:** `docs/superpowers/specs/2026-05-12-audio-denoiser-design.md`(ONNX path)— 該方案實機 ONNX input spec 不符、放棄。本 spec 為新實作路徑。

**目標:** 把 denoise 實作換成 [`noisereduce`](https://github.com/timsainb/noisereduce)(純 numpy + scipy、無 model file、API 簡單)。保留 `Project.denoise_enabled` toggle + 既有 API 介面、只換內部實作。廢棄 ONNX 相關 dependencies / mount / model file。

**架構:** `app/services/denoiser.py` 完全重寫成 noisereduce wrapper。`app/services/audio_preprocessor.py` 介面不變(`maybe_denoise(path, denoise_enabled, denoise_model)` 簽名保留),只是內部不再分 model、統一用 noisereduce。`Project.denoise_model` 欄位 deprecate 不刪、API 不再暴露、backend 不讀。

**Tech Stack:** `noisereduce`(pip 純 Python)+ numpy(已有)+ scipy(noisereduce 依賴、自動裝)+ ffmpeg(已有)。**移除** onnxruntime。

---

## 1. 動機

### 1.1 為什麼放棄 ONNX path

實機部署 `gtcrn.onnx` + `zipenhancer.onnx` 確認:

- 兩個 ONNX 都是 **STFT-based** 模型(不接 raw waveform、需要 magnitude/phase 分開 input)
- GTCRN 是 **streaming 版本**,還要 3 個 hidden state cache 接力
- 即使重寫 wrapper 支援 STFT,參數(`win_length` / `hop_length` / window type)無 metadata 揭露,試錯成本高、品質未必對

ONNX path 工程成本超出價值,放棄。

### 1.2 為什麼選 noisereduce

| 項目 | noisereduce |
|---|---|
| 演算法 | non-stationary spectral gating(基於 noise profile)|
| 依賴 | numpy + scipy(都已內含 / scipy 是 noisereduce dep)|
| Model file | 無 |
| API | `reduce_noise(y, sr, stationary=False) -> ndarray` 一行 |
| 速度 | RTF ~ 0.01-0.05(CPU、整段音檔) |
| 品質 | 對「穩定背景噪音」(office、訪談、空調聲)強 |
| 安裝 | `pip install noisereduce`、無 C binding |

對 QC 場景(office 訪談錄音、中等背景噪音)足夠用。極端 noisy 場景(突發雜音、強回音)需要更強 model,屆時再評估。

### 1.3 為什麼不直接刪 denoise feature

`Project` schema 已加 `denoise_enabled` + `denoise_model`、`ProjectFormModal` 已加 UI、`job_runner` 已整合 maybe_denoise。**接口不動、只換內部實作**,user / API 端零變動。

---

## 2. 範圍

### 2.1 In scope

- 替換 `app/services/denoiser.py` 為 noisereduce wrapper
- 不分 model — `denoise_model` 參數仍接受但忽略(maybe_denoise 內部直接 call noisereduce)
- 移除 `onnxruntime` dependency
- 移除 `docker-compose.yml` vendor/denoiser mount
- 移除 `config.py` `denoiser_model_dir` 設定
- 刪 `vendor/denoiser/` 目錄(README + .gitignore + onnx 模型若有 mount)
- 刪 `LICENSES/audio-denoiser.LICENSE.md`
- 刪 `scripts/download_denoiser_models.sh`
- 改寫 `backend/tests/test_denoiser.py` 為 noisereduce 行為(無 ONNX mock)
- `audio_preprocessor.py` 介面不動(maybe_denoise / cleanup_denoised 簽名)
- `ProjectFormModal` UI 拿掉「降噪模型」下拉、只留「啟用降噪」toggle
- `Project.denoise_model` DB 欄位**保留**(向後相容、不做 migration drop)
- `ProjectIn` / `ProjectPatch` / `ProjectOut` schema 拿掉 `denoise_model`(API 不再暴露)
- `frontend/src/api/types.ts` `DenoiseModel` type alias 移除、interfaces 拿掉 denoise_model
- 既有 project 設過 denoise_model 的值:無影響(backend 不讀、API 不回)

### 2.2 Out of scope

- 自訂 noisereduce 參數(`prop_decrease` / `n_std_thresh_stationary` 等)— 用預設值,品質不夠用再開新議題加 settings
- 多 model 切換(rnnoise / DeepFilterNet)— YAGNI、未來真需要再加
- 對 dataset audio 套 noisereduce(明確 out:dataset 用原始、規範跟原 spec 一致)
- v1 API 對外 expose denoise 行為(QC 端只感受到 ASR 精度差異、不該知道內部 pre-process)
- ONNX model file 跟 audio-denoiser-onnx 上游程式 — 不關注、視為失敗實驗
- denoise_model 欄位的 Alembic drop migration(留 backward compat、未來確定不用再開 0005)

---

## 3. 決定

### 3.1 跟原 ONNX spec 對齊保留

| 項目 | 維持原設計 |
|---|---|
| 啟用策略 | 預設 off、user 顯式開 |
| Dataset source | 原始音檔(denoise 只給 vLLM 推論) |
| 設定位置 | Project 層(`denoise_enabled` boolean) |
| 整合層 | Backend `audio_preprocessor` 在 splitter 前跑 |
| 臨時 file 清理 | try/finally cleanup_denoised |

### 3.2 跟原 ONNX spec 不同

| 項目 | 改變 |
|---|---|
| 實作 backend | noisereduce 取代 onnxruntime |
| 模型選擇 | 取消(只一個方案,不分 model)|
| Project.denoise_model | DB 欄位保留,API / UI 不再暴露 |
| docker mount | 移除 vendor/denoiser |
| Model file 取得 | 不需要 |

---

## 4. Service Layer

### 4.1 `app/services/denoiser.py` 完全重寫

```python
"""
Audio denoiser — noisereduce wrapper。

純 numpy + scipy,無 ONNX model file。對 QC 場景的穩定背景噪音
(office / 訪談 / 空調聲)效果好;極端突發雜音不在範圍。

替換原 ONNX path(audio-denoiser-onnx)— 該方案實機 ONNX input spec
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

    model_name 參數保留向後相容(原 ONNX path 簽名),目前忽略 —
    只有單一 noisereduce 實作。

    waveform shape (n_samples,) float32 [-1, 1]。
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

    # noisereduce 對長音檔記憶體可承受;internal chunking by spectral gates。
    cleaned = nr.reduce_noise(
        y=waveform,
        sr=sr,
        stationary=False,  # non-stationary:自適應 noise profile
    )
    return cleaned.astype(np.float32)
```

簡化重點:
- 移除 `_session_cache` / `_get_session` / `_MODEL_CONFIGS` / `_run_session` 等 ONNX 相關
- `model_name` 參數**保留**(audio_preprocessor 既有 caller 仍會傳)但 ignored
- 不需 lazy load(noisereduce import 輕量)

### 4.2 `app/services/audio_preprocessor.py` 改動極小

接口完全不動,只內部 call 不再分 model:

```python
def maybe_denoise(
    input_path: Path,
    *,
    denoise_enabled: bool,
    denoise_model: str = "gtcrn",  # 接受但忽略,向後相容
) -> tuple[Path, bool]:
    if not denoise_enabled:
        return input_path, False

    waveform, sr = _load_pcm(input_path)
    logger.info("denoiser: starting on %s (%.1fs audio)",
                input_path.name, len(waveform) / sr)
    cleaned = denoise(waveform, sr)  # 不傳 model_name
    logger.info("denoiser: finished")

    temp_path = _write_denoised_mp3(cleaned, sr)
    return temp_path, True
```

`cleanup_denoised` / `_load_pcm` / `_write_denoised_mp3` 不動。

---

## 5. Dependencies

### 5.1 backend/pyproject.toml

**移除**:
```toml
onnxruntime = "^1.18.0"  # 廢棄
```

**新增**:
```toml
noisereduce = "^3.0.0"
```

scipy 是 noisereduce dep、自動裝。

### 5.2 docker-compose.yml

**移除** backend 跟 worker 的 mount:
```yaml
- ./vendor/denoiser:/vendor/denoiser:ro  # 廢棄
```

### 5.3 config.py

**移除**:
```python
denoiser_model_dir: str = "/vendor/denoiser"  # 廢棄
```

---

## 6. Schema / API 變動

### 6.1 backend/app/schemas.py

**移除** `ALLOWED_DENOISE_MODELS` 常數。

`ProjectIn` / `ProjectPatch` / `ProjectOut` **拿掉** `denoise_model` 欄位:
```python
class ProjectIn(BaseModel):
    # ... 既有
    denoise_enabled: bool = False
    # denoise_model 已移除

class ProjectPatch(BaseModel):
    # ... 既有
    denoise_enabled: bool | None = None
    # denoise_model 已移除

class ProjectOut(BaseModel):
    # ... 既有
    denoise_enabled: bool
    # denoise_model 已移除
```

`field_validator("denoise_model")` 也移除。

### 6.2 DB 欄位處理

`Project.denoise_model` **不刪、不 migration**。理由:
- 既有 prod data 可能已寫入(雖然應該都是預設值)
- 留 backward compat,未來確定不用再 0005 drop

backend 不讀 `project.denoise_model`、ORM 仍 reflect 但無 caller。

### 6.3 frontend types

`frontend/src/api/types.ts`:
- 移除 `export type DenoiseModel = "gtcrn" | "zipenhancer";`
- `ProjectOut` / `ProjectIn` / `ProjectPatch` 拿掉 `denoise_model` 欄位

---

## 7. Frontend UI

### 7.1 `ProjectFormModal.tsx`

zod schema:
```typescript
// 移除 denoise_model
denoise_enabled: z.boolean().optional(),
```

formData state interface 移除 `denoise_model`。

UI block 簡化(plan §7 Step 6 對齊):
```tsx
<div className="border-t pt-3 mt-3">
  <label className="flex items-center gap-2 cursor-pointer">
    <input
      type="checkbox"
      {...register("denoise_enabled")}
      className="cursor-pointer"
    />
    <span className="text-sm text-slate-700">啟用降噪(ASR 前處理)</span>
  </label>
  <p className="text-xs text-slate-500 mt-2 ml-6">
    用 noisereduce 對音檔做 spectral gating 降噪。對穩定背景噪音
   (office / 訪談 / 空調聲)效果好。僅用於 ASR 推論、不影響 dataset
    落地的原始音檔。
  </p>
</div>
```

拿掉:
- `denoiseEnabled` watch
- `denoise_model` register
- `<select>` block
- 「降噪模型」label / option / 警告文字

submit 也不傳 `denoise_model`(zod schema 已移除)。

---

## 8. 砍掉的 Files

| Path | 動作 |
|---|---|
| `vendor/denoiser/README.md` | 刪 |
| `vendor/denoiser/.gitignore` | 刪 |
| `vendor/denoiser/` 整個目錄 | 刪(若有 onnx 留 Linux 端就放著、不影響) |
| `LICENSES/audio-denoiser.LICENSE.md` | 刪 |
| `scripts/download_denoiser_models.sh` | 刪 |

`docs/superpowers/specs/2026-05-12-audio-denoiser-design.md` **保留**(歷史紀錄、標 supersededed)。
`docs/superpowers/plans/2026-05-12-audio-denoiser.md` **保留**(同樣歷史紀錄)。

---

## 9. 測試

### 9.1 Backend

| 檔 | 範圍 |
|---|---|
| `test_denoiser.py` 改寫 | mock `noisereduce.reduce_noise`(或不 mock、純 numpy 跑小 array、test 速度可接受);驗 raw → cleaned 流程、ndim 檢查、ImportError handling |
| `test_audio_preprocessor.py` | 改動極小(mock 路徑相同),確認 `denoise_model` 參數仍接受但不影響行為 |
| `test_job_runner_denoise.py` | mock denoiser、driver 流程不動 |
| `test_routes_projects.py` | 改:`denoise_model` 不在 ProjectOut response、`POST /projects` 不接 denoise_model;若 user 帶 denoise_model 不會 422(只是 extra field 被 ignored 或 422 — 看 pydantic config) |

### 9.2 Frontend

- typecheck / lint 0 errors
- UI 手動驗:ProjectFormModal 只顯示 toggle、無下拉

### 9.3 不做的

- noisereduce 本身的演算法 unit test(vendor 黑箱)
- 對各種音檔的 denoise 品質 SNR 量測(實機觀察)

---

## 10. 遷移注意

### 10.1 既有 Project rows

- `denoise_enabled` 仍存在、值不變
- `denoise_model` DB 欄位仍存在、值不變(`"gtcrn"` / `"zipenhancer"` 都可能)
- API 不再回 / 不再接受該欄位、user 看不到、無感

### 10.2 既有 Job(已用 denoise 處理過的)

實機驗證階段 user 沒有成功 denoise 過(ONNX 都炸),所以無歷史影響。

### 10.3 既有 .env / docker-compose

`docker compose down` 後改 `docker-compose.yml` 移除 mount、重 build。沒有需要保留的 stateful data。

---

## 11. 完成條件

- [ ] `backend/app/services/denoiser.py` 完全重寫為 noisereduce wrapper
- [ ] `backend/app/services/audio_preprocessor.py` 簽名不變、內部不傳 model_name
- [ ] `backend/pyproject.toml` 移 onnxruntime、加 noisereduce
- [ ] `docker-compose.yml` 移 vendor/denoiser mount
- [ ] `backend/app/config.py` 移 denoiser_model_dir
- [ ] `backend/app/schemas.py` ProjectIn / ProjectPatch / ProjectOut 拿掉 denoise_model + 移 ALLOWED_DENOISE_MODELS
- [ ] `frontend/src/api/types.ts` 拿掉 DenoiseModel + denoise_model fields
- [ ] `frontend/src/components/ProjectFormModal.tsx` 拿掉下拉、只 toggle
- [ ] `frontend/src/pages/Projects.tsx` 對齊 type changes
- [ ] 刪 `vendor/denoiser/` 目錄、`LICENSES/audio-denoiser.LICENSE.md`、`scripts/download_denoiser_models.sh`
- [ ] `backend/tests/test_denoiser.py` 改寫 noisereduce 行為
- [ ] `backend/tests/test_audio_preprocessor.py` 對齊
- [ ] `backend/tests/test_routes_projects.py` 改 denoise_model 相關 test(刪 / 改)
- [ ] backend pytest / ruff / mypy / bandit 全綠
- [ ] frontend typecheck / lint 0 errors
- [ ] 實機:啟用降噪 + 上傳音檔 → backend log 印 `denoiser: starting...` + `denoiser: finished`、ASR 跑完、temp file 清掉

---

## 12. 不變條件(Non-Goals)

- v1 API metadata override 暫不做(留將來 Hybrid)
- 動態 SNR 偵測決定要不要 denoise
- noisereduce 進階參數調整(stationary mode / threshold)— YAGNI
- 對 dataset audio 套 denoise(明確不做)
- 多 backend(rnnoise / DeepFilterNet)切換 — YAGNI、user 真需要再說
