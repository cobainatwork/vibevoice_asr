# Audio Denoiser 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 `superpowers:subagent-driven-development` 逐 task 派 subagent 執行。

**Goal:** Backend 整合 Audio-Denoiser-ONNX(Apache 2.0)兩個模型(GTCRN + ZipEnhancer),Project 設定切換。Dataset source 用原始音檔、denoise 只給 vLLM 推論。

**Spec Reference:** `docs/superpowers/specs/2026-05-12-audio-denoiser-design.md`

---

## Task 切分

| Task | 範圍 | 依賴 |
|---|---|---|
| 1 | Backend data model + migration + schema validator + ProjectIn/Patch/Out + frontend types + ProjectFormModal UI | — |
| 2 | denoiser service + audio_preprocessor + onnxruntime 依賴 + docker-compose mount + vendor/denoiser scaffold + LICENSES + 下載 script | Task 1 |
| 3 | job_runner 整合 + tests + 實機驗證準備 | Task 2 |

---

## Task 1:Data model + Schema + Frontend types + ProjectFormModal

**Files:**
- Modify: `backend/app/models.py`(Project 加 denoise_enabled + denoise_model)
- Create: `backend/migrations/versions/0004_project_denoise_settings.py`
- Modify: `backend/app/schemas.py`(ProjectIn / ProjectPatch / ProjectOut 加欄位 + validator + ALLOWED_DENOISE_MODELS)
- Create / modify: `backend/tests/test_routes_projects.py`(加欄位驗收)
- Modify: `frontend/src/api/types.ts`(DenoiseModel type + 3 個 interface 同步)
- Modify: `frontend/src/components/ProjectFormModal.tsx`(加 toggle + 下拉)

### Steps

- [ ] **Step 1: Read 既有檔對齊風格**
  - `backend/app/models.py`(看 `text` import、Project class 結構)
  - `backend/app/schemas.py`(看 ProjectIn / ProjectPatch / ProjectOut)
  - `backend/migrations/versions/0003_*.py`(對齊 revision 風格)
  - `backend/tests/test_routes_projects.py`(看既有 test 結構、helper)
  - `frontend/src/components/ProjectFormModal.tsx`(看 form field 結構、formData state shape)

- [ ] **Step 2: 改 `models.py` 加 2 欄位**

Project class 內 `webhook_secret` 後加:
```python
    denoise_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default=text("0"),
    )
    denoise_model: Mapped[str] = mapped_column(
        String(20), default="gtcrn", nullable=False, server_default=text("'gtcrn'"),
    )
```

確認 `text` 已 import(0003 migration 已加過、應已有)。若無、`from sqlalchemy import ..., text`。

- [ ] **Step 3: 寫 Alembic migration 0004**

`backend/migrations/versions/0004_project_denoise_settings.py`(完整 code 在 spec §4.2、照寫)。revision="0004"、down_revision="0003"。

- [ ] **Step 4: 改 `schemas.py`**

在檔頂或 Project 段定義常數:
```python
ALLOWED_DENOISE_MODELS = ("gtcrn", "zipenhancer")
```

`ProjectIn` 加:
```python
    denoise_enabled: bool = False
    denoise_model: str = "gtcrn"
```

加 validator(用 pydantic v2 `field_validator`):
```python
from pydantic import field_validator

class ProjectIn(BaseModel):
    # ... 既有欄位 + denoise_enabled + denoise_model

    @field_validator("denoise_model")
    @classmethod
    def _check_denoise_model(cls, v: str) -> str:
        if v not in ALLOWED_DENOISE_MODELS:
            raise ValueError(f"denoise_model must be one of {ALLOWED_DENOISE_MODELS}")
        return v
```

`ProjectPatch` 加 optional:
```python
    denoise_enabled: bool | None = None
    denoise_model: str | None = None

    @field_validator("denoise_model")
    @classmethod
    def _check_denoise_model(cls, v: str | None) -> str | None:
        if v is not None and v not in ALLOWED_DENOISE_MODELS:
            raise ValueError(f"denoise_model must be one of {ALLOWED_DENOISE_MODELS}")
        return v
```

