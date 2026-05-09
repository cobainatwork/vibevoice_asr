# M3 Frontend Admin 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 SPEC.md §14 M3 acceptance：5 頁 + Sidebar + System 監控頁，含 Hotwords 匯入 / 匯出與 TranscriptEditor 自動儲存。

**Architecture:** Backend 加 3 個 admin endpoints（PATCH job segments / hotwords export / hotwords import）+ Frontend 6 頁與共用元件（兩層 Sidebar + WaveformPlayer + Focus Editor）。State 管理用 zustand，HTTP 統一 fetch wrapper + toast 錯誤處理。

**Tech Stack:** Backend 沿用 FastAPI / SQLAlchemy / pytest；Frontend 沿用既有 scaffold（React 18 + TypeScript + Vite + Tailwind 3 + zustand 4 + react-hook-form + zod + wavesurfer 7 + recharts 2 + lucide-react）。

**對應 spec:** [docs/superpowers/specs/2026-05-09-m3-frontend-admin-design.md](../specs/2026-05-09-m3-frontend-admin-design.md)

**測試政策:**
- Backend tasks 採嚴格 TDD（RED → GREEN → commit），用既有 pytest 基建 + 補 FastAPI TestClient fixture
- Frontend tasks 因 spec §11.2 已決議不做自動化測試，採「typecheck + 元件 mount 不爆 + 端到端手動驗證」流程，commit 後跑 `npm run typecheck` 與 `npm run lint` 驗證

---

## File Structure

### Backend 新增 / 修改

```
backend/
├── app/
│   ├── errors.py                              # 補 INVALID_SEGMENTS
│   ├── schemas.py                             # 補 SegmentsPatchIn
│   └── routes/admin/
│       ├── jobs.py                            # 補 PATCH /jobs/{id}/segments
│       └── projects.py                        # 補 hotwords import/export endpoints
└── tests/
    ├── conftest.py                            # 加 app_client fixture（FastAPI TestClient）
    ├── test_admin_jobs_segments.py            # 新增
    └── test_admin_hotwords_io.py              # 新增
```

### Frontend 新增 / 修改

```
frontend/src/
├── api/
│   ├── client.ts                              # 改：fetch wrapper + 錯誤 → toast
│   ├── types.ts                               # 改：對齊 backend schemas
│   ├── projects.ts                            # 改：CRUD + hotwords import/export
│   ├── jobs.ts                                # 改：含 PATCH segments
│   └── system.ts                              # 改：health/profile/queue/vllm_status
├── components/
│   ├── Sidebar.tsx                            # 改：兩層結構
│   ├── Toast.tsx                              # 新增：toast 容器 + 動畫
│   ├── JobStatusBadge.tsx                     # 新增
│   ├── JobList.tsx                            # 改：rows + status + 動作
│   ├── HotwordsChips.tsx                      # 改：chip input + import/export
│   ├── UploadDropzone.tsx                     # 新增：drag-drop
│   ├── WaveformPlayer.tsx                     # 改：wavesurfer + Regions
│   ├── TranscriptViewer.tsx                   # 改：read-only segments
│   ├── TranscriptEditor.tsx                   # 改：focus editor 主結構
│   ├── SegmentListItem.tsx                    # 新增：左列表 row
│   └── SegmentFocusEditor.tsx                 # 新增：右側編輯區
├── hooks/                                     # 新目錄
│   ├── useToast.ts                            # 新增
│   ├── useAutoSave.ts                         # 新增
│   └── useKeyboardShortcuts.ts                # 新增
├── stores/
│   ├── projectStore.ts                        # 改：加 currentProjectId / refetch
│   ├── editorStore.ts                         # 新增
│   └── toastStore.ts                          # 新增
├── lib/
│   ├── format.ts                              # 沿用，可能補
│   ├── time.ts                                # 沿用，可能補
│   └── keyboard.ts                            # 新增：快捷鍵 binding 集中
├── pages/
│   ├── Projects.tsx                           # 改：卡片網格
│   ├── Hotwords.tsx                           # 改：chip + 匯入匯出
│   ├── Offline.tsx                            # 改：upload + JobList
│   ├── Editor.tsx                             # 改：view/edit 切換
│   └── System.tsx                             # 改：4 panel + polling
├── App.tsx                                    # 微改：補其他 route 為 redirect+toast
├── main.tsx                                   # 微改：mount Toast
└── index.html                                 # 改：載 Inter / JetBrains Mono
```

---

## Backend Tasks

### Task 1: 補 ErrorCode.INVALID_SEGMENTS 與 conftest TestClient fixture

**Files:**
- Modify: `backend/app/errors.py`
- Modify: `backend/tests/conftest.py`

- [ ] **Step 1: 新增 ErrorCode 與 HTTP status 對應**

修改 `backend/app/errors.py`，在「Inference errors」區段下方加 enum：

```python
    # === Job segments validation ===
    INVALID_SEGMENTS = "invalid_segments"
```

在 `HTTP_STATUS_FOR_CODE` dict 加：

```python
    ErrorCode.INVALID_SEGMENTS: 400,
```

- [ ] **Step 2: 跑既有 test_errors 確認沒回歸**

```bash
docker compose exec backend pytest tests/test_errors.py -v
```

預期：所有 tests pass（`test_every_error_code_has_http_status_mapping` 會驗證新 enum 有 mapping）。

- [ ] **Step 3: 在 conftest 補 app_client fixture**

修改 `backend/tests/conftest.py`，加 import 與 fixture：

```python
"""Shared pytest fixtures."""
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path: Path, monkeypatch):
    """Each test gets its own temp data dir."""
    monkeypatch.setenv("BACKEND_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BACKEND_DB_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")
    yield


@pytest_asyncio.fixture
async def app_client() -> AsyncIterator:
    """FastAPI app with isolated DB schema (tables created per test)."""
    # 清掉 cached settings 確保讀到 monkeypatched env
    from app.config import get_settings
    get_settings.cache_clear()

    # 重 import 以套用新 env
    from app.db import Base, engine
    from httpx import ASGITransport, AsyncClient

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
```

- [ ] **Step 4: 寫 fixture smoke test 驗證可用**

建 `backend/tests/test_app_client_smoke.py`：

```python
"""Smoke test for app_client fixture."""
import pytest


@pytest.mark.asyncio
async def test_app_client_healthz(app_client):
    r = await app_client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
```

- [ ] **Step 5: 跑 fixture smoke**

```bash
docker compose exec backend pytest tests/test_app_client_smoke.py -v
```

預期：1 passed。

- [ ] **Step 6: Commit**

```bash
git add backend/app/errors.py backend/tests/conftest.py backend/tests/test_app_client_smoke.py
git commit -m "test: 補 INVALID_SEGMENTS enum 與 FastAPI TestClient fixture"
```

---

### Task 2: PATCH `/api/admin/jobs/{id}/segments`

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routes/admin/jobs.py`
- Create: `backend/tests/test_admin_jobs_segments.py`

- [ ] **Step 1: 加 SegmentsPatchIn schema**

修改 `backend/app/schemas.py`，在 Job 區段（`class JobCreatedOut` 之後）加：

```python
class SegmentsPatchIn(BaseModel):
    segments: list[Segment]
```

- [ ] **Step 2: 寫 happy-path RED test**

建 `backend/tests/test_admin_jobs_segments.py`：

```python
"""Tests for PATCH /api/admin/jobs/{id}/segments."""
from __future__ import annotations

import pytest

from app.db import db_session
from app.models import Job, JobSource, JobStatus, Project


async def _seed_project_and_job(*, segments=None):
    async with db_session() as db:
        p = Project(name="proj", hotwords=[])
        db.add(p)
        await db.flush()
        j = Job(
            id="job-1",
            project_id=p.id,
            source=JobSource.ADMIN_UPLOAD,
            filename="a.wav",
            audio_path="/tmp/a.wav",
            duration_sec=10.0,
            status=JobStatus.DONE,
            segments=segments,
            used_hotwords=[],
        )
        db.add(j)
        await db.commit()
        return p.id, j.id


@pytest.mark.asyncio
async def test_patch_segments_replaces_segments(app_client):
    _, job_id = await _seed_project_and_job(
        segments=[{"start_time": 0.0, "end_time": 3.0, "speaker_id": 1, "text": "old"}]
    )
    new_segs = [
        {"start_time": 0.0, "end_time": 3.0, "speaker_id": 1, "text": "fixed"},
        {"start_time": 3.0, "end_time": 6.0, "speaker_id": 2, "text": "new"},
    ]
    r = await app_client.patch(
        f"/api/admin/jobs/{job_id}/segments",
        json={"segments": new_segs},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["segments"]) == 2
    assert body["segments"][0]["text"] == "fixed"
    assert body["segments"][1]["speaker_id"] == 2
```

- [ ] **Step 3: 跑 RED 確認 fail**

```bash
docker compose exec backend pytest tests/test_admin_jobs_segments.py::test_patch_segments_replaces_segments -v
```

預期：FAIL（endpoint 尚未實作；可能 404 或 405）。

- [ ] **Step 4: 實作 PATCH endpoint**

修改 `backend/app/routes/admin/jobs.py`：

(a) 加 import：

```python
from app.schemas import JobCreatedOut, JobOut, SegmentsPatchIn, Segment
```

(b) 在既有 endpoints 後（`stream_audio` 之後）插入：

```python
@router.patch("/jobs/{job_id}/segments", response_model=JobOut)
async def patch_segments(
    job_id: str,
    payload: SegmentsPatchIn,
    db: AsyncSession = Depends(get_db),
):
    """更新 Job.segments（用於 TranscriptEditor 自動儲存）。"""
    job = await _get_job_or_404(db, job_id)
    _validate_segments(payload.segments)
    job.segments = [s.model_dump() for s in payload.segments]
    await db.flush()
    await db.refresh(job)
    return job
```

(c) 在「Helpers — fetch / cleanup」區段加 helper：

```python
def _validate_segments(segments: list[Segment]) -> None:
    if not segments:
        raise http_error(
            ErrorCode.INVALID_SEGMENTS, "segments must not be empty"
        )
    last_end = -1.0
    for i, s in enumerate(segments):
        if s.start_time >= s.end_time:
            raise http_error(
                ErrorCode.INVALID_SEGMENTS,
                f"segment[{i}] start ({s.start_time}) >= end ({s.end_time})",
            )
        if s.start_time < last_end:
            raise http_error(
                ErrorCode.INVALID_SEGMENTS,
                f"segment[{i}] overlaps previous (start {s.start_time} < prev end {last_end})",
            )
        if s.speaker_id < 1:
            raise http_error(
                ErrorCode.INVALID_SEGMENTS,
                f"segment[{i}] speaker_id must be >= 1, got {s.speaker_id}",
            )
        if not s.text.strip():
            raise http_error(
                ErrorCode.INVALID_SEGMENTS, f"segment[{i}] text is empty"
            )
        last_end = s.end_time
```

- [ ] **Step 5: 跑 GREEN**

```bash
docker compose exec backend pytest tests/test_admin_jobs_segments.py::test_patch_segments_replaces_segments -v
```

預期：PASS。

- [ ] **Step 6: 補 invalid-cases test**

在 `test_admin_jobs_segments.py` 加：

```python
@pytest.mark.asyncio
@pytest.mark.parametrize("segs,expected_msg", [
    # empty
    ([], "must not be empty"),
    # start >= end
    ([{"start_time": 5.0, "end_time": 3.0, "speaker_id": 1, "text": "x"}],
     "start"),
    # overlap
    (
        [
            {"start_time": 0.0, "end_time": 5.0, "speaker_id": 1, "text": "a"},
            {"start_time": 4.0, "end_time": 6.0, "speaker_id": 1, "text": "b"},
        ],
        "overlaps",
    ),
    # speaker_id < 1
    ([{"start_time": 0.0, "end_time": 1.0, "speaker_id": 0, "text": "x"}],
     "speaker_id"),
    # empty text
    ([{"start_time": 0.0, "end_time": 1.0, "speaker_id": 1, "text": "  "}],
     "text is empty"),
])
async def test_patch_segments_invalid(app_client, segs, expected_msg):
    _, job_id = await _seed_project_and_job(segments=[])
    r = await app_client.patch(
        f"/api/admin/jobs/{job_id}/segments", json={"segments": segs}
    )
    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["code"] == "invalid_segments"
    assert expected_msg in body["detail"]["detail"]


