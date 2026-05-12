# Denoise 改用 noisereduce 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 `superpowers:subagent-driven-development` 派 subagent 執行。

**Goal:** 把 denoise 實作從 ONNX(audio-denoiser-onnx)切換到 `noisereduce`。保留 Project 設定介面、API 不破。砍掉 onnxruntime / vendor model file / docker mount。

**Spec Reference:** `docs/superpowers/specs/2026-05-12-denoise-noisereduce-design.md`

---

## Task 切分

| Task | 範圍 |
|---|---|
| 1 | Backend:denoiser.py 重寫 + audio_preprocessor 小調 + pyproject + config + schemas + tests + 清除 ONNX 殘餘 file |
| 2 | Frontend:types + ProjectFormModal + Projects.tsx 對齊 |

---

## Task 1:Backend 換 noisereduce + 清 ONNX 殘餘

**Files(完整清單)**:
- Modify: `backend/app/services/denoiser.py`(完全重寫)
- Modify: `backend/app/services/audio_preprocessor.py`(內部不傳 model_name)
- Modify: `backend/pyproject.toml`(移 onnxruntime、加 noisereduce)
- Modify: `backend/app/config.py`(移 denoiser_model_dir)
- Modify: `backend/app/schemas.py`(ProjectIn/Patch/Out 拿 denoise_model、移 ALLOWED_DENOISE_MODELS)
- Modify: `docker-compose.yml`(backend + worker 各 1 處 vendor/denoiser mount 移除)
- Modify: `backend/tests/test_denoiser.py`(改 noisereduce mock)
- Modify: `backend/tests/test_audio_preprocessor.py`(對齊 model_name 不影響行為)
- Modify: `backend/tests/test_routes_projects.py`(刪 / 改 denoise_model 相關 test)
- Delete: `vendor/denoiser/README.md`
- Delete: `vendor/denoiser/.gitignore`(整個 vendor/denoiser 目錄空了可刪)
- Delete: `LICENSES/audio-denoiser.LICENSE.md`
- Delete: `scripts/download_denoiser_models.sh`

### Steps

- [ ] **Step 1: Read 既有檔**

確認當前狀態:
- `backend/app/services/denoiser.py`(目前 ONNX 邏輯、要全砍)
- `backend/app/services/audio_preprocessor.py`(maybe_denoise 內部 denoise() call)
- `backend/app/schemas.py`(ProjectIn/Patch/Out + ALLOWED_DENOISE_MODELS)
- `backend/pyproject.toml`([tool.poetry.dependencies])
- `docker-compose.yml`(backend / worker 的 vendor/denoiser mount)
- `backend/tests/test_denoiser.py`(現有 4 條 ONNX mock test)

