# Audio Playback Speed 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 `superpowers:subagent-driven-development` 派 subagent 執行。

**Goal:** Project 加 `playback_speed` 欄位,ASR 推論前用 ffmpeg atempo 調速,推論完 segments 時間戳 scale 回原 timeline。

**Spec Reference:** `docs/superpowers/specs/2026-05-13-audio-playback-speed-design.md`

---

## Task 切分

| Task | 範圍 |
|---|---|
| 1 | Backend(model + migration + schemas + audio_preprocessor + job_runner + tests) |
| 2 | Frontend(types + ProjectFormModal) |

---

## Task 1:Backend

**Files:**
- Modify: `backend/app/models.py`(Project 加 playback_speed)
- Create: `backend/migrations/versions/0006_project_playback_speed.py`
- Modify: `backend/app/schemas.py`(ProjectIn/Patch/Out 加欄位 + Field validator)
- Modify: `backend/app/services/audio_preprocessor.py`(加 maybe_adjust_speed + cleanup_adjusted_speed)
- Modify: `backend/app/services/job_runner.py`(state 加 playback_speed、stage 整合、segments scale)
- Modify: `backend/tests/test_audio_preprocessor.py`(加 4 條 speed test)
- Modify: `backend/tests/test_routes_projects.py`(加 3 條 playback_speed test)
- Create: `backend/tests/test_job_runner_speed.py`(integration mock)

### Steps

- [ ] **Step 1: Read 既有檔**

- `models.py`(Project class、確認 Float import)
- `schemas.py`(ProjectIn / Patch / Out 結構、確認 Field import)
- `audio_preprocessor.py`(既有 maybe_denoise / cleanup_denoised 結構)
- `job_runner.py`(`_begin_running` state dict、`run_transcribe` 主流程、現有 maybe_denoise 整合位置)
- `migrations/versions/0005_*`(對齊風格)
- `test_audio_preprocessor.py` / `test_routes_projects.py`(對齊 fixture pattern)

- [ ] **Step 2: `models.py` 加欄位**

`Project` class 內 `denoise_enabled` 之後:
```python
    playback_speed: Mapped[float] = mapped_column(
        Float, default=1.0, nullable=False, server_default=text("1.0"),
    )
```

確認 `Float` 已 import(若無,加 `from sqlalchemy import ..., Float`)。

- [ ] **Step 3: 寫 migration 0006**

`backend/migrations/versions/0006_project_playback_speed.py`(spec §4.2 完整 code)。

- [ ] **Step 4: `schemas.py` 加欄位 + Field validator**

`ProjectIn`:
```python
    playback_speed: float = Field(default=1.0, ge=0.5, le=2.0)
```

`ProjectPatch`:
```python
    playback_speed: float | None = Field(default=None, ge=0.5, le=2.0)
```

`ProjectOut`:
```python
    playback_speed: float
```

- [ ] **Step 5: `audio_preprocessor.py` 加 maybe_adjust_speed + cleanup**

加 import:
```python
import math
```

加 `maybe_adjust_speed` 函式(spec §5.1 完整 code,接受 keyword `playback_speed: float`、回 `(Path, bool)`)。

加 `cleanup_adjusted_speed` 函式(對齊 `cleanup_denoised` pattern)。

- [ ] **Step 6: `job_runner.py` 整合**

(a) Import 加:
```python
from app.services.audio_preprocessor import (
    cleanup_adjusted_speed, cleanup_denoised, maybe_adjust_speed, maybe_denoise,
)
```

(b) `_begin_running` state dict 加:
```python
"playback_speed": project.playback_speed if project else 1.0,
```

(c) `run_transcribe` 在 `maybe_denoise` 之後、`try:` 之前加 Stage 2:
```python
# Stage 2: maybe adjust speed
speed_adjusted_path, was_speed_adjusted = maybe_adjust_speed(
    Path(state["audio_path"]),
    playback_speed=state["playback_speed"],
)
state["audio_path"] = str(speed_adjusted_path)
```

(d) 在 `try:` block 內 `outcome = await _do_transcribe(...)` 之後、`_persist_success` 之前加 scale:
```python
if state["playback_speed"] != 1.0:
    outcome["segments"] = _scale_segments(
        outcome["segments"], state["playback_speed"],
    )
```

(e) `finally` block 加 cleanup(放 cleanup_denoised 之前、後寫的先刪):
```python
finally:
    if was_speed_adjusted:
        cleanup_adjusted_speed(speed_adjusted_path)
    if was_denoised:
        cleanup_denoised(asr_audio_path)
```

(f) 加 `_scale_segments` helper(在 `_begin_running` 之後、`_do_transcribe` 之前或檔尾):
```python
def _scale_segments(segments: list[dict], playback_speed: float) -> list[dict]:
    """Scale segment timestamps × playback_speed 回原 timeline。"""
    out = []
    for s in segments:
        out.append({
            **s,
            "start_time": round(s["start_time"] * playback_speed, 3),
            "end_time": round(s["end_time"] * playback_speed, 3),
        })
    return out
```

