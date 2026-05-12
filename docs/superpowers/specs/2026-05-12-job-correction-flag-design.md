# Job 校正完成標記設計

> **For agentic workers:** REQUIRED SUB-SKILL: 後續用 `superpowers:writing-plans` 寫實作計畫,再用 `superpowers:subagent-driven-development` 派 subagent 執行。

**目標:** JobList 加「校正完成」勾選欄位。勾選的 Job 才能在 Dataset 頁面的「從歷史轉錄」清單看到、進 dataset。編輯 segments 後自動取消勾選(防 user 改完忘記重勾)。

**架構:** `Job` 加 `is_corrected` boolean 欄位 + Alembic migration。新增 `PATCH /api/admin/jobs/{id}` 端點接 partial update。既有 `PATCH /jobs/{id}/segments` 端點加 side effect:patch 後自動 `is_corrected=False`。Dataset 「從歷史轉錄」端點 filter `is_corrected=True`。Frontend JobList 加 checkbox 欄、status=DONE enabled / 其他 disabled。

**Tech Stack:** SQLAlchemy(已有)+ Alembic(已有)+ React checkbox(已有)。無新依賴。

---

## 1. 動機

校正工作台目的是「準備 LoRA fine-tune dataset」。校正員可能要對多個 Job 進行不同程度的修正,但目前流程:

- Job 完成後 status=DONE
- 「從歷史轉錄」(`/datasets/from_job/{job_id}`)端點只看 status=DONE
- 校正員校正到一半的 Job 也會出現在 dataset 選單、容易誤匯入未完成校正的內容

加 `is_corrected` flag 讓校正員顯式標「這個 Job 校正完成、可進 dataset」。

---

## 2. 範圍

### 2.1 In scope

- `Job` 加 `is_corrected: bool`(預設 `False`)+ Alembic migration
- `JobOut` schema 加欄位
- 新增 `PATCH /api/admin/jobs/{id}` 端點(接 `JobPatch { is_corrected: bool | None }`)
- 既有 `PATCH /jobs/{id}/segments` 端點加 side effect:patch 後 `is_corrected=False`
- 既有 dataset 「從歷史轉錄」(`/datasets/jobs_eligible` 或對應端點)filter `is_corrected=True`
- `JobList.tsx` 加「校正」欄、checkbox
- `frontend/src/api/types.ts` `JobOut` 加 `is_corrected: boolean`
- `frontend/src/api/jobs.ts` 加 `setCorrected(id, value)` method

### 2.2 Out of scope

- 既有 DONE Jobs 一鍵標 corrected(全部預設 `False`、user 在 UI 手動勾)
- correction audit log(誰勾的、何時勾的)
- 多人協作 lock(防止兩人同時改同 Job)
- v1 API 端對外 expose `is_corrected`(對 QC 系統無意義,只在 admin schema 加)
- 已勾選 Job 進 dataset 後是否 unlink editing(目前接受 user 修 dataset label 後跟 source Job segments 脫鉤、既有行為不變)

---

## 3. 決定(已 user 確認)

| # | 議題 | 決定 |
|---|---|---|
| 1 | 非 DONE Jobs 的 checkbox 顯示 | 顯示但 disabled + tooltip「需先完成轉錄」 |
| 2 | 編輯 segments 後是否自動 unmark | **自動** unmark(防忘) |
| 3 | 既有 Jobs migration 處理 | 預設 `False`、無自動遷移、user 手動標 |

---

## 4. Data Model

### 4.1 `backend/app/models.py`

`Job` class 加(放在 `metadata_extra` 後、`created_at` 前的合理位置):

```python
    is_corrected: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default=sa.false(),
    )
```

注意:`server_default` 用 `sa.false()`(SQLAlchemy 跨 dialect helper)、不用 Python `False`(後者只在 ORM 層、不影響 Alembic ADD COLUMN)。

### 4.2 Alembic migration `0003_job_is_corrected.py`