@pytest.mark.asyncio
async def test_patch_segments_404(app_client):
    r = await app_client.patch(
        "/api/admin/jobs/nonexistent/segments", json={"segments": []}
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "job_not_found"
```

- [ ] **Step 7: 跑全 test_admin_jobs_segments**

```bash
docker compose exec backend pytest tests/test_admin_jobs_segments.py -v
```

預期：6+ tests pass。

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas.py backend/app/routes/admin/jobs.py backend/tests/test_admin_jobs_segments.py
git commit -m "feat(api): add PATCH /api/admin/jobs/{id}/segments + 驗證"
```

---

### Task 3: GET `/api/admin/projects/{id}/hotwords/export`

**Files:**
- Modify: `backend/app/routes/admin/projects.py`
- Create: `backend/tests/test_admin_hotwords_io.py`

- [ ] **Step 1: 寫 RED test**

建 `backend/tests/test_admin_hotwords_io.py`：

```python
"""Tests for hotwords import / export endpoints."""
from __future__ import annotations

import pytest

from app.db import db_session
from app.models import Project


async def _seed_project(name: str = "p", hotwords: list[str] | None = None) -> int:
    async with db_session() as db:
        p = Project(name=name, hotwords=hotwords or [])
        db.add(p)
        await db.commit()
        return p.id


@pytest.mark.asyncio
async def test_export_basic(app_client):
    pid = await _seed_project("export-1", ["alpha", "beta", "gamma"])
    r = await app_client.get(f"/api/admin/projects/{pid}/hotwords/export?format=txt")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "attachment" in r.headers["content-disposition"]
    assert r.text == "alpha\nbeta\ngamma\n"


@pytest.mark.asyncio
async def test_export_chinese(app_client):
    pid = await _seed_project("export-2", ["糖尿病", "胰島素"])
    r = await app_client.get(f"/api/admin/projects/{pid}/hotwords/export?format=txt")
    assert r.status_code == 200
    assert r.text == "糖尿病\n胰島素\n"


@pytest.mark.asyncio
async def test_export_empty(app_client):
    pid = await _seed_project("export-3", [])
    r = await app_client.get(f"/api/admin/projects/{pid}/hotwords/export?format=txt")
    assert r.status_code == 200
    assert r.text == ""


@pytest.mark.asyncio
async def test_export_404(app_client):
    r = await app_client.get("/api/admin/projects/9999/hotwords/export?format=txt")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_export_unsupported_format(app_client):
    pid = await _seed_project("export-4", ["x"])
    r = await app_client.get(f"/api/admin/projects/{pid}/hotwords/export?format=csv")
    assert r.status_code == 400
    assert "format" in r.json()["detail"]["detail"].lower()
```

- [ ] **Step 2: 跑 RED 確認 fail**

```bash
docker compose exec backend pytest tests/test_admin_hotwords_io.py::test_export_basic -v
```

預期：FAIL（endpoint 不存在）。

- [ ] **Step 3: 實作 export endpoint**

修改 `backend/app/routes/admin/projects.py`：

(a) 補 import：

```python
import re
from datetime import datetime
from fastapi.responses import PlainTextResponse
```

(b) 在 hotwords shortcut 區段下方加 endpoint：

```python
@router.get("/projects/{project_id}/hotwords/export")
async def export_hotwords(
    project_id: int,
    format: str = "txt",
    db: AsyncSession = Depends(get_db),
):
    """匯出 project hotwords。M3 階段僅支援 txt（一詞一行 UTF-8）。"""
    if format != "txt":
        from app.errors import ErrorCode, http_error
        raise http_error(
            ErrorCode.UNSUPPORTED_FORMAT,
            f"format {format!r} not supported (only 'txt')",
        )
    project = await _get_or_404(db, project_id)
    body = "\n".join(project.hotwords or []) + ("\n" if project.hotwords else "")
    safe_name = re.sub(r"[^\w\-]+", "-", project.name).strip("-") or "project"
    today = datetime.utcnow().strftime("%Y%m%d")
    filename = f"hotwords-{safe_name}-{today}.txt"
    return PlainTextResponse(
        content=body,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        media_type="text/plain; charset=utf-8",
    )
```

- [ ] **Step 4: 跑 GREEN**

```bash
docker compose exec backend pytest tests/test_admin_hotwords_io.py -v -k export
```

預期：5 tests pass。

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/admin/projects.py backend/tests/test_admin_hotwords_io.py
git commit -m "feat(api): add GET /api/admin/projects/{id}/hotwords/export"
```

---

### Task 4: POST `/api/admin/projects/{id}/hotwords/import`

**Files:**
- Modify: `backend/app/routes/admin/projects.py`
- Modify: `backend/tests/test_admin_hotwords_io.py`

- [ ] **Step 1: 寫 RED test**

修改 `backend/tests/test_admin_hotwords_io.py`，在檔尾加：

```python
@pytest.mark.asyncio
async def test_import_replace(app_client):
    pid = await _seed_project("imp-1", ["old1", "old2"])
    r = await app_client.post(
        f"/api/admin/projects/{pid}/hotwords/import",
        files={"file": ("h.txt", b"newA\nnewB\nnewC\n", "text/plain")},
        data={"mode": "replace"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["hotwords"] == ["newA", "newB", "newC"]
    assert body["replaced"] == 2
    assert body["added"] == 3
    assert body["skipped_duplicates"] == 0


@pytest.mark.asyncio
async def test_import_append_dedupe(app_client):
    pid = await _seed_project("imp-2", ["alpha", "beta"])
    r = await app_client.post(
        f"/api/admin/projects/{pid}/hotwords/import",
        files={"file": ("h.txt", b"beta\ngamma\nalpha\ndelta\n", "text/plain")},
        data={"mode": "append"},
    )
    assert r.status_code == 200
    body = r.json()
    # 順序：原 list 先、新詞接尾、重複略過
    assert body["hotwords"] == ["alpha", "beta", "gamma", "delta"]
    assert body["added"] == 2
    assert body["skipped_duplicates"] == 2


@pytest.mark.asyncio
async def test_import_strips_blank_lines(app_client):
    pid = await _seed_project("imp-3", [])
    r = await app_client.post(
        f"/api/admin/projects/{pid}/hotwords/import",
        files={"file": ("h.txt", b"  word1  \n\n   \nword2\n\n", "text/plain")},
        data={"mode": "replace"},
    )
    assert r.status_code == 200
    assert r.json()["hotwords"] == ["word1", "word2"]


@pytest.mark.asyncio
async def test_import_utf8_chinese(app_client):
    pid = await _seed_project("imp-4", [])
    body = "糖尿病\n胰島素\n".encode("utf-8")
    r = await app_client.post(
        f"/api/admin/projects/{pid}/hotwords/import",
        files={"file": ("h.txt", body, "text/plain")},
        data={"mode": "replace"},
    )
    assert r.status_code == 200
    assert r.json()["hotwords"] == ["糖尿病", "胰島素"]


@pytest.mark.asyncio
async def test_import_too_large(app_client):
    pid = await _seed_project("imp-5", [])
    big = b"x" * (1024 * 1024 + 1)  # 1 MB + 1
    r = await app_client.post(
        f"/api/admin/projects/{pid}/hotwords/import",
        files={"file": ("h.txt", big, "text/plain")},
        data={"mode": "replace"},
    )
    assert r.status_code == 413
    assert r.json()["detail"]["code"] == "upload_too_large"


@pytest.mark.asyncio
async def test_import_bad_mode(app_client):
    pid = await _seed_project("imp-6", [])
    r = await app_client.post(
        f"/api/admin/projects/{pid}/hotwords/import",
        files={"file": ("h.txt", b"x\n", "text/plain")},
        data={"mode": "merge"},
    )
    assert r.status_code == 400
```

- [ ] **Step 2: 跑 RED**

```bash
docker compose exec backend pytest tests/test_admin_hotwords_io.py -v -k import
```

預期：6 tests fail（endpoint 不存在）。

- [ ] **Step 3: 實作 import endpoint**

修改 `backend/app/routes/admin/projects.py`，補 import：

```python
from typing import Literal

from fastapi import File, Form, UploadFile

from app.errors import ErrorCode, http_error
```

在 `export_hotwords` 之後加：

```python
@router.post("/projects/{project_id}/hotwords/import")
async def import_hotwords(
    project_id: int,
    file: UploadFile = File(...),
    mode: Literal["append", "replace"] = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """匯入 hotwords。Mode：append（與現有 list 取聯集，保留順序）/ replace（整批換）。"""
    project = await _get_or_404(db, project_id)
    contents = await file.read()
    if len(contents) > 1024 * 1024:
        raise http_error(
            ErrorCode.UPLOAD_TOO_LARGE,
            f"hotwords import upload {len(contents)} bytes exceeds 1 MB limit",
        )
    new_words = _parse_hotwords_txt(contents)

    existing = list(project.hotwords or [])
    if mode == "replace":
        merged = new_words
        added = len(new_words)
        replaced = len(existing)
        skipped = 0
    else:  # append
        seen = set(existing)
        added_words = [w for w in new_words if w not in seen]
        skipped = len(new_words) - len(added_words)
        merged = existing + added_words
        added = len(added_words)
        replaced = 0

    project.hotwords = merged
    await db.flush()
    return {
        "hotwords": merged,
        "added": added,
        "replaced": replaced,
        "skipped_duplicates": skipped,
    }


def _parse_hotwords_txt(contents: bytes) -> list[str]:
    """Decode UTF-8、splitlines、trim、過濾空行。"""
    text = contents.decode("utf-8", errors="replace")
    return [line.strip() for line in text.splitlines() if line.strip()]
```

- [ ] **Step 4: 跑 GREEN**

```bash
docker compose exec backend pytest tests/test_admin_hotwords_io.py -v
```

預期：11 tests pass（5 export + 6 import）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/admin/projects.py backend/tests/test_admin_hotwords_io.py
git commit -m "feat(api): add POST /api/admin/projects/{id}/hotwords/import"
```

---

### Task 5: Backend 全套 regression + push

**Files:** 無新增；驗證既有測試。

- [ ] **Step 1: 跑全部 backend tests**

```bash
docker compose exec backend pytest tests/ -v --no-header
```

預期：M2 既有 129 + 新增 ~12 = 141 pass。

- [ ] **Step 2: Lint + type-check**

```bash
docker compose exec backend ruff check app/
docker compose exec backend mypy app/
```

預期：ruff 0 errors；mypy 警告（非 error）可接受。

- [ ] **Step 3: Push backend 段**

```bash
git push origin claude/crazy-rosalind-88a69d
```

---

## Frontend Tasks

> **測試政策（重申）:** Frontend 不寫 unit test（spec §11.2）。每個 task commit 前必須跑：
> ```bash
> cd frontend && npm run typecheck && npm run lint
> ```
> 並在 dev server 中手動驗證該 task 互動。

### Task 6: Frontend types 對齊 backend

**Files:** Modify `frontend/src/api/types.ts`

- [ ] **Step 1: 重寫 types.ts**

替換 `frontend/src/api/types.ts` 整個檔案內容：

```typescript
// 與 backend/app/schemas.py 對齊
// 變更時兩邊必須同步

// === Common ===

export interface Segment {
  start_time: number;
  end_time: number;
  speaker_id: number;
  text: string;
}

export interface ApiErrorBody {
  code: string;
  detail: string;
  [key: string]: unknown;
}

// === Project ===

export interface ProjectIn {
  name: string;
  description?: string;
  hotwords?: string[];
  webhook_url?: string;
}

export interface ProjectPatch {
  name?: string;
  description?: string;
  hotwords?: string[];
  webhook_url?: string;
}

export interface ProjectOut {
  id: number;
  name: string;
  description: string | null;
  hotwords: string[];
  active_model_id: number | null;
  webhook_url: string | null;
  created_at: string;
  updated_at: string;
}

// === Job ===

export type JobStatus = "pending" | "queued" | "running" | "done" | "failed" | "cancelled";
export type JobSource = "admin_upload" | "v1_api_async" | "v1_api_sync" | "v1_api_ws";

export interface JobOut {
  id: string;
  project_id: number;
  source: JobSource;
  filename: string;
  duration_sec: number | null;
  status: JobStatus;
  progress: number;
  chunks_total: number;
  chunks_done: number;
  segments: Segment[] | null;
  raw_text: string | null;
  error: string | null;
  used_hotwords: string[];
  used_model_id: number | null;
  callback_url: string | null;
  metadata_extra: Record<string, unknown> | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface JobCreatedOut {
  job_id: string;
}

// === System ===

export interface HealthOut {
  ok: boolean;
  vllm_status: string;
  redis_status: string;
  db_status: string;
}

export interface VllmStatusOut {
  status: string;
  model: string | null;
  uptime_sec: number | null;
}

export interface ProfileOut {
  profile: string;
  gpu_inference_devices: string;
  gpu_training_devices: string;
  tensor_parallel: number;
  data_parallel: number;
  max_concurrent_requests: number;
  can_concurrent_train: boolean;
  mock_vllm: boolean;
}

export interface QueueInfo {
  pending: number;
  running: number;
  workers: number;
  oldest_age_sec: number;
}

// === Hotwords I/O ===

export type HotwordsImportMode = "append" | "replace";

export interface HotwordsImportResult {
  hotwords: string[];
  added: number;
  replaced: number;
  skipped_duplicates: number;
}
```

- [ ] **Step 2: typecheck**

```bash
cd frontend && npm run typecheck
```

預期：0 errors（其他 .ts 檔還沒 import 新 types，但 types.ts 自身要 compile 過）。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/types.ts
git commit -m "feat(frontend): types.ts 對齊 M3 backend schemas"
```

---

### Task 7: HTTP client + toastStore + Toast 元件

**Files:**
- Create: `frontend/src/stores/toastStore.ts`
- Create: `frontend/src/hooks/useToast.ts`
- Create: `frontend/src/components/Toast.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: 建 toastStore**

建 `frontend/src/stores/toastStore.ts`：

```typescript
import { create } from "zustand";

export type ToastLevel = "info" | "success" | "warning" | "error";

export interface Toast {
  id: number;
  level: ToastLevel;
  message: string;
  timeoutMs: number;
}

interface ToastState {
  toasts: Toast[];
  push: (level: ToastLevel, message: string, timeoutMs?: number) => void;
  dismiss: (id: number) => void;
}

const defaultTimeouts: Record<ToastLevel, number> = {
  info: 5000,
  success: 3000,
  warning: 5000,
  error: 8000,
};

let nextId = 1;

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (level, message, timeoutMs) => {
    const id = nextId++;
    const t: Toast = {
      id,
      level,
      message,
      timeoutMs: timeoutMs ?? defaultTimeouts[level],
    };
    set((s) => ({ toasts: [...s.toasts, t].slice(-3) }));
    if (t.timeoutMs > 0) {
      setTimeout(() => {
        set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) }));
      }, t.timeoutMs);
    }
  },
  dismiss: (id) =>
    set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
}));
```

- [ ] **Step 2: 建 useToast hook（薄封裝）**

建 `frontend/src/hooks/useToast.ts`：

```typescript
import { useToastStore } from "../stores/toastStore";

export function useToast() {
  const push = useToastStore((s) => s.push);
  return {
    info: (msg: string) => push("info", msg),
    success: (msg: string) => push("success", msg),
    warning: (msg: string) => push("warning", msg),
    error: (msg: string) => push("error", msg),
  };
}
```

- [ ] **Step 3: 建 Toast 元件**

建 `frontend/src/components/Toast.tsx`：

```tsx
import { CheckCircle2, Info, AlertTriangle, XCircle, X } from "lucide-react";
import { useToastStore, type Toast as ToastT } from "../stores/toastStore";

const styles: Record<ToastT["level"], { bg: string; icon: JSX.Element; text: string }> = {
  info: { bg: "bg-blue-50 border-blue-200", text: "text-blue-900",
          icon: <Info className="w-5 h-5 text-blue-500" /> },
  success: { bg: "bg-green-50 border-green-200", text: "text-green-900",
             icon: <CheckCircle2 className="w-5 h-5 text-green-500" /> },
  warning: { bg: "bg-amber-50 border-amber-200", text: "text-amber-900",
             icon: <AlertTriangle className="w-5 h-5 text-amber-500" /> },
  error: { bg: "bg-red-50 border-red-200", text: "text-red-900",
           icon: <XCircle className="w-5 h-5 text-red-500" /> },
};

export function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts);
  const dismiss = useToastStore((s) => s.dismiss);
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-md">
      {toasts.map((t) => {
        const s = styles[t.level];
        return (
          <div
            key={t.id}
            role="status"
            className={`flex items-start gap-3 ${s.bg} ${s.text} border rounded-md px-4 py-3 shadow-md animate-in fade-in slide-in-from-right-4`}
          >
            {s.icon}
            <span className="flex-1 text-sm leading-relaxed whitespace-pre-wrap">
              {t.message}
            </span>
            <button
              type="button"
              aria-label="關閉通知"
              onClick={() => dismiss(t.id)}
              className="cursor-pointer text-current opacity-60 hover:opacity-100 transition-colors duration-200"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 4: 改 client.ts**

替換 `frontend/src/api/client.ts` 整個檔案：

```typescript
import { useToastStore } from "../stores/toastStore";
import type { ApiErrorBody } from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE || "";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    public detail: string,
    public body: ApiErrorBody,
  ) {
    super(`${code}: ${detail}`);
  }
}

interface RequestOpts {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  formData?: FormData;
  query?: Record<string, string | number | undefined>;
  signal?: AbortSignal;
  responseType?: "json" | "blob" | "text";
}

function _toUserMessage(status: number, body: ApiErrorBody | null): string {
  if (status === 401) return "請重新登入";
  if (status >= 500) return "服務異常，請稍後再試";
  if (body?.detail) return body.detail;
  return `錯誤 ${status}`;
}

async function request<T>(path: string, opts: RequestOpts = {}): Promise<T> {
  const url = new URL(BASE_URL + path, window.location.origin);
  if (opts.query) {
    for (const [k, v] of Object.entries(opts.query)) {
      if (v !== undefined && v !== null) url.searchParams.append(k, String(v));
    }
  }

  const init: RequestInit = {
    method: opts.method ?? "GET",
    signal: opts.signal,
  };
  if (opts.formData) {
    init.body = opts.formData;
  } else if (opts.body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(opts.body);
  }

  let resp: Response;
  try {
    resp = await fetch(url.toString(), init);
  } catch (e) {
    useToastStore.getState().push("error", "網路連線失敗");
    throw e;
  }

  if (!resp.ok) {
    let body: ApiErrorBody | null = null;
    try {
      const j = await resp.json();
      body = j.detail && typeof j.detail === "object" ? (j.detail as ApiErrorBody) : null;
    } catch {
      // ignore
    }
    const code = body?.code ?? "http_error";
    const detail = body?.detail ?? `HTTP ${resp.status}`;
    useToastStore.getState().push("error", _toUserMessage(resp.status, body));
    throw new ApiError(resp.status, code, detail, body ?? { code, detail });
  }

  if (opts.responseType === "blob") return (await resp.blob()) as unknown as T;
  if (opts.responseType === "text") return (await resp.text()) as unknown as T;
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export const api = {
  get: <T>(path: string, opts?: Omit<RequestOpts, "method" | "body" | "formData">) =>
    request<T>(path, { ...opts, method: "GET" }),
  post: <T>(path: string, body?: unknown, opts?: Omit<RequestOpts, "method" | "body">) =>
    request<T>(path, { ...opts, method: "POST", body }),
  postForm: <T>(path: string, formData: FormData, opts?: Omit<RequestOpts, "method" | "formData">) =>
    request<T>(path, { ...opts, method: "POST", formData }),
  patch: <T>(path: string, body?: unknown, opts?: Omit<RequestOpts, "method" | "body">) =>
    request<T>(path, { ...opts, method: "PATCH", body }),
  put: <T>(path: string, body?: unknown, opts?: Omit<RequestOpts, "method" | "body">) =>
    request<T>(path, { ...opts, method: "PUT", body }),
  del: <T>(path: string, opts?: Omit<RequestOpts, "method" | "body" | "formData">) =>
    request<T>(path, { ...opts, method: "DELETE" }),
};
```

- [ ] **Step 5: 在 main.tsx mount Toast**

修改 `frontend/src/main.tsx`，在 `<App />` 旁加 ToastContainer。先讀現況：

```bash
cat frontend/src/main.tsx
```

預期內容：

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";
```

替換為：

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ToastContainer } from "./components/Toast";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
      <ToastContainer />
    </BrowserRouter>
  </React.StrictMode>,
);
```

> 若既有 main.tsx 已有 render 區塊（含 createRoot），保留結構僅插入 `<ToastContainer />` 與其 import。

- [ ] **Step 6: typecheck + lint**

```bash
cd frontend && npm run typecheck && npm run lint
```

預期：0 errors。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/stores/toastStore.ts frontend/src/hooks/useToast.ts frontend/src/components/Toast.tsx frontend/src/api/client.ts frontend/src/main.tsx
git commit -m "feat(frontend): 加 toastStore + Toast 元件 + fetch wrapper"
```

---

### Task 8: API modules（projects / jobs / system）

**Files:** Modify `frontend/src/api/projects.ts`、`jobs.ts`、`system.ts`

- [ ] **Step 1: 寫 projects.ts**

替換 `frontend/src/api/projects.ts` 整個檔：

```typescript
import { api } from "./client";
import type {
  HotwordsImportMode,
  HotwordsImportResult,
  ProjectIn,
  ProjectOut,
  ProjectPatch,
} from "./types";

const BASE = "/api/admin/projects";

export const projectsApi = {
  list: () => api.get<ProjectOut[]>(BASE),
  get: (id: number) => api.get<ProjectOut>(`${BASE}/${id}`),
  create: (data: ProjectIn) => api.post<ProjectOut>(BASE, data),
  update: (id: number, data: ProjectPatch) =>
    api.put<ProjectOut>(`${BASE}/${id}`, data),
  remove: (id: number) => api.del<void>(`${BASE}/${id}`),

  // hotwords
  getHotwords: (id: number) => api.get<string[]>(`${BASE}/${id}/hotwords`),
  setHotwords: (id: number, words: string[]) =>
    api.put<string[]>(`${BASE}/${id}/hotwords`, words),

  exportHotwords: async (id: number): Promise<Blob> => {
    return api.get<Blob>(`${BASE}/${id}/hotwords/export`, {
      query: { format: "txt" },
      responseType: "blob",
    });
  },

  importHotwords: (id: number, file: File, mode: HotwordsImportMode) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("mode", mode);
    return api.postForm<HotwordsImportResult>(
      `${BASE}/${id}/hotwords/import`,
      fd,
    );
  },
};
```

- [ ] **Step 2: 寫 jobs.ts**

替換 `frontend/src/api/jobs.ts`：

```typescript
import { api } from "./client";
import type { JobCreatedOut, JobOut, Segment } from "./types";

const ADMIN = "/api/admin";

export const jobsApi = {
  list: (opts: { project_id?: number; status?: string; limit?: number; offset?: number } = {}) =>
    api.get<JobOut[]>(`${ADMIN}/jobs`, { query: opts }),
  get: (id: string) => api.get<JobOut>(`${ADMIN}/jobs/${id}`),
  cancel: (id: string) => api.post<JobOut>(`${ADMIN}/jobs/${id}/cancel`),
  remove: (id: string) => api.del<void>(`${ADMIN}/jobs/${id}`),
  audioUrl: (id: string) => `${import.meta.env.VITE_API_BASE || ""}${ADMIN}/jobs/${id}/audio`,

  upload: (file: File, projectId: number) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("project_id", String(projectId));
    return api.postForm<JobCreatedOut>(`${ADMIN}/transcribe`, fd);
  },

  patchSegments: (id: string, segments: Segment[]) =>
    api.patch<JobOut>(`${ADMIN}/jobs/${id}/segments`, { segments }),
};
```

- [ ] **Step 3: 寫 system.ts**

替換 `frontend/src/api/system.ts`：

```typescript
import { api } from "./client";
import type { HealthOut, ProfileOut, QueueInfo, VllmStatusOut } from "./types";

const ADMIN = "/api/admin";

export const systemApi = {
  health: () => api.get<HealthOut>(`${ADMIN}/system/health`),
  vllmStatus: () => api.get<VllmStatusOut>(`${ADMIN}/system/vllm_status`),
  profile: () => api.get<ProfileOut>(`${ADMIN}/system/profile`),
  queue: () => api.get<QueueInfo>(`${ADMIN}/system/queue`),
};
```

- [ ] **Step 4: 移除既有未用的 api 模組（datasets/training/models/api_keys）**

這些模組屬 M3.5 / M4 / M6，當前 stub 可能型別不對。檢視：

```bash
ls frontend/src/api/
```

對 `datasets.ts` / `training.ts` / `models.ts` / `api_keys.ts`：保留檔案存在但替換為簡單 export（避免引用錯誤）：

例如 `frontend/src/api/datasets.ts`：

```typescript
// M3.5 milestone — 暫保留 export 名稱，正式實作待 M3.5
export const datasetsApi = {};
```

對 training / models / api_keys 同樣處理。

- [ ] **Step 5: typecheck + lint**

```bash
cd frontend && npm run typecheck && npm run lint
```

預期：0 errors。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/
git commit -m "feat(frontend): API modules 對齊 M3 backend"
```

---

### Task 9: projectStore + 路由 redirect

**Files:**
- Modify: `frontend/src/stores/projectStore.ts`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 寫 projectStore**

替換 `frontend/src/stores/projectStore.ts`：

```typescript
import { create } from "zustand";
import { projectsApi } from "../api/projects";
import type { ProjectOut } from "../api/types";

interface ProjectState {
  projects: ProjectOut[];
  loading: boolean;
  loaded: boolean;
  refetch: () => Promise<void>;
  getById: (id: number) => ProjectOut | undefined;
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projects: [],
  loading: false,
  loaded: false,
  refetch: async () => {
    if (get().loading) return;
    set({ loading: true });
    try {
      const projects = await projectsApi.list();
      set({ projects, loaded: true });
    } finally {
      set({ loading: false });
    }
  },
  getById: (id) => get().projects.find((p) => p.id === id),
}));
```

- [ ] **Step 2: 改 App.tsx 的未實作 routes**

替換 `frontend/src/App.tsx`：

```tsx
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useEffect } from "react";
import { Sidebar } from "./components/Sidebar";
import { useToast } from "./hooks/useToast";