- [ ] **Step 2: 完全重寫 `denoiser.py`**

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
```

完全取代既有 denoiser.py 內容。

- [ ] **Step 3: 改 `audio_preprocessor.py`**

只需 1 行改動 — `cleaned = denoise(waveform, sr, model_name=denoise_model)` 改成 `cleaned = denoise(waveform, sr)`(不再傳 model_name)。

但 spec 內 denoise() 簽名仍接受 model_name 為 keyword、向後相容。所以**最小改動**:不改 audio_preprocessor.py、現有 call 仍可 work(`model_name` 被 ignore)。

如果要更乾淨可選改:把 audio_preprocessor 內 call 改成 `denoise(waveform, sr)` 對齊新簽名。**建議改**(明確意圖、避免未來迷惑)。

- [ ] **Step 4: 改 `pyproject.toml`**

`[tool.poetry.dependencies]` 移:
```toml
onnxruntime = "^1.18.0"
```

加:
```toml
noisereduce = "^3.0.0"
```

不動 `poetry.lock`(user Linux 端 build 時 resolve)。

- [ ] **Step 5: 改 `config.py`**

移 `denoiser_model_dir: str = "/vendor/denoiser"`。Read 確認位置、Edit 刪。

- [ ] **Step 6: 改 `schemas.py`**

移除:
- `ALLOWED_DENOISE_MODELS = ("gtcrn", "zipenhancer")` 常數
- `ProjectIn.denoise_model` 欄位 + `_check_denoise_model` validator
- `ProjectPatch.denoise_model` 欄位 + validator
- `ProjectOut.denoise_model` 欄位

保留 `denoise_enabled` 三處不動。

- [ ] **Step 7: 改 `docker-compose.yml`**

backend service `volumes:` 移:
```yaml
- ./vendor/denoiser:/vendor/denoiser:ro
```

worker service `volumes:` 同樣移。

- [ ] **Step 8: 改 `test_denoiser.py`**

完全重寫(現有 ONNX mock test 都不適用):
```python
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
```

不 mock noisereduce — 純 numpy 跑短 array,速度可接受。

- [ ] **Step 9: 改 `test_audio_preprocessor.py`**

既有 test 應該大致 work(maybe_denoise 簽名不變)。Read 確認:
- `test_maybe_denoise_disabled_returns_original` — 不變
- `test_maybe_denoise_enabled_writes_temp` — mock denoise 邏輯不變、call args 可能要對齊
- `test_cleanup_denoised_*` — 不變

如果有 test 假設 `denoise()` call 帶 `model_name=` keyword,改成不帶。

- [ ] **Step 10: 改 `test_routes_projects.py`**

既有 4 條 denoise test:
- `test_create_project_with_denoise_settings` — 改成只測 `denoise_enabled`、拿掉 `denoise_model`
- `test_create_project_default_denoise` — 改 assert 只 check `denoise_enabled is False`(`denoise_model` 已不在 response)
- `test_create_project_invalid_denoise_model` — **刪除**(denoise_model 不在 schema 不會 422)
- `test_patch_project_denoise` — 改成 patch 只 `denoise_enabled`

- [ ] **Step 11: 刪除廢棄 file**

```
git -C /d/vibevoice_asr rm vendor/denoiser/README.md
```

```
git -C /d/vibevoice_asr rm vendor/denoiser/.gitignore
```

```
git -C /d/vibevoice_asr rm LICENSES/audio-denoiser.LICENSE.md
```

```
git -C /d/vibevoice_asr rm scripts/download_denoiser_models.sh
```

若 `vendor/denoiser/` 目錄空了,git 不會把空目錄列追蹤、`git status` 應該乾淨。

- [ ] **Step 12: Commit + push**

```
git -C /d/vibevoice_asr add backend/app/services/denoiser.py backend/app/services/audio_preprocessor.py backend/pyproject.toml backend/app/config.py backend/app/schemas.py docker-compose.yml backend/tests/test_denoiser.py backend/tests/test_audio_preprocessor.py backend/tests/test_routes_projects.py
```

```
git -C /d/vibevoice_asr commit -m "feat(denoise): 換 noisereduce 取代 onnxruntime + 清 ONNX 殘餘"
```

```
git -C /d/vibevoice_asr push
```

---

## Task 2:Frontend 對齊 schema 變動

**Files:**
- Modify: `frontend/src/api/types.ts`(移 DenoiseModel + 三個 interface 拿掉 denoise_model)
- Modify: `frontend/src/components/ProjectFormModal.tsx`(拿掉下拉、留 toggle)
- Modify: `frontend/src/pages/Projects.tsx`(若 callback type 含 denoise_model 拿掉)

### Steps

- [ ] **Step 1: 改 `types.ts`**

移除:
```typescript
export type DenoiseModel = "gtcrn" | "zipenhancer";
```

`ProjectOut` / `ProjectIn` / `ProjectPatch` 拿掉:
```typescript
denoise_model: DenoiseModel;  // 或 denoise_model?: DenoiseModel
```

只留 `denoise_enabled` 三處不動。

- [ ] **Step 2: 改 `ProjectFormModal.tsx`**

完整修改步驟:

(a) zod schema 移 `denoise_model`:
```typescript
denoise_enabled: z.boolean().optional(),
// denoise_model 移除
```

(b) state interface(若有)移 `denoise_model`

(c) reset() initial 移 `denoise_model: (initial?.denoise_model ?? "gtcrn") as DenoiseModel,`

(d) submit values 不再傳 `denoise_model`

(e) `denoiseEnabled = watch("denoise_enabled")` 拿掉(因為下拉沒了、條件 render 不必要)

(f) UI block 改成簡化版本:
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
- `{denoiseEnabled && (` 條件 block
- `<select {...register("denoise_model")}>`
- 兩個 `<option>` GTCRN / ZipEnhancer
- 「降噪模型」label
- 「預設關閉。降噪僅用於 ASR 推論...」既有文字(被新文字取代)

import 也要清:`DenoiseModel` 若有 import、移掉。

- [ ] **Step 3: 改 `Projects.tsx`(若需要)**

Read 確認 `onCreate` / `onEdit` callback 簽名是否含 `denoise_model`。若有,拿掉。

- [ ] **Step 4: typecheck + lint**

```
npm --prefix /d/vibevoice_asr/frontend run typecheck
```

```
npm --prefix /d/vibevoice_asr/frontend run lint
```

兩者必須 PASS。

- [ ] **Step 5: Commit + push**

```
git -C /d/vibevoice_asr add frontend/src/api/types.ts frontend/src/components/ProjectFormModal.tsx frontend/src/pages/Projects.tsx
```

```
git -C /d/vibevoice_asr commit -m "feat(denoise): frontend 拿掉 denoise_model 下拉、只留 enabled toggle"
```

```
git -C /d/vibevoice_asr push
```

---

## 完成後驗證(user Linux 端)

```
git pull
```

```
docker compose build backend worker frontend
```

```
docker compose up -d backend worker frontend
```

不需要再 mount model file、不需要 alembic upgrade(沒新 migration、`denoise_model` DB 欄位保留但 API 不暴露)。

```
docker compose exec backend pytest -v
```

```
docker compose exec backend ruff check app/
```

```
docker compose exec backend mypy app/
```

```
docker compose exec backend bandit -r app/ -ll
```

### 實機

1. 進 admin UI → project 編輯 → 應看到「啟用降噪」toggle、**沒有**降噪模型下拉
2. 勾「啟用降噪」、儲存
3. 上傳一支 noisy 音檔
4. worker log 應印:
   - `denoiser: starting on <filename> (Ns audio)`
   - `denoiser: finished`
5. ASR 跑完、Editor 看到 segments
6. `data/uploads/denoised_*.mp3` job 結束後應已刪
7. 對比舊版同支音檔(取消勾「啟用降噪」再跑一次)— 降噪版 ASR 精度應該 ≥ 原版(SNR 高的場景沒差、SNR 低的場景應該有提升)

---

## Risks

| 風險 | 緩解 |
|---|---|
| noisereduce 對某些音檔反而降低 ASR 精度 | 預設 off、user 自選、QC 場景測試後決定預設 |
| noisereduce CPU 對極長音檔慢 | RTF 0.01-0.05、3hr 音檔 ~ 10 分鐘、可接受 |
| 既有 project 有 `denoise_model="zipenhancer"` 值留在 DB | DB 欄位仍存、不影響;backend / API 完全不讀 |
| 砍 onnxruntime / vendor 後 user 困惑「ONNX 模型還留著嗎」 | spec / commit message 標清楚 |

---

## Plan Self-Review

- [x] 兩個 task 依賴明確(Task 1 backend schema change 影響 Task 2 frontend)
- [x] denoise_enabled API 介面不變、user / SDK 無感
- [x] 既有 Job 處理流程不變(maybe_denoise 簽名不變)
- [x] 完成條件對應 spec §11