- [ ] **Step 7: `test_audio_preprocessor.py` 加 4 條 speed test**

```python
import math

def test_maybe_adjust_speed_noop_when_1_0(tmp_path):
    fake = tmp_path / "a.mp3"
    fake.write_bytes(b"fake")
    out, was = audio_preprocessor.maybe_adjust_speed(fake, playback_speed=1.0)
    assert out == fake
    assert was is False


def test_maybe_adjust_speed_noop_when_close_to_1(tmp_path):
    fake = tmp_path / "a.mp3"
    fake.write_bytes(b"fake")
    out, was = audio_preprocessor.maybe_adjust_speed(fake, playback_speed=1.0005)
    assert was is False  # math.isclose abs_tol=1e-3


def test_maybe_adjust_speed_writes_temp(tmp_path, monkeypatch):
    fake = tmp_path / "a.mp3"
    fake.write_bytes(b"fake")
    monkeypatch.setattr(
        audio_preprocessor, "subprocess",
        type("M", (), {
            "run": lambda *a, **k: type("R", (), {"returncode": 0})(),
            "CalledProcessError": Exception,
            "TimeoutExpired": Exception,
            "PIPE": -1,
        })(),
    )
    # ...或更簡單:patch subprocess.run 不真跑 ffmpeg、寫個假 mp3 到 temp
    # 實作 subagent 自行決定 mock 方式


def test_maybe_adjust_speed_out_of_range(tmp_path):
    fake = tmp_path / "a.mp3"
    fake.write_bytes(b"fake")
    with pytest.raises(AppError) as exc:
        audio_preprocessor.maybe_adjust_speed(fake, playback_speed=3.0)
    assert exc.value.code == ErrorCode.INTERNAL_ERROR


def test_cleanup_adjusted_speed_missing_safe(tmp_path):
    p = tmp_path / "nonexistent.mp3"
    audio_preprocessor.cleanup_adjusted_speed(p)  # 不 raise
```

- [ ] **Step 8: `test_routes_projects.py` 加 3 條 playback_speed test**

```python
@pytest.mark.asyncio
async def test_create_project_with_playback_speed(app_client):
    r = await app_client.post("/api/admin/projects", json={
        "name": "p_speed",
        "playback_speed": 0.7,
    })
    assert r.status_code == 201
    assert r.json()["playback_speed"] == 0.7


@pytest.mark.asyncio
async def test_create_project_default_playback_speed(app_client):
    r = await app_client.post("/api/admin/projects", json={"name": "p_default"})
    assert r.status_code == 201
    assert r.json()["playback_speed"] == 1.0


@pytest.mark.asyncio
async def test_create_project_speed_out_of_range(app_client):
    r = await app_client.post("/api/admin/projects", json={
        "name": "p_bad",
        "playback_speed": 3.0,
    })
    assert r.status_code == 422
```

- [ ] **Step 9: 新建 `test_job_runner_speed.py`**

```python
"""run_transcribe 整合 maybe_adjust_speed 邏輯 + segments scale。"""
from __future__ import annotations

import pytest

from app.services.job_runner import _scale_segments


def test_scale_segments_slow():
    """playback_speed=0.7、segments × 0.7 還原原 timeline。"""
    segs = [
        {"start_time": 10.0, "end_time": 20.0, "speaker_id": 1, "text": "a"},
    ]
    out = _scale_segments(segs, 0.7)
    assert out[0]["start_time"] == 7.0
    assert out[0]["end_time"] == 14.0


def test_scale_segments_fast():
    """playback_speed=1.5、segments × 1.5。"""
    segs = [
        {"start_time": 10.0, "end_time": 20.0, "speaker_id": 1, "text": "a"},
    ]
    out = _scale_segments(segs, 1.5)
    assert out[0]["start_time"] == 15.0
    assert out[0]["end_time"] == 30.0


def test_scale_segments_preserves_other_fields():
    segs = [{"start_time": 0.0, "end_time": 1.0, "speaker_id": 2, "text": "hello"}]
    out = _scale_segments(segs, 0.5)
    assert out[0]["speaker_id"] == 2
    assert out[0]["text"] == "hello"


def test_scale_segments_empty():
    assert _scale_segments([], 0.7) == []
```

整段 integration test(run_transcribe 走通 + cleanup 順序驗證)可選做、視 mocking 複雜度而定。Subagent 自行決定。

- [ ] **Step 10: Commit + push**

```
git -C /d/vibevoice_asr add backend/app/models.py backend/migrations/versions/0006_project_playback_speed.py backend/app/schemas.py backend/app/services/audio_preprocessor.py backend/app/services/job_runner.py backend/tests/test_audio_preprocessor.py backend/tests/test_routes_projects.py backend/tests/test_job_runner_speed.py
```

