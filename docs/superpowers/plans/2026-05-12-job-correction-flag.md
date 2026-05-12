# Job 校正完成標記實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 `superpowers:subagent-driven-development` 逐 task 派 subagent 執行。

**Goal:** Job 加 `is_corrected` boolean 欄位、UI 加 checkbox、勾選後才能在 Dataset 「從歷史轉錄」匯入、編輯 segments 自動 unmark。

**Architecture:** SQLAlchemy 加欄位 + Alembic migration + 新 `PATCH /jobs/{id}` 端點 + 既有 `PATCH /jobs/{id}/segments` 加 side effect + GET /jobs 加 `is_corrected` query filter + Frontend JobList checkbox 即點即生效 + FromJobModal jobs list 加 filter。

**Spec Reference:** `docs/superpowers/specs/2026-05-12-job-correction-flag-design.md`

---

## Task 切分

| Task | 範圍 |
|---|---|
| 1 | Backend:model + migration + schema + 2 endpoints + GET /jobs filter + tests |
| 2 | Frontend:types + jobs api + JobList + Offline + FromJobModal |

---

## Task 1:Backend

**Files:**
- Modify: `backend/app/models.py`(Job 加 is_corrected)
- Modify: `backend/app/schemas.py`(JobOut + JobPatch)
- Create: `backend/migrations/versions/0003_job_is_corrected.py`
- Modify: `backend/app/routes/admin/jobs.py`(加 PATCH /jobs/{id} + 改 patch_segments side effect + GET /jobs filter)
- Create: `backend/tests/test_admin_jobs_patch.py`
- Modify: `backend/tests/test_admin_jobs_segments.py`(加 unmark assert)

### Steps

- [ ] **Step 1: `models.py` 加欄位**

`backend/app/models.py` `Job` class 內(放在 `metadata_extra: Mapped[dict | None] = mapped_column(JSON)` 之後、`created_at` 之前的合理位置):

```python
    is_corrected: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default=sa.text("0"),
    )
```

**注意**:`server_default` 用 `sa.text("0")` 或 `sa.false()`。SQLite 對 `sa.false()` 解析成 `0`,Postgres 解析成 `FALSE`,都對。**建議用 `sa.text("0")` 顯式避免歧義**。

Read `models.py` 確認 `sa` 是否已 import(看 `from sqlalchemy import ... Boolean` 或 `import sqlalchemy as sa`)。若無 `import sqlalchemy as sa`,可保持既有 import 風格、改用 `text("0")`(import text from sqlalchemy)。

- [ ] **Step 2: `schemas.py` 加 JobPatch + JobOut 欄位**

`backend/app/schemas.py`:

`JobOut`(約第 140-160 行)`finished_at` 之後加:
```python
    is_corrected: bool = False
```

(放在既有 `source_url` / `reference_subtitles` / `reference_subtitle_lang` 旁、合理位置。)

新增 schema(放在 `JobOut` 之後、`JobCreatedOut` 之前):
```python
class JobPatch(BaseModel):
    """Partial update for a Job. 目前只支援 is_corrected。"""
    is_corrected: bool | None = None
```

- [ ] **Step 3: 寫 Alembic migration**

`backend/migrations/versions/0003_job_is_corrected.py`:
```python
"""job_is_corrected

加 Job.is_corrected boolean 欄位,標「校正完成」、進 dataset 必要條件。
既有 rows 預設 0(False)、user 手動勾標。

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "is_corrected",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("jobs", "is_corrected")
```

- [ ] **Step 4: `routes/admin/jobs.py` 加 PATCH /jobs/{id} 端點 + 修 patch_segments + 改 list_jobs filter**

#### 4a:加 `JobPatch` import + 新端點

在既有 `from app.schemas import ...` 內加 `JobPatch`:
```python
from app.schemas import JobCreatedOut, JobOut, JobPatch, Segment, SegmentsPatchIn, YoutubeImportIn
```

新增端點(放在既有 `get_job` 端點之後、`delete_job` 之前的合理位置):
```python
@router.patch("/jobs/{job_id}", response_model=JobOut)
async def patch_job(
    job_id: str,
    payload: JobPatch,
    db: AsyncSession = Depends(get_db),
):
    """Partial update of Job. 目前只支援 is_corrected。"""
    job = await _get_job_or_404(db, job_id)
    if payload.is_corrected is not None:
        job.is_corrected = payload.is_corrected
    await db.flush()
    await db.refresh(job)
    return job
```

#### 4b:修既有 `patch_segments` 加 side effect