import Projects from "./pages/Projects";
import Hotwords from "./pages/Hotwords";
import Offline from "./pages/Offline";
import Editor from "./pages/Editor";
import System from "./pages/System";

function NotImplemented({ pageName }: { pageName: string }) {
  const toast = useToast();
  useEffect(() => {
    toast.info(`「${pageName}」頁面尚未開放（M3.5+ 才實作）`);
  }, [pageName]);
  return <Navigate to="/" replace />;
}

export default function App() {
  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        <Routes>
          <Route path="/" element={<Projects />} />
          <Route path="/projects/:id/hotwords" element={<Hotwords />} />
          <Route path="/projects/:id/offline" element={<Offline />} />
          <Route path="/projects/:id/edit/:itemId" element={<Editor />} />
          <Route path="/system" element={<System />} />

          {/* M3 不實作的頁面：toast 提示後 redirect */}
          <Route path="/projects/:id/datasets" element={<NotImplemented pageName="資料集" />} />
          <Route path="/projects/:id/training" element={<NotImplemented pageName="訓練" />} />
          <Route path="/projects/:id/training/:runId" element={<NotImplemented pageName="訓練" />} />
          <Route path="/projects/:id/models" element={<NotImplemented pageName="模型" />} />
          <Route path="/projects/:id/api_keys" element={<NotImplemented pageName="API Keys" />} />
          <Route path="/projects/:id/webhook" element={<NotImplemented pageName="Webhook" />} />
          <Route path="/projects/:id/integration_calls" element={<NotImplemented pageName="整合紀錄" />} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
```

- [ ] **Step 3: typecheck**

```bash
cd frontend && npm run typecheck
```

預期：0 errors（Sidebar 等元件還沒改，但既有 stub export 應仍可 import）。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/stores/projectStore.ts frontend/src/App.tsx
git commit -m "feat(frontend): projectStore + routes redirect 未實作頁面"
```

---

### Task 10: Sidebar（兩層結構）

**Files:** Modify `frontend/src/components/Sidebar.tsx`

- [ ] **Step 1: 寫 Sidebar**

替換 `frontend/src/components/Sidebar.tsx`：

```tsx
import { ChevronDown, Plus, Hash, Upload, Edit3, Activity } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useProjectStore } from "../stores/projectStore";

const SUBPAGES = [
  { key: "hotwords", label: "Hotwords", icon: Hash },
  { key: "offline", label: "離線轉錄", icon: Upload },
  { key: "edit", label: "校正工作台", icon: Edit3, hidden: true }, // 從 Offline 進入，不直接顯示
] as const;

export function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const params = useParams();
  const { projects, loaded, refetch } = useProjectStore();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!loaded) refetch();
  }, [loaded]);

  const projectIdRaw = params.id ?? location.pathname.match(/^\/projects\/(\d+)/)?.[1];
  const projectId = projectIdRaw ? Number(projectIdRaw) : null;
  const currentProject = projectId ? projects.find((p) => p.id === projectId) : null;

  const currentSub = location.pathname.match(/^\/projects\/\d+\/(\w+)/)?.[1];
  const isSystem = location.pathname.startsWith("/system");

  return (
    <aside className="w-60 bg-slate-900 text-slate-200 flex flex-col h-screen sticky top-0 shrink-0">
      {/* brand */}
      <div className="px-4 py-4 border-b border-slate-800">
        <Link to="/" className="text-base font-semibold text-white tracking-wide cursor-pointer hover:text-blue-300 transition-colors duration-200">
          VibeVoice ASR
        </Link>
      </div>

      {/* project switcher */}
      <div className="px-2 py-3 border-b border-slate-800 relative">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="w-full flex items-center gap-2 px-2 py-2 rounded text-left cursor-pointer hover:bg-slate-800 transition-colors duration-200"
        >
          <span className="flex-1 truncate text-sm">
            {currentProject ? currentProject.name : "選擇專案"}
          </span>
          <ChevronDown className={`w-4 h-4 transition-transform ${open ? "rotate-180" : ""}`} />
        </button>
        {open && (
          <div className="absolute left-2 right-2 top-full mt-1 bg-slate-800 border border-slate-700 rounded shadow-lg z-10 max-h-72 overflow-auto">
            {projects.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => {
                  setOpen(false);
                  // 切 project 維持子頁
                  const sub = currentSub && SUBPAGES.some((s) => s.key === currentSub)
                    ? currentSub
                    : "hotwords";
                  navigate(`/projects/${p.id}/${sub}`);
                }}
                className={`block w-full text-left px-3 py-2 text-sm cursor-pointer hover:bg-slate-700 transition-colors duration-200 ${currentProject?.id === p.id ? "bg-slate-700 text-white" : ""}`}
              >
                {p.name}
              </button>
            ))}
            <Link
              to="/"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-3 py-2 text-sm text-blue-400 cursor-pointer hover:bg-slate-700 transition-colors duration-200 border-t border-slate-700"
            >
              <Plus className="w-4 h-4" /> 管理 / 新增專案
            </Link>
          </div>
        )}
      </div>

      {/* 本專案子頁 */}
      <nav className="flex-1 px-2 py-2 overflow-auto">
        <div className="text-xs uppercase text-slate-500 px-2 py-1 tracking-wider">本專案</div>
        {projectId && SUBPAGES.filter((s) => !s.hidden).map((s) => {
          const active = currentSub === s.key;
          return (
            <Link
              key={s.key}
              to={`/projects/${projectId}/${s.key}`}
              className={`flex items-center gap-2 px-2 py-2 my-0.5 rounded text-sm cursor-pointer transition-colors duration-200 ${
                active ? "bg-blue-500/20 text-white border-l-2 border-blue-400 pl-1.5" : "hover:bg-slate-800"
              }`}
            >
              <s.icon className="w-4 h-4" /> {s.label}
            </Link>
          );
        })}
        {!projectId && (
          <p className="px-2 py-2 text-xs text-slate-500">未選擇專案</p>
        )}
      </nav>

      {/* System 底部 */}
      <div className="px-2 py-3 border-t border-slate-800">
        <div className="text-xs uppercase text-slate-500 px-2 py-1 tracking-wider">系統</div>
        <Link
          to="/system"
          className={`flex items-center gap-2 px-2 py-2 rounded text-sm cursor-pointer transition-colors duration-200 ${
            isSystem ? "bg-blue-500/20 text-white border-l-2 border-blue-400 pl-1.5" : "hover:bg-slate-800"
          }`}
        >
          <Activity className="w-4 h-4" /> 服務狀態
        </Link>
      </div>
    </aside>
  );
}
```

- [ ] **Step 2: typecheck + 啟動 dev 手動驗證**

```bash
cd frontend && npm run typecheck
```

預期：0 errors。

啟動 dev：

```bash
cd frontend && npm run dev
```

開啟 http://localhost:5173，確認 Sidebar 顯示、專案 dropdown 可開合（即使 projects 還是空 list）、System 連結可達。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Sidebar.tsx
git commit -m "feat(frontend): Sidebar 兩層結構（project switcher + 子頁 + 系統）"
```

---

### Task 11: Projects 頁

**Files:**
- Modify: `frontend/src/pages/Projects.tsx`
- Create: `frontend/src/components/ProjectFormModal.tsx`

- [ ] **Step 1: 寫 ProjectFormModal**

建 `frontend/src/components/ProjectFormModal.tsx`：

```tsx
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { X } from "lucide-react";
import type { ProjectOut } from "../api/types";

const schema = z.object({
  name: z.string().min(1, "必填").max(100),
  description: z.string().optional(),
  webhook_url: z.string().url("格式不正確").optional().or(z.literal("")),
  hotwords_text: z.string().optional(), // 逗號或換行分隔
});

type FormValues = z.infer<typeof schema>;

interface Props {
  open: boolean;
  onClose: () => void;
  initial?: ProjectOut;
  onSubmit: (data: { name: string; description?: string; webhook_url?: string; hotwords: string[] }) => Promise<void>;
}

function parseHotwords(text: string | undefined): string[] {
  if (!text) return [];
  return text
    .split(/[,\n]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function ProjectFormModal({ open, onClose, initial, onSubmit }: Props) {
  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } =
    useForm<FormValues>({ resolver: zodResolver(schema) });

  useEffect(() => {
    if (open) {
      reset({
        name: initial?.name ?? "",
        description: initial?.description ?? "",
        webhook_url: initial?.webhook_url ?? "",
        hotwords_text: (initial?.hotwords ?? []).join("\n"),
      });
    }
  }, [open, initial, reset]);

  if (!open) return null;

  const submit = handleSubmit(async (values) => {
    await onSubmit({
      name: values.name.trim(),
      description: values.description?.trim() || undefined,
      webhook_url: values.webhook_url?.trim() || undefined,
      hotwords: parseHotwords(values.hotwords_text),
    });
    onClose();
  });

  return (
    <div className="fixed inset-0 z-40 bg-slate-900/40 flex items-center justify-center p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" className="bg-white rounded-lg shadow-xl max-w-lg w-full p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-slate-900">{initial ? "編輯專案" : "新增專案"}</h3>
          <button type="button" aria-label="關閉" onClick={onClose} className="cursor-pointer text-slate-500 hover:text-slate-700 transition-colors duration-200"><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-sm text-slate-700 mb-1">名稱</label>
            <input {...register("name")} className="w-full border border-slate-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            {errors.name && <p className="text-xs text-red-600 mt-1">{errors.name.message}</p>}
          </div>
          <div>
            <label className="block text-sm text-slate-700 mb-1">描述（選填）</label>
            <textarea {...register("description")} rows={2} className="w-full border border-slate-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
          <div>
            <label className="block text-sm text-slate-700 mb-1">Webhook URL（選填）</label>
            <input {...register("webhook_url")} className="w-full border border-slate-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            {errors.webhook_url && <p className="text-xs text-red-600 mt-1">{errors.webhook_url.message}</p>}
          </div>
          <div>
            <label className="block text-sm text-slate-700 mb-1">Hotwords（逗號或換行分隔，可在 Hotwords 頁細部編輯）</label>
            <textarea {...register("hotwords_text")} rows={3} className="w-full border border-slate-300 rounded px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="微軟, VibeVoice, ..." />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-600 cursor-pointer hover:text-slate-900 transition-colors duration-200">取消</button>
            <button type="submit" disabled={isSubmitting} className="px-4 py-2 text-sm bg-blue-500 text-white rounded cursor-pointer hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200">{isSubmitting ? "儲存中..." : "儲存"}</button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

需 `@hookform/resolvers`。檢查：

```bash
cd frontend && npm ls @hookform/resolvers 2>&1 | head -3
```

若未裝：

```bash
cd frontend && npm install @hookform/resolvers
```

- [ ] **Step 2: 寫 Projects 頁**

替換 `frontend/src/pages/Projects.tsx`：

```tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Edit2, Trash2, MoreVertical } from "lucide-react";
import { ProjectFormModal } from "../components/ProjectFormModal";
import { projectsApi } from "../api/projects";
import { useProjectStore } from "../stores/projectStore";
import { useToast } from "../hooks/useToast";
import type { ProjectOut } from "../api/types";

export default function Projects() {
  const { projects, loaded, refetch } = useProjectStore();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<ProjectOut | undefined>();
  const toast = useToast();

  useEffect(() => {
    if (!loaded) refetch();
  }, [loaded]);

  const onCreate = async (data: { name: string; description?: string; webhook_url?: string; hotwords: string[] }) => {
    await projectsApi.create(data);
    toast.success(`已建立專案「${data.name}」`);
    await refetch();
  };

  const onEdit = async (data: { name: string; description?: string; webhook_url?: string; hotwords: string[] }) => {
    if (!editing) return;
    await projectsApi.update(editing.id, data);
    toast.success(`已更新「${data.name}」`);
    setEditing(undefined);
    await refetch();
  };

  const onDelete = async (p: ProjectOut) => {
    if (!confirm(`確定刪除專案「${p.name}」？此動作無法復原。`)) return;
    try {
      await projectsApi.remove(p.id);
      toast.success(`已刪除「${p.name}」`);
      await refetch();
    } catch {
      // client.ts 已 toast
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-6 py-6">
      <header className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-slate-900">專案列表</h1>
        <button type="button" onClick={() => setOpen(true)} className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded cursor-pointer hover:bg-blue-600 transition-colors duration-200">
          <Plus className="w-4 h-4" /> 新增專案
        </button>
      </header>

      {projects.length === 0 && loaded && (
        <div className="bg-white border border-slate-200 rounded-lg p-12 text-center">
          <p className="text-slate-600 mb-4">尚未建立任何專案</p>
          <button type="button" onClick={() => setOpen(true)} className="px-4 py-2 bg-blue-500 text-white rounded cursor-pointer hover:bg-blue-600 transition-colors duration-200">建立第一個專案</button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {projects.map((p) => (
          <div key={p.id} className="bg-white border border-slate-200 rounded-lg p-4 hover:shadow-md transition-shadow duration-200 group relative">
            <Link to={`/projects/${p.id}/hotwords`} className="block cursor-pointer">
              <h3 className="font-semibold text-slate-900 mb-1 truncate">{p.name}</h3>
              <p className="text-sm text-slate-600 mb-3 line-clamp-2 min-h-[2.5em]">{p.description || "—"}</p>
              <div className="text-xs text-slate-500 flex gap-3">
                <span>{p.hotwords.length} hotwords</span>
                <span>更新 {new Date(p.updated_at).toLocaleDateString("zh-TW")}</span>
              </div>
            </Link>
            <ProjectMenu p={p} onEdit={() => setEditing(p)} onDelete={() => onDelete(p)} />
          </div>
        ))}
      </div>

      <ProjectFormModal
        open={open || !!editing}
        onClose={() => { setOpen(false); setEditing(undefined); }}
        initial={editing}
        onSubmit={editing ? onEdit : onCreate}
      />
    </div>
  );
}

function ProjectMenu({ p, onEdit, onDelete }: { p: ProjectOut; onEdit: () => void; onDelete: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="absolute top-3 right-3" onClick={(e) => e.preventDefault()}>
      <button type="button" aria-label="專案動作" onClick={(e) => { e.preventDefault(); setOpen((v) => !v); }} className="p-1 rounded cursor-pointer text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors duration-200">
        <MoreVertical className="w-4 h-4" />
      </button>
      {open && (
        <div className="absolute right-0 mt-1 bg-white border border-slate-200 rounded shadow-lg z-10 min-w-[7rem]" onMouseLeave={() => setOpen(false)}>
          <button type="button" onClick={() => { setOpen(false); onEdit(); }} className="flex items-center gap-2 w-full px-3 py-2 text-sm text-slate-700 cursor-pointer hover:bg-slate-50 transition-colors duration-200"><Edit2 className="w-4 h-4" /> 編輯</button>
          <button type="button" onClick={() => { setOpen(false); onDelete(); }} className="flex items-center gap-2 w-full px-3 py-2 text-sm text-red-600 cursor-pointer hover:bg-red-50 transition-colors duration-200"><Trash2 className="w-4 h-4" /> 刪除</button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: typecheck + lint + 手動驗證**

```bash
cd frontend && npm run typecheck && npm run lint
```

啟動 dev 在瀏覽器測：建立、編輯、刪除一個 project，看 toast 與卡片更新。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Projects.tsx frontend/src/components/ProjectFormModal.tsx frontend/package.json frontend/package-lock.json
git commit -m "feat(frontend): Projects 頁卡片網格 + Create/Edit modal"
```

---

### Task 12: Hotwords 頁 + chip + 匯入匯出

**Files:**
- Modify: `frontend/src/components/HotwordsChips.tsx`
- Modify: `frontend/src/pages/Hotwords.tsx`
- Create: `frontend/src/components/HotwordsImportModal.tsx`

- [ ] **Step 1: 寫 HotwordsChips**

替換 `frontend/src/components/HotwordsChips.tsx`：

```tsx
import { X } from "lucide-react";
import { useState } from "react";

interface Props {
  value: string[];
  onChange: (next: string[]) => void;
}

export function HotwordsChips({ value, onChange }: Props) {
  const [draft, setDraft] = useState("");

  const commit = () => {
    const tokens = draft.split(/[,\n]/).map((s) => s.trim()).filter(Boolean);
    if (tokens.length === 0) return;
    const next = [...value];
    for (const t of tokens) if (!next.includes(t)) next.push(t);
    onChange(next);
    setDraft("");
  };

  const remove = (i: number) => {
    const next = [...value];
    next.splice(i, 1);
    onChange(next);
  };

  return (
    <div className="flex flex-wrap gap-2 p-3 border border-slate-300 rounded-md bg-white min-h-[3rem] focus-within:ring-2 focus-within:ring-blue-500">
      {value.map((w, i) => (
        <span key={`${w}-${i}`} className="inline-flex items-center gap-1 px-2 py-1 bg-blue-50 text-blue-900 text-sm rounded">
          {w}
          <button type="button" aria-label={`刪除 ${w}`} onClick={() => remove(i)} className="cursor-pointer text-blue-600 hover:text-blue-900 transition-colors duration-200"><X className="w-3 h-3" /></button>
        </span>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            commit();
          } else if (e.key === "Backspace" && draft === "" && value.length > 0) {
            remove(value.length - 1);
          }
        }}
        onBlur={commit}
        placeholder={value.length === 0 ? "輸入 hotwords，Enter 或逗號分隔..." : "+ 新增"}
        className="flex-1 min-w-[8rem] outline-none text-sm bg-transparent"
      />
    </div>
  );
}
```

- [ ] **Step 2: 寫 HotwordsImportModal**

建 `frontend/src/components/HotwordsImportModal.tsx`：

```tsx
import { useState } from "react";
import { X, Upload } from "lucide-react";
import type { HotwordsImportMode } from "../api/types";

interface Props {
  open: boolean;
  onClose: () => void;
  onImport: (file: File, mode: HotwordsImportMode) => Promise<void>;
}

export function HotwordsImportModal({ open, onClose, onImport }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<HotwordsImportMode>("append");
  const [submitting, setSubmitting] = useState(false);

  if (!open) return null;

  const submit = async () => {
    if (!file) return;
    setSubmitting(true);
    try {
      await onImport(file, mode);
      setFile(null);
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-40 bg-slate-900/40 flex items-center justify-center p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" className="bg-white rounded-lg shadow-xl max-w-md w-full p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-slate-900">匯入 Hotwords</h3>
          <button type="button" aria-label="關閉" onClick={onClose} className="cursor-pointer text-slate-500 hover:text-slate-700 transition-colors duration-200"><X className="w-5 h-5" /></button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="block text-sm text-slate-700 mb-2">選擇檔案（.txt，一詞一行 UTF-8，上限 1 MB）</label>
            <input type="file" accept=".txt,text/plain" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="block w-full text-sm cursor-pointer file:mr-3 file:px-3 file:py-1 file:rounded file:border-0 file:bg-blue-50 file:text-blue-700 file:cursor-pointer hover:file:bg-blue-100 file:transition-colors file:duration-200" />
          </div>
          <fieldset>
            <legend className="text-sm text-slate-700 mb-2">模式</legend>
            <label className="flex items-start gap-2 mb-2 cursor-pointer">
              <input type="radio" name="mode" value="append" checked={mode === "append"} onChange={() => setMode("append")} className="mt-1 cursor-pointer" />
              <span className="text-sm">
                <strong>Append</strong>：與現有 list 合併，重複詞自動略過
              </span>
            </label>
            <label className="flex items-start gap-2 cursor-pointer">
              <input type="radio" name="mode" value="replace" checked={mode === "replace"} onChange={() => setMode("replace")} className="mt-1 cursor-pointer" />
              <span className="text-sm">
                <strong>Replace</strong>：清空現有 list 後整批換新（不可復原）
              </span>
            </label>
          </fieldset>
        </div>
        <div className="flex justify-end gap-2 pt-4 mt-4 border-t border-slate-200">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-600 cursor-pointer hover:text-slate-900 transition-colors duration-200">取消</button>
          <button type="button" onClick={submit} disabled={!file || submitting} className="flex items-center gap-2 px-4 py-2 text-sm bg-blue-500 text-white rounded cursor-pointer hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200">
            <Upload className="w-4 h-4" /> {submitting ? "上傳中..." : "匯入"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: 寫 Hotwords 頁**

替換 `frontend/src/pages/Hotwords.tsx`：

```tsx
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Download, Upload as UploadIcon, Save } from "lucide-react";
import { HotwordsChips } from "../components/HotwordsChips";
import { HotwordsImportModal } from "../components/HotwordsImportModal";
import { projectsApi } from "../api/projects";
import { useProjectStore } from "../stores/projectStore";
import { useToast } from "../hooks/useToast";

export default function Hotwords() {
  const { id } = useParams();
  const projectId = Number(id);
  const project = useProjectStore((s) => s.projects.find((p) => p.id === projectId));
  const refetch = useProjectStore((s) => s.refetch);

  const [words, setWords] = useState<string[]>([]);
  const [original, setOriginal] = useState<string[]>([]);
  const [importOpen, setImportOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const toast = useToast();

  useEffect(() => {
    if (!project) refetch();
  }, [project]);

  useEffect(() => {
    if (project) {
      setWords(project.hotwords ?? []);
      setOriginal(project.hotwords ?? []);
    }
  }, [project?.id, project?.updated_at]);

  const dirty = JSON.stringify(words) !== JSON.stringify(original);

  const save = async () => {
    setSaving(true);
    try {
      await projectsApi.setHotwords(projectId, words);
      setOriginal(words);
      toast.success("Hotwords 已儲存");
      await refetch();
    } finally {
      setSaving(false);
    }
  };

  const exportTxt = async () => {
    const blob = await projectsApi.exportHotwords(projectId);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const today = new Date().toISOString().slice(0, 10).replace(/-/g, "");
    const safe = (project?.name ?? "project").replace(/[^\w\-]/g, "-");
    a.download = `hotwords-${safe}-${today}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("已下載");
  };

  const onImport = async (file: File, mode: "append" | "replace") => {
    const result = await projectsApi.importHotwords(projectId, file, mode);
    setWords(result.hotwords);
    setOriginal(result.hotwords);
    await refetch();
    toast.success(
      `匯入完成：新增 ${result.added}、覆蓋 ${result.replaced}、略過 ${result.skipped_duplicates}`
    );
  };

  if (!project) return <div className="p-6">載入中...</div>;

  return (
    <div className="max-w-5xl mx-auto px-6 py-6">
      <header className="flex items-center justify-between mb-4 gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Hotwords</h1>
          <p className="text-sm text-slate-600 mt-1">{project.name}</p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={exportTxt} className="flex items-center gap-2 px-3 py-2 text-sm text-slate-700 border border-slate-300 rounded cursor-pointer hover:bg-slate-50 transition-colors duration-200">
            <Download className="w-4 h-4" /> 匯出
          </button>
          <button type="button" onClick={() => setImportOpen(true)} className="flex items-center gap-2 px-3 py-2 text-sm text-slate-700 border border-slate-300 rounded cursor-pointer hover:bg-slate-50 transition-colors duration-200">
            <UploadIcon className="w-4 h-4" /> 匯入
          </button>
          <button type="button" onClick={save} disabled={!dirty || saving} className="flex items-center gap-2 px-3 py-2 text-sm bg-blue-500 text-white rounded cursor-pointer hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200">
            <Save className="w-4 h-4" /> {saving ? "儲存中..." : "儲存"}
          </button>
        </div>
      </header>

      <HotwordsChips value={words} onChange={setWords} />

      <p className="text-xs text-slate-500 mt-2">
        共 {words.length} 個詞 · 上次更新 {new Date(project.updated_at).toLocaleString("zh-TW")}
        {dirty && <span className="ml-2 text-amber-600">· 有未儲存變更</span>}
      </p>

      <HotwordsImportModal open={importOpen} onClose={() => setImportOpen(false)} onImport={onImport} />
    </div>
  );
}
```

- [ ] **Step 4: 手動驗證**

```bash
cd frontend && npm run typecheck && npm run lint
```

啟動 dev，建立 project，進 Hotwords 加幾個詞、匯出（檔案下載）、匯入（換 mode 試 append/replace）。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/HotwordsChips.tsx frontend/src/components/HotwordsImportModal.tsx frontend/src/pages/Hotwords.tsx
git commit -m "feat(frontend): Hotwords 頁 + chip + 匯入匯出"
```

---

### Task 13: JobStatusBadge + JobList + Offline 頁

**Files:**
- Create: `frontend/src/components/JobStatusBadge.tsx`
- Create: `frontend/src/components/UploadDropzone.tsx`
- Modify: `frontend/src/components/JobList.tsx`
- Modify: `frontend/src/pages/Offline.tsx`

- [ ] **Step 1: 寫 JobStatusBadge**

建 `frontend/src/components/JobStatusBadge.tsx`：

```tsx
import type { JobStatus } from "../api/types";

const map: Record<JobStatus, { label: string; dot: string; text: string; bg: string }> = {
  pending:   { label: "待處理", dot: "bg-slate-400", text: "text-slate-700", bg: "bg-slate-100" },
  queued:    { label: "排隊中", dot: "bg-blue-400 animate-pulse", text: "text-blue-700", bg: "bg-blue-50" },
  running:   { label: "執行中", dot: "bg-blue-500 animate-pulse", text: "text-blue-700", bg: "bg-blue-50" },
  done:      { label: "完成", dot: "bg-green-500", text: "text-green-700", bg: "bg-green-50" },
  failed:    { label: "失敗", dot: "bg-red-500", text: "text-red-700", bg: "bg-red-50" },
  cancelled: { label: "已取消", dot: "bg-slate-400", text: "text-slate-600", bg: "bg-slate-100" },
};

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const m = map[status];
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs ${m.bg} ${m.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${m.dot}`} />
      {m.label}
    </span>
  );
}
```

- [ ] **Step 2: 寫 UploadDropzone**

建 `frontend/src/components/UploadDropzone.tsx`：

```tsx
import { useRef, useState } from "react";
import { UploadCloud, Loader2 } from "lucide-react";

interface Props {
  onFile: (f: File) => Promise<void>;
  accept?: string;
  disabled?: boolean;
}

export function UploadDropzone({ onFile, accept = "audio/*,video/mp4,video/webm,video/quicktime", disabled }: Props) {
  const ref = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);

  const handle = async (file: File) => {
    setBusy(true);
    try { await onFile(file); }
    finally { setBusy(false); }
  };

  return (
    <div
      onClick={() => !disabled && !busy && ref.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault(); setOver(false);
        const f = e.dataTransfer.files?.[0];
        if (f && !disabled) handle(f);
      }}
      className={`flex flex-col items-center justify-center gap-2 px-6 py-8 border-2 border-dashed rounded-lg transition-colors duration-200 cursor-pointer ${
        over ? "border-blue-500 bg-blue-50" : "border-slate-300 hover:border-blue-400 hover:bg-slate-50"
      } ${disabled || busy ? "opacity-60 cursor-not-allowed" : ""}`}
    >
      {busy
        ? <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
        : <UploadCloud className="w-8 h-8 text-slate-400" />
      }
      <p className="text-sm text-slate-700">
        {busy ? "上傳中..." : "拖入音檔，或點擊選擇"}
      </p>
      <p className="text-xs text-slate-500">支援 wav / mp3 / m4a / mp4 / webm；上限 500 MB / 4 小時</p>
      <input
        ref={ref}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) handle(f);
          e.target.value = "";
        }}
      />
    </div>
  );
}
```

- [ ] **Step 3: 寫 JobList**

替換 `frontend/src/components/JobList.tsx`：

```tsx
import { Link } from "react-router-dom";
import { Eye, Trash2 } from "lucide-react";
import { JobStatusBadge } from "./JobStatusBadge";
import type { JobOut } from "../api/types";

interface Props {
  jobs: JobOut[];
  projectId: number;
  onDelete?: (j: JobOut) => void;
}

function formatDuration(sec: number | null): string {
  if (sec == null) return "—";
  if (sec < 60) return `${sec.toFixed(1)} 秒`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m} 分 ${s} 秒`;
}

export function JobList({ jobs, projectId, onDelete }: Props) {
  if (jobs.length === 0) {
    return <div className="bg-white border border-slate-200 rounded-lg p-12 text-center text-slate-500">尚無 Job</div>;
  }
  return (
    <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
          <tr>
            <th className="px-4 py-2 text-left">狀態</th>
            <th className="px-4 py-2 text-left">時間</th>
            <th className="px-4 py-2 text-left">檔名</th>
            <th className="px-4 py-2 text-left">時長</th>
            <th className="px-4 py-2 text-left">進度</th>
            <th className="px-4 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.id} className="border-b border-slate-100 hover:bg-slate-50 transition-colors duration-200">
              <td className="px-4 py-2"><JobStatusBadge status={j.status} /></td>
              <td className="px-4 py-2 text-slate-600 font-mono text-xs">{new Date(j.created_at).toLocaleTimeString("zh-TW")}</td>
              <td className="px-4 py-2 text-slate-900 truncate max-w-[16rem]">{j.filename}</td>
              <td className="px-4 py-2 text-slate-600">{formatDuration(j.duration_sec)}</td>
              <td className="px-4 py-2 text-slate-600">
                {j.status === "running" || j.status === "queued"
                  ? <span>{j.chunks_done}/{j.chunks_total} ({Math.round(j.progress * 100)}%)</span>
                  : j.status === "failed"
                  ? <span className="text-red-600 font-mono text-xs" title={j.error ?? ""}>{j.error?.split(":")[0] ?? "—"}</span>
                  : "—"
                }
              </td>
              <td className="px-4 py-2 text-right">
                {j.status === "done" && (
                  <Link to={`/projects/${projectId}/edit/${j.id}?mode=view`} className="inline-flex items-center gap-1 text-blue-600 cursor-pointer hover:text-blue-800 transition-colors duration-200 mr-3">
                    <Eye className="w-4 h-4" /> 檢視
                  </Link>
                )}
                {onDelete && (
                  <button type="button" aria-label="刪除" onClick={() => onDelete(j)} className="text-slate-400 cursor-pointer hover:text-red-600 transition-colors duration-200">
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: 寫 Offline 頁（含 polling）**

替換 `frontend/src/pages/Offline.tsx`：

```tsx
import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { UploadDropzone } from "../components/UploadDropzone";
import { JobList } from "../components/JobList";
import { jobsApi } from "../api/jobs";
import { useProjectStore } from "../stores/projectStore";
import { useToast } from "../hooks/useToast";
import type { JobOut } from "../api/types";

const ACTIVE_STATUSES = new Set(["pending", "queued", "running"]);

export default function Offline() {
  const { id } = useParams();
  const projectId = Number(id);
  const project = useProjectStore((s) => s.projects.find((p) => p.id === projectId));
  const refetchProjects = useProjectStore((s) => s.refetch);

  const [jobs, setJobs] = useState<JobOut[]>([]);
  const [loading, setLoading] = useState(false);
  const toast = useToast();
  const pollRef = useRef<number | null>(null);

  useEffect(() => { if (!project) refetchProjects(); }, [project]);

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    try {
      const list = await jobsApi.list({ project_id: projectId, limit: 50 });
      setJobs(list);
    } finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { fetchJobs(); }, [fetchJobs]);

  // active job 時 polling 每 2 秒
  useEffect(() => {
    const hasActive = jobs.some((j) => ACTIVE_STATUSES.has(j.status));
    if (!hasActive) {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      return;
    }
    if (pollRef.current) return;
    pollRef.current = window.setInterval(fetchJobs, 2000);
    return () => {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    };
  }, [jobs, fetchJobs]);

  const onUpload = async (file: File) => {
    try {
      await jobsApi.upload(file, projectId);
      toast.success("Job 已建立，等待處理");
      await fetchJobs();
    } catch {
      // client.ts 已 toast
    }
  };

  const onDelete = async (j: JobOut) => {
    if (!confirm(`確定刪除 Job ${j.filename}？此動作會一併刪除原始音檔。`)) return;
    try {
      await jobsApi.remove(j.id);
      toast.success("已刪除");
      await fetchJobs();
    } catch { /* toast in client */ }
  };

  if (!project) return <div className="p-6">載入中...</div>;

  return (
    <div className="max-w-7xl mx-auto px-6 py-6">
      <header className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">離線轉錄</h1>
          <p className="text-sm text-slate-600 mt-1">{project.name}</p>
        </div>
        <button type="button" onClick={fetchJobs} disabled={loading} className="flex items-center gap-2 px-3 py-2 text-sm text-slate-700 border border-slate-300 rounded cursor-pointer hover:bg-slate-50 disabled:opacity-50 transition-colors duration-200">
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} /> 重新整理
        </button>
      </header>

      <UploadDropzone onFile={onUpload} />

      <h2 className="text-sm font-semibold text-slate-700 mt-6 mb-3">最近 Job（{jobs.length}）</h2>
      <JobList jobs={jobs} projectId={projectId} onDelete={onDelete} />
    </div>
  );
}
```

- [ ] **Step 5: 手動驗證**

```bash
cd frontend && npm run typecheck && npm run lint
```

啟動 dev：上傳 demo 音檔，看 JobList 即時更新（polling）、status 變 done、檢視按鈕跳 Editor route（頁面尚未實作但 route 應該已存在）。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/JobStatusBadge.tsx frontend/src/components/UploadDropzone.tsx frontend/src/components/JobList.tsx frontend/src/pages/Offline.tsx
git commit -m "feat(frontend): Offline 頁含 Upload + JobList + 自動 polling"
```

---

### Task 14: WaveformPlayer 共用元件

**Files:** Modify `frontend/src/components/WaveformPlayer.tsx`

- [ ] **Step 1: 確認 wavesurfer 版本**

```bash
cd frontend && npm ls wavesurfer.js 2>&1 | head -3
```

預期：`wavesurfer.js@^7.x`。

- [ ] **Step 2: 寫 WaveformPlayer**

替換 `frontend/src/components/WaveformPlayer.tsx`：

```tsx
import { useEffect, useImperativeHandle, useRef, useState, forwardRef } from "react";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions";
import { Play, Pause, Volume2, VolumeX } from "lucide-react";
import type { Segment } from "../api/types";

export interface WaveformHandle {
  play: () => void;
  pause: () => void;
  toggle: () => void;
  seek: (time: number) => void;
  jumpRelative: (deltaSec: number) => void;
  setMuted: (muted: boolean) => void;
  toggleMuted: () => void;
}

interface Props {
  audioUrl: string;
  segments: Segment[];
  activeIdx: number | null;
  editable?: boolean;
  onRegionClick?: (idx: number) => void;
  onRegionResize?: (idx: number, newStart: number, newEnd: number) => void;
}

export const WaveformPlayer = forwardRef<WaveformHandle, Props>(function WaveformPlayer(
  { audioUrl, segments, activeIdx, editable, onRegionClick, onRegionResize },
  ref
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WaveSurfer | null>(null);
  const regionsPluginRef = useRef<ReturnType<typeof RegionsPlugin.create> | null>(null);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);

  // create wavesurfer
  useEffect(() => {
    if (!containerRef.current) return;
    const regions = RegionsPlugin.create();
    const ws = WaveSurfer.create({
      container: containerRef.current,
      waveColor: "#94a3b8",
      progressColor: "#3b82f6",
      cursorColor: "#0f172a",
      height: 64,
      barWidth: 2,
      barGap: 1,
      plugins: [regions],
    });
    ws.load(audioUrl);
    ws.on("play", () => setPlaying(true));
    ws.on("pause", () => setPlaying(false));
    ws.on("timeupdate", (t) => setTime(t));
    ws.on("ready", () => setDuration(ws.getDuration()));
    wsRef.current = ws;
    regionsPluginRef.current = regions;
    return () => { ws.destroy(); };
  }, [audioUrl]);

  // sync segments → regions
  useEffect(() => {
    const regions = regionsPluginRef.current;
    if (!regions) return;
    regions.clearRegions();
    segments.forEach((s, i) => {
      const isActive = i === activeIdx;
      const r = regions.addRegion({
        start: s.start_time,
        end: s.end_time,
        color: isActive ? "rgba(249, 115, 22, 0.25)" : "rgba(59, 130, 246, 0.18)",
        drag: false,
        resize: !!editable,
      });
      r.on("click", (e) => {
        e?.stopPropagation?.();
        onRegionClick?.(i);
      });
      if (editable) {
        r.on("update-end", () => {
          onRegionResize?.(i, r.start, r.end);
        });
      }
    });
  }, [segments, activeIdx, editable, onRegionClick, onRegionResize]);

  // expose imperative API
  useImperativeHandle(ref, () => ({
    play: () => wsRef.current?.play(),
    pause: () => wsRef.current?.pause(),
    toggle: () => wsRef.current?.playPause(),
    seek: (t) => { const d = wsRef.current?.getDuration() ?? 0; if (d > 0) wsRef.current?.seekTo(t / d); },
    jumpRelative: (delta) => {
      const ws = wsRef.current; if (!ws) return;
      const d = ws.getDuration(); if (!d) return;
      const next = Math.max(0, Math.min(d, ws.getCurrentTime() + delta));
      ws.seekTo(next / d);
    },
    setMuted: (m) => { wsRef.current?.setMuted(m); setMuted(m); },
    toggleMuted: () => { const m = !muted; wsRef.current?.setMuted(m); setMuted(m); },
  }), [muted]);

  return (
    <div className="bg-slate-900 rounded-md p-3">
      <div ref={containerRef} className="rounded" />
      <div className="flex items-center gap-3 mt-2 text-slate-300 text-xs">
        <button type="button" aria-label={playing ? "暫停" : "播放"} onClick={() => wsRef.current?.playPause()} className="cursor-pointer text-white hover:text-blue-300 transition-colors duration-200">
          {playing ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5" />}
        </button>
        <span className="font-mono">{formatTime(time)} / {formatTime(duration)}</span>
        <button type="button" aria-label={muted ? "取消靜音" : "靜音"} onClick={() => { const m = !muted; wsRef.current?.setMuted(m); setMuted(m); }} className="ml-auto cursor-pointer text-slate-300 hover:text-white transition-colors duration-200">
          {muted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
        </button>
      </div>
    </div>
  );
});

function formatTime(s: number): string {
  if (!isFinite(s) || s < 0) s = 0;
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  const ms = Math.floor((s - Math.floor(s)) * 100);
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}.${String(ms).padStart(2, "0")}`;
}
```

- [ ] **Step 3: typecheck**

```bash
cd frontend && npm run typecheck
```

預期：0 errors。若 wavesurfer 7 plugin import path 不同，依套件版本調整 import line（常見替代：`import RegionsPlugin from 'wavesurfer.js/plugins/regions'`）。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/WaveformPlayer.tsx
git commit -m "feat(frontend): WaveformPlayer 用 wavesurfer 7 + Regions"
```

---

### Task 15: TranscriptViewer

**Files:** Modify `frontend/src/components/TranscriptViewer.tsx`

- [ ] **Step 1: 寫 TranscriptViewer**

替換 `frontend/src/components/TranscriptViewer.tsx`：

```tsx
import { useRef, useState } from "react";
import { Edit3 } from "lucide-react";
import { Link } from "react-router-dom";
import { WaveformPlayer, type WaveformHandle } from "./WaveformPlayer";
import type { JobOut } from "../api/types";

interface Props {
  job: JobOut;
  audioUrl: string;
  projectId: number;
}

export function TranscriptViewer({ job, audioUrl, projectId }: Props) {
  const segments = job.segments ?? [];
  const [active, setActive] = useState<number | null>(segments.length > 0 ? 0 : null);
  const waveRef = useRef<WaveformHandle>(null);

  const focusSegment = (i: number) => {
    setActive(i);
    waveRef.current?.seek(segments[i].start_time);
    waveRef.current?.play();
  };

  return (
    <div className="max-w-7xl mx-auto px-6 py-6">
      <header className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 truncate max-w-md">{job.filename}</h1>
          <p className="text-xs text-slate-500 mt-1">
            時長 {(job.duration_sec ?? 0).toFixed(1)} 秒 · {segments.length} 段 · hotwords {job.used_hotwords.length} 詞
          </p>
        </div>
        <Link to={`/projects/${projectId}/edit/${job.id}?mode=edit`} className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white text-sm rounded cursor-pointer hover:bg-blue-600 transition-colors duration-200">
          <Edit3 className="w-4 h-4" /> 編輯模式
        </Link>
      </header>

      <WaveformPlayer
        ref={waveRef}
        audioUrl={audioUrl}
        segments={segments}
        activeIdx={active}
        onRegionClick={focusSegment}
      />

      <div className="grid grid-cols-12 gap-4 mt-4">
        <div className="col-span-12 md:col-span-5 bg-white border border-slate-200 rounded-md overflow-hidden max-h-[60vh] overflow-y-auto">
          {segments.map((s, i) => (
            <button
              key={i}
              type="button"
              onClick={() => focusSegment(i)}
              className={`w-full text-left px-3 py-2 border-b border-slate-100 cursor-pointer transition-colors duration-200 ${
                i === active ? "bg-blue-50 border-l-2 border-l-blue-500 pl-2.5" : "hover:bg-slate-50"
              }`}
            >
              <div className="flex items-center gap-2 text-xs text-slate-500 font-mono mb-0.5">
                <span>{s.start_time.toFixed(2)}</span>
                <span>·</span>
                <span>Sp{s.speaker_id}</span>
              </div>
              <div className="text-sm text-slate-900 line-clamp-2">{s.text}</div>
            </button>
          ))}
        </div>
        <div className="col-span-12 md:col-span-7 bg-white border border-slate-200 rounded-md p-4">
          {active !== null && segments[active] ? (
            <>
              <div className="text-xs text-slate-500 mb-2">
                <span className="font-mono">{segments[active].start_time.toFixed(2)} → {segments[active].end_time.toFixed(2)}</span>
                {" · "}Speaker {segments[active].speaker_id}
              </div>
              <p className="text-base text-slate-900 leading-relaxed whitespace-pre-wrap">
                {segments[active].text}
              </p>
            </>
          ) : (
            <p className="text-sm text-slate-500">此 Job 沒有 segments</p>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: typecheck**

```bash
cd frontend && npm run typecheck
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/TranscriptViewer.tsx
git commit -m "feat(frontend): TranscriptViewer 含 waveform + 段落列表"
```

---

### Task 16: editorStore + useAutoSave + useKeyboardShortcuts

**Files:**
- Create: `frontend/src/stores/editorStore.ts`
- Create: `frontend/src/hooks/useAutoSave.ts`
- Create: `frontend/src/hooks/useKeyboardShortcuts.ts`
- Create: `frontend/src/lib/keyboard.ts`

- [ ] **Step 1: 寫 editorStore**

建 `frontend/src/stores/editorStore.ts`：

```typescript
import { create } from "zustand";
import type { Segment } from "../api/types";

interface EditorState {
  jobId: string | null;
  segments: Segment[];
  originalSnapshot: string;  // JSON.stringify(segments) 用於 dirty 判定
  activeIdx: number;
  saving: boolean;
  lastSavedAt: Date | null;

  init: (jobId: string, segments: Segment[]) => void;
  reset: () => void;
  setActive: (idx: number) => void;
  patchSegment: (idx: number, partial: Partial<Segment>) => void;
  resizeSegment: (idx: number, start: number, end: number) => void;

  isDirty: () => boolean;
  markSaved: (segments: Segment[]) => void;
  setSaving: (b: boolean) => void;
}

export const useEditorStore = create<EditorState>((set, get) => ({
  jobId: null,
  segments: [],
  originalSnapshot: "[]",
  activeIdx: 0,
  saving: false,
  lastSavedAt: null,

  init: (jobId, segments) => set({
    jobId,
    segments,
    originalSnapshot: JSON.stringify(segments),
    activeIdx: 0,
    saving: false,
    lastSavedAt: null,
  }),
  reset: () => set({
    jobId: null, segments: [], originalSnapshot: "[]",
    activeIdx: 0, saving: false, lastSavedAt: null,
  }),
  setActive: (idx) => set({ activeIdx: idx }),
  patchSegment: (idx, partial) => {
    const next = [...get().segments];
    next[idx] = { ...next[idx], ...partial };
    set({ segments: next });
  },
  resizeSegment: (idx, start, end) => {
    const grid = 0.05;
    const snap = (v: number) => Math.round(v / grid) * grid;
    const next = [...get().segments];
    next[idx] = { ...next[idx], start_time: snap(start), end_time: snap(end) };
    set({ segments: next });
  },
  isDirty: () => JSON.stringify(get().segments) !== get().originalSnapshot,
  markSaved: (segments) => set({
    originalSnapshot: JSON.stringify(segments),
    lastSavedAt: new Date(),
    saving: false,
  }),
  setSaving: (b) => set({ saving: b }),
}));
```

- [ ] **Step 2: 寫 useAutoSave**

建 `frontend/src/hooks/useAutoSave.ts`：

```typescript
import { useEffect, useRef } from "react";

export function useAutoSave(
  isDirty: boolean,
  save: () => Promise<void> | void,
  options: { delayMs?: number; enabled?: boolean } = {},
) {
  const { delayMs = 3000, enabled = true } = options;
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!enabled) return;
    if (!isDirty) return;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => { save(); }, delayMs);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [isDirty, delayMs, enabled]);

  // beforeunload 攔截
  useEffect(() => {
    if (!enabled) return;
    if (!isDirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty, enabled]);

  return {
    flush: save,
  };
}
```

- [ ] **Step 3: 寫 keyboard.ts shortcut helpers**

建 `frontend/src/lib/keyboard.ts`：

```typescript
export interface ShortcutDefinition {
  key: string;          // e.g. "Space", "ArrowLeft", "/"
  meta?: boolean;       // Cmd / Ctrl
  shift?: boolean;
  preventInInput?: boolean; // 預設 true：focus 在 input/textarea 時不觸發
  handler: (e: KeyboardEvent) => void;
}

export function matchShortcut(e: KeyboardEvent, s: ShortcutDefinition): boolean {
  const wantMeta = !!s.meta;
  const hasMeta = e.metaKey || e.ctrlKey;
  const wantShift = !!s.shift;
  if (wantMeta !== hasMeta) return false;
  if (wantShift !== e.shiftKey) return false;
  return e.key === s.key || (s.key === "Space" && e.code === "Space");
}

export function isInTextField(e: KeyboardEvent): boolean {
  const t = e.target as HTMLElement | null;
  if (!t) return false;
  const tag = t.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || (t as HTMLElement).isContentEditable;
}
```

- [ ] **Step 4: 寫 useKeyboardShortcuts**

建 `frontend/src/hooks/useKeyboardShortcuts.ts`：

```typescript
import { useEffect } from "react";
import { isInTextField, matchShortcut, type ShortcutDefinition } from "../lib/keyboard";

export function useKeyboardShortcuts(
  shortcuts: ShortcutDefinition[],
  enabled: boolean = true,
) {
  useEffect(() => {
    if (!enabled) return;
    const listener = (e: KeyboardEvent) => {
      for (const s of shortcuts) {
        const inText = isInTextField(e);
        if (s.preventInInput !== false && inText) continue;
        if (matchShortcut(e, s)) {
          e.preventDefault();
          s.handler(e);
          return;
        }
      }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [shortcuts, enabled]);
}
```

- [ ] **Step 5: typecheck + Commit**

```bash
cd frontend && npm run typecheck
git add frontend/src/stores/editorStore.ts frontend/src/hooks/useAutoSave.ts frontend/src/hooks/useKeyboardShortcuts.ts frontend/src/lib/keyboard.ts
git commit -m "feat(frontend): editorStore + useAutoSave + keyboard shortcut helpers"
```

---

### Task 17: SegmentListItem + SegmentFocusEditor + TranscriptEditor

**Files:**
- Create: `frontend/src/components/SegmentListItem.tsx`
- Create: `frontend/src/components/SegmentFocusEditor.tsx`
- Modify: `frontend/src/components/TranscriptEditor.tsx`

- [ ] **Step 1: 寫 SegmentListItem**

建 `frontend/src/components/SegmentListItem.tsx`：

```tsx
import type { Segment } from "../api/types";

interface Props {
  segment: Segment;
  active: boolean;
  dirty: boolean;
  onClick: () => void;
}

export function SegmentListItem({ segment, active, dirty, onClick }: Props) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full text-left px-3 py-2 border-b border-slate-100 cursor-pointer transition-colors duration-200 ${
        active ? "bg-blue-50 border-l-2 border-l-blue-500 pl-2.5" : "hover:bg-slate-50"
      }`}
    >
      <div className="flex items-center gap-2 text-xs text-slate-500 font-mono mb-0.5">
        <span>{segment.start_time.toFixed(2)}</span>
        <span>·</span>
        <span>Sp{segment.speaker_id}</span>
        {dirty && <span className="ml-auto w-1.5 h-1.5 rounded-full bg-amber-500" aria-label="未儲存" />}
      </div>
      <div className="text-sm text-slate-900 line-clamp-2">{segment.text}</div>
    </button>
  );
}
```

- [ ] **Step 2: 寫 SegmentFocusEditor**

建 `frontend/src/components/SegmentFocusEditor.tsx`：

```tsx
import { useEffect, useRef } from "react";
import type { Segment } from "../api/types";

interface Props {
  segment: Segment;
  index: number;
  total: number;
  speakerOptions: number[];
  onChange: (partial: Partial<Segment>) => void;
}

export function SegmentFocusEditor({ segment, index, total, speakerOptions, onChange }: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // autosize
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${ta.scrollHeight}px`;
  }, [segment.text]);

  return (
    <div className="bg-orange-50/60 border border-orange-200 rounded-md p-4">
      <div className="text-xs uppercase text-orange-700 font-semibold tracking-wider mb-3">
        SEGMENT {index + 1} / {total}
      </div>

      <div className="flex flex-wrap gap-2 mb-3 text-xs">
        <div className="inline-flex items-center gap-1 bg-white border border-slate-300 rounded px-2 py-1">
          <span className="text-slate-500">起</span>
          <input
            type="number"
            step="0.05"
            value={segment.start_time}
            onChange={(e) => onChange({ start_time: Number(e.target.value) })}
            className="w-20 font-mono text-slate-900 bg-transparent outline-none"
          />
        </div>
        <div className="inline-flex items-center gap-1 bg-white border border-slate-300 rounded px-2 py-1">
          <span className="text-slate-500">迄</span>
          <input
            type="number"
            step="0.05"
            value={segment.end_time}
            onChange={(e) => onChange({ end_time: Number(e.target.value) })}
            className="w-20 font-mono text-slate-900 bg-transparent outline-none"
          />
        </div>
        <div className="inline-flex items-center gap-1 bg-white border border-slate-300 rounded px-2 py-1">
          <span className="text-slate-500">Speaker</span>
          <select
            value={segment.speaker_id}
            onChange={(e) => onChange({ speaker_id: Number(e.target.value) })}
            className="bg-transparent outline-none cursor-pointer text-slate-900"
          >
            {speakerOptions.map((sp) => <option key={sp} value={sp}>{sp}</option>)}
          </select>
        </div>
      </div>

      <textarea
        ref={textareaRef}
        value={segment.text}
        onChange={(e) => onChange({ text: e.target.value })}
        className="w-full px-3 py-2 border-2 border-orange-300 rounded bg-white text-base text-slate-900 leading-relaxed resize-none outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-200 transition-colors duration-200 min-h-[120px]"
      />
    </div>
  );
}
```

- [ ] **Step 3: 寫 TranscriptEditor**

替換 `frontend/src/components/TranscriptEditor.tsx`：

```tsx
import { useEffect, useMemo, useRef } from "react";
import { Link } from "react-router-dom";
import { Eye, CheckCircle2, Loader2 } from "lucide-react";
import { WaveformPlayer, type WaveformHandle } from "./WaveformPlayer";
import { SegmentListItem } from "./SegmentListItem";
import { SegmentFocusEditor } from "./SegmentFocusEditor";
import { useEditorStore } from "../stores/editorStore";
import { useAutoSave } from "../hooks/useAutoSave";
import { useKeyboardShortcuts } from "../hooks/useKeyboardShortcuts";
import { useToast } from "../hooks/useToast";
import { jobsApi } from "../api/jobs";
import type { JobOut, Segment } from "../api/types";

interface Props {
  job: JobOut;
  audioUrl: string;
  projectId: number;
}

export function TranscriptEditor({ job, audioUrl, projectId }: Props) {
  const init = useEditorStore((s) => s.init);
  const reset = useEditorStore((s) => s.reset);
  const segments = useEditorStore((s) => s.segments);
  const activeIdx = useEditorStore((s) => s.activeIdx);
  const setActive = useEditorStore((s) => s.setActive);
  const patchSegment = useEditorStore((s) => s.patchSegment);
  const resizeSegment = useEditorStore((s) => s.resizeSegment);
  const isDirty = useEditorStore((s) => s.isDirty);
  const dirtySegments = useEditorStore((s) => s.segments); // 訂閱變動
  const dirty = isDirty();
  const saving = useEditorStore((s) => s.saving);
  const lastSavedAt = useEditorStore((s) => s.lastSavedAt);
  const setSaving = useEditorStore((s) => s.setSaving);
  const markSaved = useEditorStore((s) => s.markSaved);

  const waveRef = useRef<WaveformHandle>(null);
  const toast = useToast();

  // mount: init store
  useEffect(() => {
    init(job.id, job.segments ?? []);
    return () => reset();
  }, [job.id]);

  const speakerOptions = useMemo(() => {
    const set = new Set<number>([1, 2, 3, 4, 5]);
    segments.forEach((s) => set.add(s.speaker_id));
    return Array.from(set).sort((a, b) => a - b);
  }, [segments]);

  const save = async () => {
    if (saving) return;
    if (!dirty) return;
    setSaving(true);
    try {
      const updated = await jobsApi.patchSegments(job.id, segments);
      markSaved(updated.segments ?? segments);
    } catch {
      // client.ts 已 toast
      setSaving(false);
    }
  };

  useAutoSave(dirty, save, { delayMs: 3000 });

  const focusSegment = (i: number) => {
    if (dirty) save(); // 切段前 flush
    setActive(i);
    if (segments[i]) {
      waveRef.current?.seek(segments[i].start_time);
      waveRef.current?.play();
    }
  };

  useKeyboardShortcuts([
    { key: "Space", handler: () => waveRef.current?.toggle() },
    { key: "ArrowLeft", handler: () => waveRef.current?.jumpRelative(-5) },
    { key: "ArrowRight", handler: () => waveRef.current?.jumpRelative(5) },
    { key: "Tab", shift: false, handler: () => focusSegment(Math.min(segments.length - 1, activeIdx + 1)) },
    { key: "Tab", shift: true, handler: () => focusSegment(Math.max(0, activeIdx - 1)) },
    { key: "m", handler: () => waveRef.current?.toggleMuted() },
    { key: "M", handler: () => waveRef.current?.toggleMuted() },
    { key: "s", meta: true, preventInInput: false, handler: () => { save(); toast.info("手動儲存"); } },
    { key: "Escape", preventInInput: false, handler: () => (document.activeElement as HTMLElement | null)?.blur() },
  ], true);

  return (
    <div className="max-w-7xl mx-auto px-6 py-6">
      <header className="flex items-center justify-between mb-4 gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 truncate max-w-md">{job.filename}</h1>
          <p className="text-xs text-slate-500 mt-1 flex items-center gap-2">
            {saving
              ? <span className="inline-flex items-center gap-1 text-blue-600"><Loader2 className="w-3 h-3 animate-spin" /> 儲存中...</span>
              : lastSavedAt
              ? <span className="inline-flex items-center gap-1 text-green-600"><CheckCircle2 className="w-3 h-3" /> 已儲存於 {lastSavedAt.toLocaleTimeString("zh-TW")}</span>
              : dirty
              ? <span className="text-amber-600">有未儲存變更</span>
              : <span className="text-slate-500">無變更</span>
            }
          </p>
        </div>
        <Link to={`/projects/${projectId}/edit/${job.id}?mode=view`} className="flex items-center gap-2 px-3 py-2 text-sm text-slate-600 border border-slate-300 rounded cursor-pointer hover:bg-slate-50 transition-colors duration-200">
          <Eye className="w-4 h-4" /> 檢視模式
        </Link>
      </header>

      <WaveformPlayer
        ref={waveRef}
        audioUrl={audioUrl}
        segments={segments}
        activeIdx={activeIdx}
        editable
        onRegionClick={focusSegment}
        onRegionResize={(i, s, e) => resizeSegment(i, s, e)}
      />

      <div className="grid grid-cols-12 gap-4 mt-4">
        <div className="col-span-12 md:col-span-5 bg-white border border-slate-200 rounded-md overflow-hidden max-h-[60vh] overflow-y-auto">
          {segments.map((s, i) => (
            <SegmentListItem
              key={i}
              segment={s}
              active={i === activeIdx}
              dirty={JSON.stringify(s) !== JSON.stringify((job.segments ?? [])[i])}
              onClick={() => focusSegment(i)}
            />
          ))}
        </div>
        <div className="col-span-12 md:col-span-7">
          {segments[activeIdx] && (
            <SegmentFocusEditor
              segment={segments[activeIdx]}
              index={activeIdx}
              total={segments.length}
              speakerOptions={speakerOptions}
              onChange={(p) => patchSegment(activeIdx, p)}
            />
          )}
        </div>
      </div>

      <p className="text-xs text-slate-500 mt-4 px-2 flex flex-wrap gap-3">
        <span><kbd className="font-mono bg-slate-100 px-1 rounded">Space</kbd> 播停</span>
        <span><kbd className="font-mono bg-slate-100 px-1 rounded">←/→</kbd> ±5s</span>
        <span><kbd className="font-mono bg-slate-100 px-1 rounded">Tab</kbd> 下一段</span>
        <span><kbd className="font-mono bg-slate-100 px-1 rounded">Shift+Tab</kbd> 上一段</span>
        <span><kbd className="font-mono bg-slate-100 px-1 rounded">M</kbd> 靜音</span>
        <span><kbd className="font-mono bg-slate-100 px-1 rounded">Ctrl+S</kbd> 手動存</span>
      </p>
    </div>
  );
}
```

- [ ] **Step 4: 寫 Editor 頁（view / edit 切換）**

替換 `frontend/src/pages/Editor.tsx`：

```tsx
import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { TranscriptViewer } from "../components/TranscriptViewer";
import { TranscriptEditor } from "../components/TranscriptEditor";
import { jobsApi } from "../api/jobs";
import type { JobOut } from "../api/types";

export default function Editor() {
  const { id, itemId } = useParams();
  const [params] = useSearchParams();
  const mode = params.get("mode") === "edit" ? "edit" : "view";
  const [job, setJob] = useState<JobOut | null>(null);

  useEffect(() => {
    if (!itemId) return;
    jobsApi.get(itemId).then(setJob);
  }, [itemId]);

  if (!job) return <div className="p-6">載入中...</div>;
  if (job.status !== "done") return <div className="p-6 text-amber-700">Job 尚未完成（{job.status}），無法檢視 transcript</div>;

  const audioUrl = jobsApi.audioUrl(job.id);
  const projectId = Number(id);

  return mode === "edit"
    ? <TranscriptEditor job={job} audioUrl={audioUrl} projectId={projectId} />
    : <TranscriptViewer job={job} audioUrl={audioUrl} projectId={projectId} />;
}
```

- [ ] **Step 5: 手動驗證**

```bash
cd frontend && npm run typecheck && npm run lint
```

啟動 dev：上傳音檔 → 等 done → 進 Viewer 確認段落跳音檔 → 切 Editor 改文字 → 等 3 秒看 toolbar 變「✓ 已儲存於 ...」→ 鍵盤快捷鍵測試（Space / ←→ / Tab / M / Ctrl+S）。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/SegmentListItem.tsx frontend/src/components/SegmentFocusEditor.tsx frontend/src/components/TranscriptEditor.tsx frontend/src/pages/Editor.tsx
git commit -m "feat(frontend): TranscriptEditor 含 auto-save + keyboard shortcuts"
```

---

### Task 18: System 頁

**Files:** Modify `frontend/src/pages/System.tsx`

- [ ] **Step 1: 寫 System 頁**

替換 `frontend/src/pages/System.tsx`：

```tsx
import { useEffect, useState } from "react";
import { RefreshCw, Activity, Cpu, ListTree, Database } from "lucide-react";
import { systemApi } from "../api/system";
import type { HealthOut, ProfileOut, QueueInfo, VllmStatusOut } from "../api/types";

const POLL_MS = 10_000;

interface PanelState {
  health: HealthOut | null;
  vllm: VllmStatusOut | null;
  profile: ProfileOut | null;
  queue: QueueInfo | null;
  loading: boolean;
  lastError: string | null;
}

export default function System() {
  const [s, setS] = useState<PanelState>({
    health: null, vllm: null, profile: null, queue: null,
    loading: false, lastError: null,
  });

  const fetchAll = async () => {
    setS((p) => ({ ...p, loading: true }));
    try {
      const [h, v, p, q] = await Promise.all([
        systemApi.health().catch(() => null),
        systemApi.vllmStatus().catch(() => null),
        systemApi.profile().catch(() => null),
        systemApi.queue().catch(() => null),
      ]);
      setS({ health: h, vllm: v, profile: p, queue: q, loading: false, lastError: null });
    } catch (e) {
      setS((prev) => ({ ...prev, loading: false, lastError: String(e) }));
    }
  };

  useEffect(() => {
    fetchAll();
    const t = setInterval(fetchAll, POLL_MS);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="max-w-7xl mx-auto px-6 py-6">
      <header className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-semibold text-slate-900">服務狀態</h1>
        <button type="button" onClick={fetchAll} disabled={s.loading} className="flex items-center gap-2 px-3 py-2 text-sm text-slate-700 border border-slate-300 rounded cursor-pointer hover:bg-slate-50 disabled:opacity-50 transition-colors duration-200">
          <RefreshCw className={`w-4 h-4 ${s.loading ? "animate-spin" : ""}`} /> 重新整理
        </button>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Health */}
        <Panel title="健康檢查" icon={<Activity className="w-4 h-4" />}>
          {s.health ? (
            <ul className="space-y-2 text-sm">
              <Row label="DB" value={s.health.db_status} />
              <Row label="Redis" value={s.health.redis_status} />
              <Row label="vLLM" value={s.health.vllm_status} />
              <Row label="總體" value={s.health.ok ? "ok" : "不健康"} />
            </ul>
          ) : <Loading />}
        </Panel>

        {/* vLLM */}
        <Panel title="vLLM 狀態" icon={<Cpu className="w-4 h-4" />}>
          {s.vllm ? (
            <ul className="space-y-2 text-sm">
              <Row label="狀態" value={s.vllm.status} />
              <Row label="Model" value={s.vllm.model ?? "—"} />
              <Row label="Uptime" value={s.vllm.uptime_sec != null ? `${s.vllm.uptime_sec}s` : "—"} />
              {s.vllm.status === "mock" && <li className="text-xs text-amber-600 pt-1">Mock 模式（dev 用，無真實推論）</li>}
            </ul>
          ) : <Loading />}
        </Panel>

        {/* Profile */}
        <Panel title="部署 Profile" icon={<Database className="w-4 h-4" />}>
          {s.profile ? (
            <ul className="space-y-2 text-sm">
              <Row label="Profile" value={s.profile.profile} />
              <Row label="Inference GPU" value={s.profile.gpu_inference_devices} />
              <Row label="Training GPU" value={s.profile.gpu_training_devices} />
              <Row label="TP × DP" value={`${s.profile.tensor_parallel} × ${s.profile.data_parallel}`} />
              <Row label="最大並發" value={String(s.profile.max_concurrent_requests)} />
              <Row label="可同時訓練" value={s.profile.can_concurrent_train ? "是" : "否"} />
            </ul>
          ) : <Loading />}
        </Panel>

        {/* Queue */}
        <Panel title="任務佇列" icon={<ListTree className="w-4 h-4" />}>
          {s.queue ? (
            <ul className="space-y-2 text-sm">
              <Row label="Pending" value={String(s.queue.pending)} />
              <Row label="Running" value={String(s.queue.running)} />
              <Row label="Workers" value={String(s.queue.workers)} />
              <Row label="最舊任務年齡" value={`${s.queue.oldest_age_sec}s`} />
            </ul>
          ) : <Loading />}
        </Panel>
      </div>
      <p className="text-xs text-slate-500 mt-4">每 10 秒自動更新；數值是最後一次成功的回應</p>
    </div>
  );
}

function Panel({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="bg-white border border-slate-200 rounded-lg p-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-700 mb-3">{icon}{title}</div>
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <li className="flex justify-between gap-2 text-slate-700">
      <span className="text-slate-500">{label}</span>
      <span className="font-mono text-slate-900 truncate max-w-[60%] text-right">{value}</span>
    </li>
  );
}

function Loading() {
  return <p className="text-sm text-slate-400">載入中...</p>;
}
```

- [ ] **Step 2: 手動驗證**

```bash
cd frontend && npm run typecheck && npm run lint
```

啟動 dev，進 `/system`，看 4 個 panel 顯示資料、10 秒後自動更新。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/System.tsx
git commit -m "feat(frontend): System 頁含 4 panel + 自動 polling"
```

---

### Task 19: index.html 字體 + 收尾調整

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/src/index.css`（如有）

- [ ] **Step 1: index.html 加 Inter / JetBrains Mono**

修改 `frontend/index.html`，在 `<head>` 內加：

```html
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```

- [ ] **Step 2: tailwind.config.js 設字體**

修改 `frontend/tailwind.config.js`，theme.extend 內加：

```js
fontFamily: {
  sans: ['Inter', 'system-ui', 'sans-serif'],
  mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
},
```

- [ ] **Step 3: 確認 index.css 引 Tailwind**

確認 `frontend/src/index.css`（或 `main.css`）含：

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

html { font-family: Inter, system-ui, sans-serif; }
body { font-feature-settings: "ss01"; }
```

若檔案不存在，建立並在 `main.tsx` import。

- [ ] **Step 4: typecheck + dev 視覺驗證**

```bash
cd frontend && npm run typecheck && npm run lint && npm run build
```

啟動 dev，確認字體切換為 Inter + JetBrains Mono。

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html frontend/tailwind.config.js frontend/src/index.css
git commit -m "feat(frontend): 載 Inter / JetBrains Mono 字體"
```

---

### Task 20: e2e 手動驗收（依 SPEC.md §14.2 + 設計 spec §12）

**Files:** 無新增。執行手動測試清單。

- [ ] **Step 1: 啟動完整環境**

```bash
docker compose up -d redis backend worker
docker compose exec backend alembic upgrade head
cd frontend && npm run dev
```

- [ ] **Step 2: e2e 流程**

依下列順序，每完成一項打勾：

- [ ] 訪問 http://localhost:5173 看到 Projects 頁
- [ ] 建立 project「M3-test」（名稱 + 描述 + 2 個 hotwords）
- [ ] Sidebar 切到 Hotwords 頁
- [ ] 加 3 個詞、Enter 送出
- [ ] 點「匯出」下載 hotwords-M3-test-YYYYMMDD.txt，內容正確
- [ ] 點「匯入」用 mode=replace 上傳剛剛下載的檔，確認 toast 顯示新增/覆蓋數
- [ ] 點「儲存」按鈕，toast「已儲存」
- [ ] Sidebar 切到「離線轉錄」
- [ ] 拖入 vendor/VibeVoice/demo/asr_demo/demo3-hotwords.wav
- [ ] JobList 出現新 row、status=queued → running → done（mock 模式約 2 秒）
- [ ] 點「檢視」進 Viewer 頁
- [ ] 看到 waveform、segments 列表、active 段
- [ ] 點任一 segment row → 音檔跳到該段並播
- [ ] 切「編輯模式」
- [ ] 改某段文字、看 toolbar「有未儲存變更」→ 等 3 秒變「✓ 已儲存於 ...」
- [ ] 改 speaker dropdown → 同樣 3 秒後 auto-save
- [ ] 拖 region 邊界 → 時間更新並 auto-save
- [ ] Tab / Shift+Tab 切段、Space 播停、←/→ 跳秒、M 靜音皆正確
- [ ] Ctrl+S 顯示「手動儲存」toast
- [ ] 切 Sidebar 到「服務狀態」
- [ ] 看到 4 個 panel 全顯示資料（vllm=mock）
- [ ] 等 10 秒自動更新一次

- [ ] **Step 3: 任何項失敗則修並回對應 task；全綠後 push**

```bash
git push origin claude/crazy-rosalind-88a69d
```

---

## Self-Review 結果

`spec coverage`：spec §1.1 列的 6 頁皆有 task，共用元件、後端 3 endpoints、Hotwords 匯入/匯出、auto-save、快捷鍵、System polling 皆覆蓋。

`placeholder scan`：無 TBD/TODO/「實作 X 細節」。每個 step 含 code 或精確指令。

`type consistency`：`Segment` 介面在 backend `app/models.Segment` ↔ frontend `types.Segment` 對齊；`JobOut`、`ProjectOut` 同步；hotwords import/export 回傳結構（`{hotwords, added, replaced, skipped_duplicates}`）在 backend Task 4 與 frontend Task 12 一致。

無遺漏。

---

## Execution

Plan complete and saved to [docs/superpowers/plans/2026-05-09-m3-frontend-admin.md](.).

兩個執行選項：

**1. Subagent-Driven（推薦）** — 我為每個 task 派一個全新 subagent，task 間我審查、快迭代。可平行的 task（Task 7-8 / Task 11-12 / Task 13-14）一次派多個。

**2. Inline Execution** — 我在當前 session 內依 `superpowers:executing-plans` 流程批次執行，含 checkpoint review。

選哪個？依先前討論你傾向 subagent-driven。