`ProjectOut` 加 required:
```python
    denoise_enabled: bool
    denoise_model: str
```

- [ ] **Step 5: 改 `frontend/src/api/types.ts`**

加 type alias:
```typescript
export type DenoiseModel = "gtcrn" | "zipenhancer";
```

`ProjectOut` interface 加:
```typescript
  denoise_enabled: boolean;
  denoise_model: DenoiseModel;
```

`ProjectIn` / `ProjectPatch` 同樣方式加 optional:
```typescript
  denoise_enabled?: boolean;
  denoise_model?: DenoiseModel;
```

- [ ] **Step 6: 改 `ProjectFormModal.tsx`**

Read 既有檔、找 `formData` state 跟 form field 排版位置。

在 webhook_url 那塊欄位之後加 denoise 區段:
```tsx
<div className="border-t pt-3 mt-3">
  <label className="flex items-center gap-2 cursor-pointer">
    <input
      type="checkbox"
      checked={formData.denoise_enabled ?? false}
      onChange={(e) => setFormData({
        ...formData, denoise_enabled: e.target.checked,
      })}
      className="cursor-pointer"
    />
    <span className="text-sm text-slate-700">啟用降噪(ASR 前處理)</span>
  </label>
  {formData.denoise_enabled && (
    <div className="mt-2 ml-6">
      <label className="block text-sm text-slate-700">降噪模型</label>
      <select
        value={formData.denoise_model ?? "gtcrn"}
        onChange={(e) => setFormData({
          ...formData,
          denoise_model: e.target.value as "gtcrn" | "zipenhancer",
        })}
        className="block w-full mt-1 border border-slate-300 rounded px-2 py-1 text-sm"
      >
        <option value="gtcrn">GTCRN(輕量、快、品質基本可用)</option>
        <option value="zipenhancer">ZipEnhancer(高品質、慢約 100×)</option>
      </select>
      <p className="text-xs text-slate-500 mt-1">
        預設關閉。降噪僅用於 ASR 推論、不影響 dataset 落地的原始音檔。
      </p>
    </div>
  )}
</div>
```

**注意**:`formData` state 型別應該對齊 ProjectIn / ProjectPatch。若 state 型別 TypeScript 沒匹配 denoise_enabled / denoise_model、要加進 state interface。

- [ ] **Step 7: 加 backend test**

`backend/tests/test_routes_projects.py` 加 test(找既有檔 helper):
```python
@pytest.mark.asyncio
async def test_create_project_with_denoise_settings(app_client):
    r = await app_client.post("/api/admin/projects", json={
        "name": "p_denoise",
        "denoise_enabled": True,
        "denoise_model": "zipenhancer",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["denoise_enabled"] is True
    assert body["denoise_model"] == "zipenhancer"


@pytest.mark.asyncio
async def test_create_project_default_denoise(app_client):
    r = await app_client.post("/api/admin/projects", json={"name": "p_default"})
    assert r.status_code == 201
    body = r.json()
    assert body["denoise_enabled"] is False
    assert body["denoise_model"] == "gtcrn"


@pytest.mark.asyncio
async def test_create_project_invalid_denoise_model(app_client):
    r = await app_client.post("/api/admin/projects", json={
        "name": "p_bad",
        "denoise_model": "unknown_model",
    })
    assert r.status_code == 422  # pydantic validator


@pytest.mark.asyncio
async def test_patch_project_denoise(app_client):
    r = await app_client.post("/api/admin/projects", json={"name": "p1"})
    pid = r.json()["id"]
    r = await app_client.put(f"/api/admin/projects/{pid}", json={
        "denoise_enabled": True,
        "denoise_model": "gtcrn",
    })
    assert r.status_code == 200
    assert r.json()["denoise_enabled"] is True
```

- [ ] **Step 8: typecheck + lint**