找 `patch_segments` 函式(既有),在 `job.segments = ...` 之後加一行:
```python
@router.patch("/jobs/{job_id}/segments", response_model=JobOut)
async def patch_segments(
    job_id: str,
    payload: SegmentsPatchIn,
    db: AsyncSession = Depends(get_db),
):
    """更新 Job.segments(用於 TranscriptEditor 自動儲存)。

    Side effect: 編輯 segments 後自動取消 is_corrected
   (user 改了內容應該重新確認校正完成才進 dataset)。
    """
    job = await _get_job_or_404(db, job_id)
    _validate_segments(payload.segments)
    job.segments = [s.model_dump() for s in payload.segments]
    job.is_corrected = False  # 新加 side effect
    await db.flush()
    await db.refresh(job)
    return job
```

#### 4c:GET /jobs 加 is_corrected query filter

找既有 `list_jobs` 函式,signature 加 query 參數:
```python
@router.get("/jobs", response_model=list[JobOut])
async def list_jobs(
    project_id: int | None = None,
    source: str | None = None,
    status: str | None = None,
    is_corrected: bool | None = None,  # 新加
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Job).order_by(Job.created_at.desc())
    if project_id is not None:
        stmt = stmt.where(Job.project_id == project_id)
    if source is not None:
        stmt = stmt.where(Job.source == source)
    if status is not None:
        stmt = stmt.where(Job.status == status)
    if is_corrected is not None:                          # 新加
        stmt = stmt.where(Job.is_corrected == is_corrected)
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    return result.scalars().all()
```

- [ ] **Step 5: 寫 `test_admin_jobs_patch.py`**

`backend/tests/test_admin_jobs_patch.py`:
```python
"""PATCH /api/admin/jobs/{id} — partial update Job(目前只 is_corrected)。"""
from __future__ import annotations

import pytest

from app import models  # noqa: F401
from app.db import db_session
from app.models import Job, JobSource, JobStatus, Project


async def _seed_project_and_job(status: JobStatus = JobStatus.DONE) -> str:
    """建一個 project + done job,回 job_id。"""
    async with db_session() as db:
        project = Project(name="p1")
        db.add(project)
        await db.flush()
        job = Job(
            id="job-1",
            project_id=project.id,
            source=JobSource.ADMIN_UPLOAD,
            filename="a.mp3",
            audio_path="/tmp/a.mp3",
            duration_sec=10.0,
            status=status,
        )
        db.add(job)
        await db.commit()
        return job.id


@pytest.mark.asyncio
async def test_patch_job_set_is_corrected_true(app_client):
    job_id = await _seed_project_and_job()
    r = await app_client.patch(
        f"/api/admin/jobs/{job_id}",
        json={"is_corrected": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["is_corrected"] is True


@pytest.mark.asyncio
async def test_patch_job_set_is_corrected_false(app_client):
    job_id = await _seed_project_and_job()
    # 先設 True
    await app_client.patch(f"/api/admin/jobs/{job_id}", json={"is_corrected": True})
    # 再設 False
    r = await app_client.patch(
        f"/api/admin/jobs/{job_id}",
        json={"is_corrected": False},
    )
    assert r.status_code == 200
    assert r.json()["is_corrected"] is False


@pytest.mark.asyncio
async def test_patch_job_missing_field_no_op(app_client):
    """body 空(無 is_corrected)→ 不改、回原 Job。"""
    job_id = await _seed_project_and_job()
    r = await app_client.patch(f"/api/admin/jobs/{job_id}", json={})
    assert r.status_code == 200
    assert r.json()["is_corrected"] is False


@pytest.mark.asyncio
async def test_patch_job_not_found(app_client):
    r = await app_client.patch(
        "/api/admin/jobs/nonexistent",
        json={"is_corrected": True},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "job_not_found"


@pytest.mark.asyncio
async def test_list_jobs_filter_is_corrected_true(app_client):
    """GET /jobs?is_corrected=true 只回勾過的 Jobs。"""
    job_id = await _seed_project_and_job()
    # 先建立 unmarked job(預設 False)
    r = await app_client.get("/api/admin/jobs?is_corrected=true")
    assert r.status_code == 200
    assert len(r.json()) == 0  # 還沒勾任何 job

    # 勾它
    await app_client.patch(f"/api/admin/jobs/{job_id}", json={"is_corrected": True})

    r = await app_client.get("/api/admin/jobs?is_corrected=true")
    assert r.status_code == 200
    jobs = r.json()
    assert len(jobs) == 1
    assert jobs[0]["id"] == job_id
    assert jobs[0]["is_corrected"] is True


@pytest.mark.asyncio
async def test_list_jobs_filter_is_corrected_false(app_client):
    job_id = await _seed_project_and_job()
    r = await app_client.get("/api/admin/jobs?is_corrected=false")
    assert r.status_code == 200
    jobs = r.json()
    assert len(jobs) == 1
    assert jobs[0]["id"] == job_id
    assert jobs[0]["is_corrected"] is False
```