```python
"""job is_corrected

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
            "is_corrected", sa.Boolean(),
            server_default=sa.false(), nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("jobs", "is_corrected")
```

`server_default=sa.false()` 讓 SQLite ADD COLUMN 對既有 rows 自動填 0。否則 NOT NULL 沒 default 會失敗。

### 4.3 Schema `backend/app/schemas.py`

`JobOut` 加:
```python
    is_corrected: bool = False
```

新增 `JobPatch`(放在 `JobOut` 旁):
```python
class JobPatch(BaseModel):
    is_corrected: bool | None = None
```

### 4.4 Frontend types

`frontend/src/api/types.ts` `JobOut` 加:
```typescript
  is_corrected: boolean;
```

---

## 5. API

### 5.1 新端點 `PATCH /api/admin/jobs/{id}`

```
PATCH /api/admin/jobs/{id}
Content-Type: application/json
Body: { "is_corrected": true | false }
Response: 200 JobOut

Errors:
  404 JOB_NOT_FOUND
```

實作位置 `backend/app/routes/admin/jobs.py`:
```python
@router.patch("/jobs/{job_id}", response_model=JobOut)
async def patch_job(
    job_id: str,
    payload: JobPatch,
    db: AsyncSession = Depends(get_db),
):
    """Partial update of Job. 目前僅支援 is_corrected 欄位。"""
    job = await _get_job_or_404(db, job_id)
    if payload.is_corrected is not None:
        job.is_corrected = payload.is_corrected
    await db.flush()
    await db.refresh(job)
    return job
```

### 5.2 既有 `PATCH /jobs/{id}/segments` 加 side effect

修 `patch_segments` 函式(`backend/app/routes/admin/jobs.py`):

```python
@router.patch("/jobs/{job_id}/segments", response_model=JobOut)
async def patch_segments(
    job_id: str,
    payload: SegmentsPatchIn,
    db: AsyncSession = Depends(get_db),
):
    job = await _get_job_or_404(db, job_id)
    _validate_segments(payload.segments)
    job.segments = [s.model_dump() for s in payload.segments]
    # Side effect: 編輯 segments 後自動取消校正完成標記
    # (理由:user 改了內容應該要重新確認校正完成才進 dataset)
    job.is_corrected = False
    await db.flush()
    await db.refresh(job)
    return job
```

### 5.3 Dataset 「從歷史轉錄」filter

需要 grep 找既有「從歷史轉錄」相關端點(可能在 `backend/app/routes/admin/datasets.py`)。

可能的端點:
- `GET /api/admin/datasets/jobs_eligible?project_id=X` — 列可進 dataset 的 Jobs(若存在)
- 或 frontend 直接打 `GET /jobs?project_id=X&status=done` + 自己 filter

**統一處理**:
- 若有專屬 `/datasets/jobs_eligible` 端點:加 query filter `is_corrected=True`
- 若沒有、frontend 直接打 `GET /jobs`:在 `GET /jobs` 加 `is_corrected: bool | None = None` query filter,frontend 「從歷史轉錄」打 `?status=done&is_corrected=true`

實作 subagent 要先 grep 確認既有 pattern。

---

## 6. Frontend UI

### 6.1 `JobList.tsx`

新增「校正」欄,位置在「狀態」跟「時間」之間或末尾(看視覺平衡)。

```tsx
<th className="px-4 py-2 text-left">校正</th>
...
<td className="px-4 py-2">
  <input
    type="checkbox"
    checked={j.is_corrected}
    disabled={j.status !== "done"}
    title={j.status !== "done" ? "需先完成轉錄" : "勾選後可在資料集「從歷史轉錄」匯入"}
    onChange={(e) => onMarkCorrected?.(j, e.target.checked)}
    className="cursor-pointer disabled:cursor-not-allowed disabled:opacity-40"
  />
</td>
```

JobList Props 加:
```typescript
onMarkCorrected?: (j: JobOut, value: boolean) => void;
```

### 6.2 `Offline.tsx`(JobList 的 caller)