```
npm --prefix /d/vibevoice_asr/frontend run typecheck
```

```
npm --prefix /d/vibevoice_asr/frontend run lint
```

- [ ] **Step 9: Commit + push**

```
git -C /d/vibevoice_asr add backend/app/models.py backend/migrations/versions/0004_project_denoise_settings.py backend/app/schemas.py backend/tests/test_routes_projects.py frontend/src/api/types.ts frontend/src/components/ProjectFormModal.tsx
```

```
git -C /d/vibevoice_asr commit -m "feat(denoise): Project 加 denoise_enabled + denoise_model 設定 + UI toggle"
```

```
git -C /d/vibevoice_asr push
```

---

## Task 2:Denoiser service + audio_preprocessor + vendor scaffold + dependencies

**Files:**
- Create: `backend/app/services/denoiser.py`
- Create: `backend/app/services/audio_preprocessor.py`
- Create: `backend/tests/test_denoiser.py`
- Create: `backend/tests/test_audio_preprocessor.py`
- Modify: `backend/app/config.py`(加 denoiser_model_dir)
- Modify: `backend/pyproject.toml`(加 onnxruntime)
- Modify: `docker-compose.yml`(backend + worker 加 vendor/denoiser mount)
- Create: `vendor/denoiser/README.md`
- Create: `vendor/denoiser/.gitignore`
- Create: `scripts/download_denoiser_models.sh`
- Create: `LICENSES/audio-denoiser.LICENSE.md`

### Steps

- [ ] **Step 1: WebFetch 確認 model file 下載來源**

用 WebFetch tool 拿 `https://github.com/DakeQQ/Audio-Denoiser-ONNX` README、找:
- GTCRN ONNX 檔案位置(HuggingFace mirror / GitHub release / repo 內)
- ZipEnhancer 同上
- Model file 大概大小(MB)
- Python 推論範例(input/output shape、reshape 規則)

如果找不到 direct download URL,fallback 看 repo `Export_ONNX/<ModelName>/` 子目錄是否含 ONNX 檔(常見 pattern)。

把下載 URL 跟 input/output shape 記下、進 `denoiser.py` 跟 `download_denoiser_models.sh`。

- [ ] **Step 2: 寫 `denoiser.py`**

完整 code 在 spec §5.1。需要根據 Step 1 確認的 model input/output shape 微調 `_run_session`(`reshape(1, -1)` 可能不對、視模型而定)。

如果兩個模型 input shape 不同,寫成:
```python
def _run_session(session: Any, chunk: np.ndarray, model_name: str) -> np.ndarray:
    if model_name == "gtcrn":
        # GTCRN 預期 (1, n_samples) ...
        out = session.run(None, {input_name: chunk.reshape(1, -1)})
    elif model_name == "zipenhancer":
        # ZipEnhancer 預期 ... (依 Step 1 確認)
        ...
```

- [ ] **Step 3: 寫 `audio_preprocessor.py`**

完整 code 在 spec §5.2、照寫。

- [ ] **Step 4: 加 `config.py` 設定**

```python
denoiser_model_dir: str = "/vendor/denoiser"
```

- [ ] **Step 5: 加 `pyproject.toml` 依賴**

`[tool.poetry.dependencies]` 加:
```toml
onnxruntime = "^1.18.0"
```

不動 `poetry.lock`(user Linux 端 build 時 resolve)。

- [ ] **Step 6: 改 `docker-compose.yml`**

`backend` service `volumes:` 內加:
```yaml
- ./vendor/denoiser:/vendor/denoiser:ro
```

`worker` service `volumes:` 加同樣 mount。

- [ ] **Step 7: 寫 `vendor/denoiser/README.md`**