- [ ] **Step 6: 改 `test_admin_jobs_segments.py` 加 unmark side effect 測試**

在既有 test_admin_jobs_segments.py **檔末**加新 test(不動既有 test):

```python
@pytest.mark.asyncio
async def test_patch_segments_resets_is_corrected(app_client):
    """PATCH segments 後自動 unmark is_corrected(防 user 改完忘記重勾)。"""
    project_id, job_id = await _seed_project_and_job(segments=[])
    # 先勾 is_corrected=True
    r = await app_client.patch(f"/api/admin/jobs/{job_id}", json={"is_corrected": True})
    assert r.status_code == 200
    assert r.json()["is_corrected"] is True

    # 改 segments
    segs = [{"start_time": 0.0, "end_time": 1.0, "speaker_id": 1, "text": "hello"}]
    r = await app_client.patch(
        f"/api/admin/jobs/{job_id}/segments",
        json={"segments": segs},
    )
    assert r.status_code == 200
    # 自動 unmark
    assert r.json()["is_corrected"] is False
```

> **注意**:`_seed_project_and_job` 是 test 檔內既有 helper,implementer 要先 Read test_admin_jobs_segments.py 確認 helper 簽名再寫 test。

- [ ] **Step 7: Commit**

```
git -C /d/vibevoice_asr add backend/app/models.py backend/app/schemas.py backend/migrations/versions/0003_job_is_corrected.py backend/app/routes/admin/jobs.py backend/tests/test_admin_jobs_patch.py backend/tests/test_admin_jobs_segments.py
```

```
git -C /d/vibevoice_asr commit -m "feat(jobs): is_corrected flag + PATCH endpoint + segments 自動 unmark"
```

```
git -C /d/vibevoice_asr push
```

---

## Task 2:Frontend

**Files:**
- Modify: `frontend/src/api/types.ts`(JobOut 加 is_corrected)
- Modify: `frontend/src/api/jobs.ts`(加 setCorrected + list signature 加 is_corrected 參數)
- Modify: `frontend/src/components/JobList.tsx`(加校正 checkbox 欄)
- Modify: `frontend/src/pages/Offline.tsx`(加 onMarkCorrected handler)
- Modify: `frontend/src/components/FromJobModal.tsx`(jobs list filter is_corrected=true)

### Steps

- [ ] **Step 1: 改 `types.ts` JobOut**

`frontend/src/api/types.ts` `JobOut` interface(`reference_subtitle_lang` 之後)加:
```typescript
  is_corrected: boolean;
```

- [ ] **Step 2: 改 `api/jobs.ts`**

整檔(完整新版):
```typescript
import { api } from "./client";
import type { JobCreatedOut, JobOut, Segment } from "./types";

const ADMIN = "/api/admin";

export const jobsApi = {
  list: (opts: {
    project_id?: number;
    status?: string;
    is_corrected?: boolean;
    limit?: number;
    offset?: number;
  } = {}) =>
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

  transcribeFromYoutube: (url: string, projectId: number) =>
    api.post<JobCreatedOut>(`${ADMIN}/transcribe/from_youtube`, {
      url,
      project_id: projectId,
    }),

  patchSegments: (id: string, segments: Segment[]) =>
    api.patch<JobOut>(`${ADMIN}/jobs/${id}/segments`, { segments }),

  setCorrected: (id: string, value: boolean) =>
    api.patch<JobOut>(`${ADMIN}/jobs/${id}`, { is_corrected: value }),
};
```

- [ ] **Step 3: 改 `JobList.tsx`**

完整新版:
```tsx
import { Link } from "react-router-dom";
import { Eye, Trash2 } from "lucide-react";
import { JobStatusBadge } from "./JobStatusBadge";
import type { JobOut } from "../api/types";

interface Props {
  jobs: JobOut[];
  projectId: number;
  onDelete?: (j: JobOut) => void;
  onMarkCorrected?: (j: JobOut, value: boolean) => void;
}

function formatDuration(sec: number | null): string {
  if (sec == null) return "—";
  if (sec < 60) return `${sec.toFixed(1)} 秒`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m} 分 ${s} 秒`;
}