加 handler:
```typescript
const onMarkCorrected = async (j: JobOut, value: boolean) => {
  try {
    await jobsApi.setCorrected(j.id, value);
    // 樂觀更新 — 不等下次 fetchJobs,UI 立即反映
    setJobs((prev) =>
      prev.map((x) => (x.id === j.id ? { ...x, is_corrected: value } : x))
    );
  } catch {
    // client.ts 已 toast
  }
};
```

傳給 JobList:`<JobList jobs={jobs} projectId={projectId} onDelete={onDelete} onMarkCorrected={onMarkCorrected} />`

### 6.3 `frontend/src/api/jobs.ts` 加 method

```typescript
setCorrected: (id: string, value: boolean) =>
  api.patch<JobOut>(`${ADMIN}/jobs/${id}`, { is_corrected: value }),
```

### 6.4 Dataset 「從歷史轉錄」modal

找既有元件(可能 `FromJobModal.tsx`),改 filter:
- 若 frontend 自己 filter:Jobs list 加 `.filter((j) => j.is_corrected)`
- 若打 backend filter API:改 API call 加 `is_corrected=true` query

---

## 7. 測試策略

### 7.1 Backend tests

| 檔 | 範圍 |
|---|---|
| `test_admin_jobs_patch.py`(新建)| `PATCH /jobs/{id}` 改 `is_corrected=True/False`、404 不存在 Job |
| `test_admin_jobs_segments.py`(改)| 既有 `test_patch_segments_*` 加 assert:patch 後 `is_corrected=False`(side effect 驗證);加 `test_patch_segments_resets_corrected`(先設 True、patch 後驗 False)|
| `test_routes_datasets.py`(改)| 「從歷史轉錄」端點 filter:勾過的 Job 出現、沒勾的不出現 |
| `test_models_job.py` 或新檔 | `Job.is_corrected` 預設 False、欄位存在 |

### 7.2 Frontend

- typecheck + lint 0 errors
- 無 unit test(無 vitest 框架)
- 實機測:勾 / 取消勾 / 編輯 segments 後 unmark / dataset 從歷史只列勾過的

---

## 8. 邊界 case

| 情境 | 處理 |
|---|---|
| user 在 status=running 時勾選(若 UI 有 bug 漏 disabled)| backend 不檢查 status、接受;UI 應該 disabled 擋 |
| 同時間多 tab user 勾兩次 | 後 patch 覆蓋前 patch、無 lock、可接受 |
| editor 自動 save 觸發 patch_segments → unmark | 預期行為,user 看到 checkbox 自動取消勾、可重新勾 |
| dataset 已從 Job 建立後、Job 取消勾 | dataset 不受影響(已建)、只影響後續「從歷史轉錄」是否再列 |
| migration server_default=False 對 SQLite | sa.false() 跨 dialect 安全、不破現有 row |

---

## 9. 完成條件

- [ ] `Job` model 加 `is_corrected` 欄位
- [ ] Alembic `0003_job_is_corrected.py` migration 寫好、可 upgrade
- [ ] `JobOut` schema + frontend types 加欄位
- [ ] `PATCH /jobs/{id}` 端點實作 + test
- [ ] `PATCH /jobs/{id}/segments` 自動 unmark + test
- [ ] Dataset 「從歷史轉錄」filter `is_corrected=True` + test
- [ ] `JobList.tsx` 加 checkbox 欄
- [ ] `frontend/src/api/jobs.ts` 加 `setCorrected`
- [ ] `Offline.tsx` 串接 onMarkCorrected handler
- [ ] backend pytest 全綠
- [ ] frontend typecheck + lint 0 errors

---

## 10. 不變條件(Non-Goals)

- v1 API JobStatusOut / JobResultOut 不加 `is_corrected`(對外 QC 系統無意義)
- Job model 既有欄位 / 索引不動
- 既有 transcribe_job / job_runner 邏輯不動
- 既有 webhook payload 不加 `is_corrected`