```markdown
# Denoiser ONNX Models

ONNX 模型來自 [Audio-Denoiser-ONNX](https://github.com/DakeQQ/Audio-Denoiser-ONNX)
(Apache 2.0)。本目錄不 commit 模型本體(file 大、~50-200MB)、需 setup 時下載。

## Models

| File | Source | License |
|---|---|---|
| `gtcrn.onnx` | <填入 Step 1 確認的 URL> | (依 model 自己 license) |
| `zipenhancer.onnx` | <填入 URL> | (依 model 自己 license) |

## 下載

```
bash scripts/download_denoiser_models.sh
```

或手動 wget 各 URL 到本目錄。
```

- [ ] **Step 8: 寫 `vendor/denoiser/.gitignore`**

```
*.onnx
```

- [ ] **Step 9: 寫 `scripts/download_denoiser_models.sh`**

```bash
#!/usr/bin/env bash
# Download Audio-Denoiser-ONNX models for ASR pre-processing.
# Run once after `git clone`。

set -euo pipefail

VENDOR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../vendor/denoiser" && pwd)"
cd "$VENDOR_DIR"

# URLs 由 Step 1 WebFetch 確認後填入
GTCRN_URL="<URL>"
ZIPENHANCER_URL="<URL>"

echo "Downloading GTCRN to $VENDOR_DIR/gtcrn.onnx..."
wget -O gtcrn.onnx "$GTCRN_URL"

echo "Downloading ZipEnhancer to $VENDOR_DIR/zipenhancer.onnx..."
wget -O zipenhancer.onnx "$ZIPENHANCER_URL"

echo "Done. Models in $VENDOR_DIR/"
ls -lh "$VENDOR_DIR"/*.onnx
```

加執行權限:`chmod +x scripts/download_denoiser_models.sh`(Windows 端用 `git update-index --chmod=+x`)。

- [ ] **Step 10: 寫 `LICENSES/audio-denoiser.LICENSE.md`**