export function JobList({ jobs, projectId, onDelete, onMarkCorrected }: Props) {
  if (jobs.length === 0) {
    return <div className="bg-white border border-slate-200 rounded-lg p-12 text-center text-slate-500">尚無 Job</div>;
  }
  return (
    <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
          <tr>
            <th className="px-4 py-2 text-left">狀態</th>
            <th className="px-4 py-2 text-left">校正</th>
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
              <td className="px-4 py-2">
                <input
                  type="checkbox"
                  checked={j.is_corrected}
                  disabled={j.status !== "done" || !onMarkCorrected}
                  title={
                    j.status !== "done"
                      ? "需先完成轉錄"
                      : j.is_corrected
                      ? "取消標記校正完成"
                      : "勾選後可在資料集「從歷史轉錄」匯入"
                  }
                  onChange={(e) => onMarkCorrected?.(j, e.target.checked)}
                  className="cursor-pointer disabled:cursor-not-allowed disabled:opacity-40"
                />
              </td>
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

- [ ] **Step 4: 改 `Offline.tsx` 加 handler + 傳 prop**

在既有 `onDelete` handler 之後(約第 70 行)加:
```typescript
const onMarkCorrected = async (j: JobOut, value: boolean) => {
  try {
    await jobsApi.setCorrected(j.id, value);
    // 樂觀更新 — UI 立即反映,不等下次 fetchJobs
    setJobs((prev) =>
      prev.map((x) => (x.id === j.id ? { ...x, is_corrected: value } : x)),
    );
  } catch {
    // client.ts 已 toast
  }
};
```

`<JobList>` 呼叫(約第 96 行)加 prop:
```tsx
<JobList
  jobs={jobs}
  projectId={projectId}
  onDelete={onDelete}
  onMarkCorrected={onMarkCorrected}
/>
```

- [ ] **Step 5: 改 `FromJobModal.tsx` filter is_corrected=true**

`frontend/src/components/FromJobModal.tsx` `useEffect`(第 23-34 行)的 `jobsApi.list` 加 `is_corrected: true`:

```typescript
useEffect(() => {
  if (!open) return;
  setError(null);
  setSelectedId(null);
  setNotes("");
  setLoading(true);
  jobsApi
    .list({ project_id: projectId, status: "done", is_corrected: true })
    .then(setJobs)
    .catch(() => setError("載入失敗"))
    .finally(() => setLoading(false));
}, [open, projectId]);
```

修「尚無已完成的 Job」訊息(第 65 行附近)讓 user 知道為什麼:
```tsx
{loading ? (
  <div className="text-sm text-slate-500">載入中...</div>
) : jobs.length === 0 ? (
  <div className="text-sm text-slate-500">
    尚無已校正完成的 Job。請先在「離線轉錄」頁勾選「校正」欄位。
  </div>
) : (
```

- [ ] **Step 6: typecheck + lint**

```
npm --prefix /d/vibevoice_asr/frontend run typecheck
```

```
npm --prefix /d/vibevoice_asr/frontend run lint
```

兩者都要 PASS。

- [ ] **Step 7: Commit**

```
git -C /d/vibevoice_asr add frontend/src/api/types.ts frontend/src/api/jobs.ts frontend/src/components/JobList.tsx frontend/src/pages/Offline.tsx frontend/src/components/FromJobModal.tsx
```

```
git -C /d/vibevoice_asr commit -m "feat(jobs): JobList 加校正 checkbox + FromJobModal filter is_corrected"
```

```
git -C /d/vibevoice_asr push
```

---

## 完成後驗證(user 在 Linux 端)

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

### 實機驗收

1. 進 admin UI → 任一 project → 離線轉錄 → JobList 應該多一個「校正」欄
2. 對 status=done 的 Job:checkbox enabled、可勾 / 取消勾
3. 對其他 status:checkbox disabled、hover 顯示 tooltip「需先完成轉錄」
4. 勾一個 Job → 進 Editor 改 segments 存檔 → 回 JobList:該 Job checkbox 自動取消(unmark)
5. 進 Dataset 頁 → 點「從歷史轉錄」→ 只列勾過的 Job;沒勾的不列;空清單顯示「尚無已校正完成的 Job」訊息

---

## Risks

| 風險 | 緩解 |
|---|---|
| Alembic migration 對 SQLite + NOT NULL 加欄位失敗 | 用 `server_default=sa.text("0")` 給既有 row default |
| 樂觀更新 race condition(快速連點) | 既有 jobs[] state 用 functional setter `prev.map`、safe |
| 用 status="done" + is_corrected=true filter 後沒任何 Job 顯示 | 既有 Job 預設 False、user 需手動勾。FromJobModal 提示文字已說明 |

---

## Plan Self-Review

- [x] Files paths 精確
- [x] 每個 step 完整 code
- [x] Task 1 不依賴 Task 2、可獨立 ship
- [x] 命名一致(`is_corrected` snake_case Python / `is_corrected` 同 TS、`setCorrected` 動詞 + camelCase frontend)
- [x] 完成條件對應 spec §9