```
git -C /d/vibevoice_asr commit -m "feat(speed): Project 加 playback_speed、ASR 前 atempo 調速 + segments scale 還原"
```

```
git -C /d/vibevoice_asr push
```

---

## Task 2:Frontend

**Files:**
- Modify: `frontend/src/api/types.ts`(ProjectOut/In/Patch 加 playback_speed)
- Modify: `frontend/src/components/ProjectFormModal.tsx`(zod schema + state + UI 數字輸入)
- Modify: `frontend/src/pages/Projects.tsx`(若 callback inline type 含 playback_speed)

### Steps

- [ ] **Step 1: Read 既有檔**

- `types.ts`(ProjectOut / ProjectIn / ProjectPatch 結構)
- `ProjectFormModal.tsx`(整檔、找 denoise 區塊位置、zod schema、submit)

- [ ] **Step 2: 改 types.ts**

`ProjectOut` 加:
```typescript
  playback_speed: number;
```

`ProjectIn` / `ProjectPatch` 加 optional:
```typescript
  playback_speed?: number;
```

- [ ] **Step 3: 改 ProjectFormModal.tsx**

(a) zod schema 加:
```typescript
playback_speed: z.number().min(0.5).max(2.0).optional(),
```

(b) state interface / Props.onSubmit inline type 加 `playback_speed?: number;`

(c) reset() initial:
```typescript
playback_speed: initial?.playback_speed ?? 1.0,
```

(d) submit values 帶 `playback_speed: values.playback_speed`

(e) UI 在 denoise 區塊之後加:
```tsx
<div className="border-t pt-3 mt-3">
  <label className="block text-sm text-slate-700 mb-1">
    ASR 推論速度調整(playback_speed)
  </label>
  <input
    type="number"
    step="0.05"
    min="0.5"
    max="2.0"
    {...register("playback_speed", { valueAsNumber: true })}
    className="w-32 border border-slate-300 rounded px-2 py-1 text-sm"
  />
  <p className="text-xs text-slate-500 mt-1">
    1.0 = 原速(預設)、&lt; 1 = 拉慢音檔(客服快語速場景設 0.7-0.8)、
    &gt; 1 = 加速(短音檔節省處理時間)。
    範圍 0.5-2.0。Segments 時間戳會自動 scale 回原時間軸。
  </p>
</div>
```

- [ ] **Step 4: Projects.tsx 對齊**

若 `onCreate` / `onEdit` callback inline 型別宣告含 ProjectIn shape(而非用 ProjectIn type),加 `playback_speed?: number`。

- [ ] **Step 5: typecheck + lint**

```
npm --prefix /d/vibevoice_asr/frontend run typecheck
```

```
npm --prefix /d/vibevoice_asr/frontend run lint
```

兩者必須 PASS。

- [ ] **Step 6: Commit + push**

```
git -C /d/vibevoice_asr add frontend/src/api/types.ts frontend/src/components/ProjectFormModal.tsx frontend/src/pages/Projects.tsx
```

```
git -C /d/vibevoice_asr commit -m "feat(speed): frontend ProjectFormModal 加 playback_speed 數字輸入"
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

### 實機

1. project 編輯頁應該多一個「ASR 推論速度調整」數字輸入,預設 1.0
2. 設成 0.7、儲存
3. 上傳一支客服音檔
4. worker log 應該印:
   - `denoiser: starting ...`(若 denoise 也開)
   - `speed: adjusted ... @ 0.7×`
   - `split_long_audio: ...`
   - `transcribe_job DONE`
5. Editor 看到 segments、時間軸對齊**原音檔**(不是慢速版的 1.43× 時長)
6. cleanup:`/data/uploads/` 內 `speed_*.mp3` 跟 `denoised_*.mp3` job 結束都應該刪掉

---

## Risks

| 風險 | 緩解 |
|---|---|
| ffmpeg atempo 對極端 ratio(0.5)品質差 | 預設 1.0、user 自選極端值要自己負責 |
| 慢速版 audio 時長 ×1/0.7 ≈ 1.43、vLLM 處理時間變長 | 接受、trade quality for time |
| 時間戳 scale 浮點誤差 | `round(t * speed, 3)` 對齊毫秒 |
| denoise + speed 都開、temp file 累積 | finally cleanup 兩個都刪 |
| segments scale 後 end_time < start_time 邏輯出錯 | × 同樣 ratio 不會反序;若 vLLM 輸出本身有問題,既有 validator 已擋 |

---

## Plan Self-Review

- [x] 兩個 task 依賴明確
- [x] Job.audio_path 不變(dataset safe)
- [x] Pipeline order: denoise → speed → splitter,理由清楚
- [x] Segments scale 公式驗證(spec §5.3)
- [x] cleanup 順序:後寫的先刪