```markdown
# Audio-Denoiser-ONNX

Models vendored at `vendor/denoiser/*.onnx` derive from
https://github.com/DakeQQ/Audio-Denoiser-ONNX

## Wrapper License

Apache License 2.0

Copyright (c) 2024 DakeQQ

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

## Model Licenses

Individual model weights may have separate licenses inherited from upstream:
- GTCRN: <填入 license 確認結果>
- ZipEnhancer: <填入>
```

- [ ] **Step 11: 寫 `test_denoiser.py`**

```python
"""denoiser ONNX wrapper 行為驗證 — 全 mock onnxruntime,不真載 model file。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from app.errors import AppError, ErrorCode
from app.services import denoiser


@pytest.fixture(autouse=True)
def _reset_cache():
    """每個 test 清 session cache。"""
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
    """3 秒音檔 → 3 個 1-second chunks → 各 chunk session.run → concat。"""
    fake_session = MagicMock()
    fake_session.get_inputs.return_value = [MagicMock(name="x")]
    fake_session.get_inputs.return_value[0].name = "x"
    # 每次 run 回 chunk 大小的 zeros 即可
    fake_session.run.return_value = [np.zeros((1, 16000), dtype=np.float32)]

    with patch.object(denoiser, "_get_session", return_value=fake_session):
        waveform = np.ones(48000, dtype=np.float32)  # 3 秒
        cleaned = denoiser.denoise(waveform, sr=16000, model_name="gtcrn")

    assert cleaned.shape == waveform.shape
    assert cleaned.dtype == np.float32
    # 3 個 chunk
    assert fake_session.run.call_count == 3
```

- [ ] **Step 12: 寫 `test_audio_preprocessor.py`**

```python
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
        audio_preprocessor, "_load_pcm",
        lambda p: (np.zeros(16000, dtype=np.float32), 16000),
    )
    monkeypatch.setattr(
        audio_preprocessor, "denoise",
        lambda waveform, sr, model_name: np.zeros_like(waveform),
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
```

- [ ] **Step 13: Commit + push**

```
git -C /d/vibevoice_asr add backend/app/services/denoiser.py backend/app/services/audio_preprocessor.py backend/app/config.py backend/pyproject.toml backend/tests/test_denoiser.py backend/tests/test_audio_preprocessor.py docker-compose.yml vendor/denoiser/ scripts/download_denoiser_models.sh LICENSES/audio-denoiser.LICENSE.md
```

```
git -C /d/vibevoice_asr commit -m "feat(denoise): denoiser service + audio_preprocessor + vendor scaffold"
```

```
git -C /d/vibevoice_asr push
```

---

## Task 3:job_runner 整合 + integration test

**Files:**
- Modify: `backend/app/services/job_runner.py`(call maybe_denoise + cleanup)
- Modify / create: `backend/tests/test_job_runner_denoise.py`(integration mock 走通整段)

### Steps

- [ ] **Step 1: Read `job_runner.py` 找整合點**

找 `run_transcribe` 函式:
- 哪一步取 job + project(目前實作)
- 哪一步呼叫 `split_long_audio`
- 哪一步 cleanup chunks(success / failure)

Integration 在「取 job + project 之後」、「split 之前」加 `maybe_denoise`、用 `try/finally` 包整段確保 cleanup。

- [ ] **Step 2: 改 `job_runner.py`**

對應 spec §5.3。但 job_runner 內已有複雜的 chunk-level retry / 並行邏輯,要找最外層 try/finally 加 `cleanup_denoised`,**不能**用單 chunk 處理時的 try 包(那會 retry 中重複刪掉 temp file)。

實作 subagent 仔細看現有結構、找最外層 entry point 加邏輯。建議:
```python
async def run_transcribe(job_id: str) -> None:
    # 既有取 job + project
    ...

    # 新:audio preprocessing
    from app.services.audio_preprocessor import maybe_denoise, cleanup_denoised
    asr_audio_path, was_denoised = maybe_denoise(
        Path(job.audio_path),
        denoise_enabled=project.denoise_enabled,
        denoise_model=project.denoise_model,
    )

    try:
        # 既有 splitter + chunk transcribe 流程,把 audio_path 替換成 asr_audio_path
        ...
    finally:
        if was_denoised:
            cleanup_denoised(asr_audio_path)
```

**重要**:`job.audio_path` **不**改、splitter 用 `asr_audio_path`。Dataset source 安全。

- [ ] **Step 3: 寫 integration test**

`backend/tests/test_job_runner_denoise.py`:
```python
"""run_transcribe 整合 denoise pipeline。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest

from app.db import db_session
from app.models import Job, JobSource, JobStatus, Project


async def _seed_job_with_denoise(denoise_enabled: bool) -> tuple[int, str]:
    async with db_session() as db:
        project = Project(name="p1", denoise_enabled=denoise_enabled, denoise_model="gtcrn")
        db.add(project)
        await db.flush()
        job = Job(
            id="job-denoise-1",
            project_id=project.id,
            source=JobSource.ADMIN_UPLOAD,
            filename="a.mp3",
            audio_path="/tmp/a.mp3",
            duration_sec=10.0,
            status=JobStatus.QUEUED,
        )
        db.add(job)
        await db.commit()
        return project.id, job.id


@pytest.mark.asyncio
async def test_run_transcribe_denoise_disabled_skips(app_client):
    """denoise_enabled=False → maybe_denoise 不寫 temp file。"""
    _, job_id = await _seed_job_with_denoise(denoise_enabled=False)

    with patch(
        "app.services.job_runner.maybe_denoise",
        return_value=(Path("/tmp/a.mp3"), False),
    ) as mock_denoise, patch(
        "app.services.job_runner.split_long_audio",
        return_value=[],
    ):
        # mock 整段 transcribe 流程
        with patch(
            "app.services.job_runner._transcribe_all_chunks",
            new_callable=AsyncMock,
            return_value=[],
        ):
            from app.services.job_runner import run_transcribe
            await run_transcribe(job_id)

    mock_denoise.assert_called_once()
    # was_denoised=False → cleanup 不會被 call;但 maybe_denoise 仍照打
    assert mock_denoise.call_args.kwargs["denoise_enabled"] is False


@pytest.mark.asyncio
async def test_run_transcribe_denoise_enabled_temp_cleanup(app_client, tmp_path):
    """denoise_enabled=True → temp denoised file 寫了、job 完後刪掉。"""
    _, job_id = await _seed_job_with_denoise(denoise_enabled=True)

    temp_denoised = tmp_path / "denoised_x.mp3"
    temp_denoised.write_bytes(b"fake")

    with patch(
        "app.services.job_runner.maybe_denoise",
        return_value=(temp_denoised, True),
    ), patch(
        "app.services.job_runner.cleanup_denoised",
    ) as mock_cleanup, patch(
        "app.services.job_runner.split_long_audio",
        return_value=[],
    ), patch(
        "app.services.job_runner._transcribe_all_chunks",
        new_callable=AsyncMock,
        return_value=[],
    ):
        from app.services.job_runner import run_transcribe
        await run_transcribe(job_id)

    mock_cleanup.assert_called_once_with(temp_denoised)
```

> **Note**:test 寫法依賴 job_runner 內部 import 路徑。Subagent 看實際 `run_transcribe` 結構決定 mock path(`app.services.job_runner.maybe_denoise` 還是 `app.services.audio_preprocessor.maybe_denoise`)。

- [ ] **Step 4: Commit + push**

```
git -C /d/vibevoice_asr add backend/app/services/job_runner.py backend/tests/test_job_runner_denoise.py
```

```
git -C /d/vibevoice_asr commit -m "feat(denoise): job_runner 整合 maybe_denoise + try/finally cleanup"
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
bash scripts/download_denoiser_models.sh
```

```
docker compose build backend worker
```

```
docker compose up -d backend worker
```

```
docker compose exec backend alembic upgrade head
```

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

### 實機驗收

1. 進 admin UI → 任一 project 編輯頁:應該看到「啟用降噪」toggle + 「降噪模型」下拉(預設關閉)
2. **未啟用 case**:現有 ASR 流程不變、log 不應出現 `denoiser: starting`
3. **啟用 GTCRN case**:上傳一支 noisy 音檔、log 應印 `denoiser: starting gtcrn` 跟 `denoiser: finished gtcrn`、後續 ASR 流程跑、Editor 看到 segments
4. **啟用 ZipEnhancer**:跟 GTCRN 同流程、但處理時間明顯長
5. **Dataset 落地驗證**:勾「校正完成」、從歷史轉錄建 dataset → 確認 dataset.audio_path 還是指原始音檔(沒指 denoised temp)
6. **Temp file 清理**:job 結束後 `data/uploads/denoised_*.mp3` 應該已刪

---

## Risks

| 風險 | 緩解 |
|---|---|
| ONNX model 下載 URL 找不到 | Step 1 必須 WebFetch 確認、若 upstream 沒 direct link、退而求其次手動從 HuggingFace mirror / repo `Export_ONNX/` 拿 |
| Model input/output shape 跟 spec 假設不符 | Step 1 同時拿 Python 推論範例、按範例調整 `_run_session` 內 reshape 邏輯 |
| onnxruntime CPU 對長音檔(>1hr)記憶體爆 | maybe_denoise 內按 chunk 處理、不一次 load 整段 |
| temp denoised file 累積在 data/uploads/ | cleanup 在 try/finally、job 失敗時也應該刪;startup 加 `*.mp3` 老檔清理 backlog 可選 |
| Model license 限制 redistribute | README 紀錄各 model 來源 + license 確認 |

---

## Plan Self-Review

- [x] 3 task 依賴順序明確
- [x] 每 step 含完整 code(model file 下載 URL 待 Step 1 確認、不算 placeholder — 是必要的 research step)
- [x] backend pytest 全綠是 done criteria
- [x] dataset source 不被影響(job.audio_path 不變)— spec §11 / pipeline §5.3 保證
- [x] denoise 預設 off — 既有 project 不受影響
