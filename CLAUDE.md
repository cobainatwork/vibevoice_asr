# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 一、 專案速覽

**VibeVoice-ASR 內部部署平台**：以 `microsoft/VibeVoice-ASR-7B` 為核心的內部 ASR 服務。對外 v1 API（`/api/v1/*`）給 QC 系統整合；對內 admin（`/api/admin/*` + frontend）是給內部標註人員 / 工程師**準備 LoRA 微調訓練資料**的工作台，**不是**質檢前端。

**校正工作台（TranscriptViewer / Editor）的核心目的**：把 ASR 輸出當作 LoRA fine-tuning 訓練資料的起點，編輯後存為 dataset。時間軸精準度（拖 region 邊界 / 數字 input）直接影響訓練資料品質，不可為了 UX 簡潔移除這類精細互動。

**單一真實來源（Single Source of Truth）**：[SPEC.md](SPEC.md)（v1.1，112 KB，繁體中文）。所有資料模型、API 介面、訊息協定、目錄結構皆以 SPEC.md 為準。本檔僅補充工作流與不易從原始碼直接看出的慣例。

**目前狀態（2026-05-10）**：M1-M3 已完成。Backend admin endpoints + frontend 6 頁全套可用、含 hotwords 匯入 / 匯出與 TranscriptEditor auto-save。M3.5 / M4 / M6 屬下階段（Datasets / Training / v1 API）。`git log` 看最新進度。

## 二、 常用指令

跨平台統一入口：Linux / macOS 用 `make`、Windows 用 `.\make.ps1`、Windows cmd 用 `make`（透過 `make.bat` 轉發）。功能對齊。

### 服務生命週期

| 動作 | Linux / macOS | Windows |
|---|---|---|
| 一次性安裝 | `make setup` | `.\make.ps1 setup` |
| 啟動全部服務（redis、backend、worker、frontend） | `make up` | `.\make.ps1 up` |
| 停止 | `make down` | `.\make.ps1 down` |
| 重啟 backend | `make restart-backend` | `.\make.ps1 restart-backend` |
| 進 backend container shell | `make shell-backend` | `.\make.ps1 shell-backend` |
| Tail backend log | `make logs-backend` | `.\make.ps1 logs-backend` |
| Tail vLLM log | `make logs-vllm` | `.\make.ps1 logs-vllm` |
| 全環境部署驗證 | `bash scripts/verify_deployment.sh` | `.\make.ps1 verify` |

### 開發 / 測試

| 動作 | 指令 |
|---|---|
| 跑全部後端測試 | `make test-backend`（內部即 `docker compose exec backend pytest -v`） |
| 跑單一測試檔 | `docker compose exec backend pytest -v tests/test_parser.py` |
| 跑單一測試函式 | `docker compose exec backend pytest -v -k test_function_name` |
| 後端 lint | `docker compose exec backend ruff check app/` |
| 後端 type-check | `docker compose exec backend mypy app/` |
| 前端 hot-reload（host 端） | `make frontend-dev`（即 `cd frontend && npm run dev`） |
| 前端 lint | `cd frontend && npm run lint` |
| 前端 type-check | `cd frontend && npm run typecheck` |
| 前端 production build | `cd frontend && npm run build` |

### 資料庫 migration（Alembic）

| 動作 | 指令 |
|---|---|
| 套用最新 migration | `make db-migrate` |
| 產生新 migration | `make db-revision M='訊息文字'` |
| 在容器內手動下指令 | `docker compose exec backend alembic <subcommand>` |

### vLLM container

`vllm` 服務在 `docker-compose.yml` 中設為 `profiles: ["manual"]`，由 backend 控制啟停（依 `DeploymentStrategy`）。手動啟動：`docker compose --profile manual up -d vllm`。

## 三、 高層架構

### 服務拓撲

```
QC 系統 ─► /api/v1/*    ─┐                ┌─► vLLM container（推論，按需啟停）
                         ├─► Backend      │
Browser ─► /api/admin/* ─┘   (FastAPI)    ├─► Training container（一次性，跑完即退）
                                ├─► Redis（Arq queue + idempotency cache + DLQ）
                                ├─► Worker（Arq，水平擴展，預設 1 replica）
                                └─► SQLite（預設）/ Postgres（生產可選）
```

詳見 SPEC.md §3 系統架構圖。

### 兩個 API 介面（重要分界）

| 介面 | Path 前綴 | 用途 | 認證 | Schema 穩定度 |
|---|---|---|---|---|
| Admin | `/api/admin/*` | 內部 UI | 無（內網部署，可在 nginx 加 IP 白名單） | 可調整 |
| v1 | `/api/v1/*` | QC 系統整合 | API Key（HTTP Bearer / WS Subprotocol `bearer.<key>`） | 凍結，向後相容 |

修改 v1 介面前必須先讀 SPEC.md §17 全章。`/api/v1/openapi.json` 為對外 SDK 生成入口。

### 關鍵抽象層（後端）

| 模組 | 職責 | 接手者必看 |
|---|---|---|
| [`app/services/deployment.py`](backend/app/services/deployment.py) | `DeploymentStrategy` 介面，依 `DEPLOYMENT_PROFILE` env（`single` / `single-large` / `dual-split` / `dual-tp` / `multi`）切換 GPU 分配、vLLM 啟動參數、是否允許訓練+推論並行 | 新增 GPU 配置選項時擴充此處 |
| [`app/services/vllm_client.py`](backend/app/services/vllm_client.py) | vLLM HTTP client，支援 round-robin 多 instance、自動 repetition recovery（依 `RETRY_TEMPERATURES` 升溫重試）、`MOCK_VLLM=true` 時回固定假 segments（Windows dev） | 對應上游測試：`vendor/VibeVoice/vllm_plugin/tests/test_api.py`、`test_api_auto_recover.py` |
| [`app/worker.py`](backend/app/worker.py) | Arq worker registry：`transcribe_job`、`training_job`、`merge_lora_job`、`webhook_delivery_job`，皆委派給 `app.services.*` 實作 | 任何新背景任務必須在這裡註冊 |
| [`app/constants.py`](backend/app/constants.py) | 共用常數：prompt 模板、key mapping、MIME map、repetition 偵測閾值、WS 訊息類型、Webhook header 與 retry delay | 修改前確認上游測試 |
| [`app/errors.py`](backend/app/errors.py) | `ErrorCode` enum + `HTTP_STATUS_FOR_CODE` 映射 + `http_error()` helper（HTTP / WS / Webhook 三處共用同一錯誤碼） | 新增錯誤情境必須在此宣告 |

### Admin 端點（M3 完整）

```
/api/admin/
├── projects                      CRUD + hotwords 匯入 / 匯出
│   ├── GET / POST / PUT / DELETE  /projects[/:id]
│   ├── GET / PUT                  /projects/:id/hotwords
│   ├── GET                        /projects/:id/hotwords/export?format=txt
│   └── POST                       /projects/:id/hotwords/import (multipart, mode=append|replace)
├── jobs                          上傳 / 列表 / 取消 / segments 編輯
│   ├── POST                       /transcribe（multipart）
│   ├── GET / DELETE               /jobs[?project_id=&status=...][/:id]
│   ├── POST                       /jobs/:id/cancel
│   ├── GET                        /jobs/:id/audio  (FileResponse)
│   └── PATCH                      /jobs/:id/segments  (TranscriptEditor 自動儲存)
└── system                        4 panel 狀態
    ├── GET  /system/health
    ├── GET  /system/vllm_status
    ├── GET  /system/profile
    └── GET  /system/queue
```

### Frontend 結構（M3）

```
frontend/src/
├── api/                  client.ts (fetch wrapper) + 各模組 + types.ts (對齊 schemas.py)
├── pages/                Projects / Hotwords / Offline / Editor / System (5 routes)
├── components/           Sidebar / WaveformPlayer / TranscriptViewer / TranscriptEditor /
│                         SegmentListItem / SegmentFocusEditor / JobList / JobStatusBadge /
│                         HotwordsChips / HotwordsImportModal / UploadDropzone /
│                         ProjectFormModal / Toast
├── stores/               projectStore (全域) / editorStore (Editor scope) / toastStore (全域)
├── hooks/                useToast / useAutoSave / useKeyboardShortcuts
└── lib/                  format / time / keyboard
```

關鍵 frontend 抽象：
- **`api/client.ts`**：fetch wrapper，4xx 抽 `detail.detail` toast、401 → 「請重新登入」、5xx → 「服務異常」、network error → 「網路連線失敗」。所有 api 模組透過此 wrapper。
- **`stores/editorStore.ts`**：TranscriptEditor 用，含 `segments` / `originalSnapshot`（dirty 判定）/ `resizeSegment`（內含 `clampSegmentBounds` 防 overlap）/ `markSaved`。
- **`hooks/useAutoSave.ts`**：3 秒 idle debounce + `beforeunload` 攔截。
- **`stores/toastStore.ts`**：全域 toast queue（最多 3 條，依 level 自動逾時）。

### 資料流摘要

1. **離線轉錄**：上傳音檔到 `data/uploads/{job_id}/` → enqueue 到 Redis → worker 跑 `vllm_client.transcribe` → `parser.parse_transcription` 解析 → 存 segments → 觸發 webhook（如有 `callback_url` 或 project `webhook_url`）。
2. **長音檔自動切段**：`audio_splitter.split_long_audio`（>55 分鐘自動切，每段 50 分鐘 + 5 秒 overlap），每段獨立推論後 `merge_chunk_results` 合併。
3. **訓練**：選 dataset items → `TrainingRun` 排入 worker → 視 profile 決定是否停 vLLM → 在 `data/staging/{run_id}/` 建 symlink → docker run training container（`vibevoice-train` image）→ tail log 走 SSE 推到前端 → 完成後 merge LoRA 至 `data/merged/` → 註冊 `ModelVersion` → 重啟 vLLM（如先前停過）。

## 四、 強制慣例（不易從程式碼推得）

### 4.1 SPEC.md 為單一真實來源

實作與 SPEC.md 不一致時，先確認 SPEC.md 是否需更新（以 PR 同步），不可單方面改 code。新增功能前對照 SPEC.md 對應章節。

### 4.2 `vendor/VibeVoice/` 不得修改

該目錄為上游 microsoft/VibeVoice 的 clone，透過 docker volume `:ro` 掛載進 vLLM 與 training container。所有上游 patch 須以獨立 fork 處理，不可直接編輯。`make setup` 會 clone 缺少的 vendor。

### 4.3 Speaker ID 索引慣例（容易踩雷）

| 上下文 | 格式 |
|---|---|
| vLLM 輸出 | `"1"`、`"2"`（1-indexed，str） |
| 內部規範化（DB segment、API 回應） | 1-indexed，int |
| 訓練 JSON（上游格式） | 0-indexed，int |

轉換僅發生於三處：
- [`app/utils/parser.py`](backend/app/utils/parser.py)：vLLM 輸出 → 內部
- [`app/services/dataset_importer.py`](backend/app/services/dataset_importer.py)：訓練 JSON → 內部
- dataset exporter（M3.5）：內部 → 訓練 JSON

其他模組不可自行 ±1。

### 4.4 Job source 必須正確標記

新建 `Job` 時 `source` 欄位（`JobSource` enum）必須與來源端對齊：`ADMIN_UPLOAD` / `V1_API_ASYNC` / `V1_API_SYNC` / `V1_API_WS`。`IntegrationCall` 表只記錄 v1 來源呼叫。

### 4.5 Idempotency 鍵作用域

- 唯一鍵：`(project_id, idempotency_key)`，**範圍為 per project**（內測簡化決策；同 project 多把 API Key 共用同一範圍）
- TTL：24 小時（Redis 暫存）+ DB 唯一約束（`uq_job_idempotency`）
- 同 key 重送必須回原 `job_id`，不可建新 job
- Body hash 算法（server 內部規則，**不對 QC SDK 揭露**）：
  - sync：`sha256(file_bytes)`
  - WS：`sha256(canonical_json(start_metadata))`，canonical 為 `json.dumps(meta, separators=(",",":"), sort_keys=True)`
- 詳見 SPEC.md §17.7

### 4.6 配置與路徑抽象

- 環境變數：所有設定透過 [`app/config.py`](backend/app/config.py) `Settings`（pydantic-settings）讀取，不可在模組內直接讀 `os.environ`。
- 路徑：宿主端用相對路徑 `./data`（compose mount），容器內路徑為 `/data`。Code 內請用 `Settings.upload_dir`、`Settings.datasets_dir` 等 property，不寫死。
- DB URL：`backend_db_url` 為同步格式字串，[`app/db.py`](backend/app/db.py) 自動轉 async（`sqlite:///` → `sqlite+aiosqlite:///`、`postgresql://` → `postgresql+asyncpg://`）。

### 4.7 `app/constants.py` 為常數集散地

任何 ≥2 模組共用的字面值（prompt 模板、HTTP / WS header 名稱、enum 字串、超時秒數、retry delay 陣列）必須集中於此，不可散落。修改前確認對應上游測試是否需同步。

### 4.8 錯誤碼三處共用

`ErrorCode` enum 同時用於 HTTP response body、WS error frame、Webhook callback payload。新增錯誤情境必須先在 [`app/errors.py`](backend/app/errors.py) 宣告 enum 與 HTTP status 映射。

### 4.9 Hotwords 簡化處理（內測階段決策）

- 每個 project 維護一份共用 `hotwords` list（[`models.py`](backend/app/models.py) `Project.hotwords`）
- 本階段不支援 per-job 覆寫、不支援多 hotwords profile 切換（QC 端假設只有一個領域）
- 推論時直接 join 為逗號分隔字串注入 prompt（見 [`constants.py`](backend/app/constants.py) `build_user_prompt`）
- 長音檔切段時每段都注入同一份 hotwords，**不去重、不差異化**（token 開銷在 64k context 下可忽略）
- v1 API done frame 回傳 `hotwords_used` 給 QC 端核對，但 v1 API 不接受 caller 覆寫

### 4.10 Webhook secret 為 raw 儲存

HMAC 簽章 server 端必須持有 raw secret 才能簽，不可 hash 化。建立時唯一一次顯示 plain，UI 後續顯示前 8 碼遮罩。欄位寬度 `String(128)` 預留日後改 base64 表示或欄位加密 at-rest。詳見 SPEC.md §16.2。

### 4.11 vLLM 切 model 採 drain → switch → ready 三段式

切 model 期間 v1 端對新請求回 `503 vllm_unavailable + Retry-After: 60`；queue 已 enqueue 的 transcribe_job 在 worker 端 sleep + 重試直到 ready。詳見 SPEC.md §6.6。

### 4.12 Frontend Editor：保留與最新 store 值對齊

- TranscriptEditor 的 `save()` 用 `useEditorStore.getState()` 取最新 `segments`，**不**信賴 closure（`setTimeout` callback 觸發時 closure 內值可能 stale；使用者持續編輯期間值已變動）。
- `markSaved` 用「送出當下的 frontend snapshot」當 originalSnapshot，**不**信任 backend 回的 `updated.segments`（dict key order / 浮點精度 round-trip 後可能與 frontend JSON.stringify 不 byte-equal，導致 dirty 永遠 true）。
- SegmentFocusEditor 的時間 `number input` 與 WaveformPlayer 的 `region.update-end` **共用** `editorStore.resizeSegment`，由 `clampSegmentBounds` 防 overlap（不可侵入鄰段、最短 0.1 秒）。`patchSegment` 不含此邏輯，僅給 text / speaker_id 用。

### 4.13 Pytest fixture 不可共用 module-level engine

[`backend/tests/conftest.py`](backend/tests/conftest.py) 的 `app_client` fixture 必須建立 **獨立 test engine**，monkey-patch `app.db.engine` / `SessionLocal` 指向 test，test 結束還原。**絕不** `from app.db import engine; engine.run_sync(Base.metadata.drop_all)` —— 那個 engine 在 module 載入時用 prod `BACKEND_DB_URL=/data/app.db` 建立，drop_all 會抹掉 production schema 的業務 tables（alembic_version row 不在 ORM Base 內，會留下「version 已是 head 但 tables 已沒」的卡死狀態）。

## 五、 開發環境

### 5.1 三種開發 / 部署情境（SPEC.md §0.2）

| 情境 | dev 主機 | prod 主機 | dev 端要 GPU |
|---|---|---|---|
| (a) 全程 Linux / macOS | Linux / macOS | Linux | 是 |
| (b) 全程 Windows | Windows + WSL2 | Windows + WSL2 | 是 |
| (c) **Windows dev / Linux prod**（本專案主要模式） | Windows | Linux | **不需**（不啟 vLLM container） |

情境 (c)：M2、M3、M3.5、M6、M7 等純後端 / 前端邏輯可在 Windows 完成；M1（vLLM 部署驗證）、M4（training）必須在 Linux prod 上做。

### 5.2 技術棧版本

- **Python**：3.11+（match 上游）
- **Node.js**：20+（前端 host 端開發）
- **Docker Desktop**：24+ + Compose v2（Windows / macOS）或 Docker Engine + NVIDIA Container Toolkit（Linux prod）
- **GPU driver**：NVIDIA 535+，CUDA 12.1+（僅 Linux prod 需要）

### 5.3 依賴管理

- Backend：Poetry（`backend/pyproject.toml`）。新增依賴：在 backend container 內 `poetry add <pkg>`，commit `poetry.lock`。
- Frontend：npm（`frontend/package.json`）。

### 5.4 Lint / format / type-check 規則

- Ruff：`line-length=100`、啟用 `E`、`F`、`I`、`N`、`B`、`UP`、`ASYNC`，忽略 `E501`
- Mypy：`disallow_untyped_defs=false`，故新 code 不強制 type hint，但建議補上
- Frontend：`tsc --noEmit` 為單一型別正確性檢查；`eslint` 含 `react-hooks` plugin

### 5.5 Test 隔離

[`tests/conftest.py`](backend/tests/conftest.py) 為每個 test 建立 tmp data dir 與 sqlite，並切換 Redis 至 DB 15。`app_client` fixture 用獨立 test engine（見 §4.13）。本機跑測試前需 `docker compose up redis`。

### 5.6 開發期把 host 端改動推入 backend container

Backend image 的 `app/` 與 `tests/` 是 build 時 `COPY` 進去的，不是 volume mount。開發中改 host 端檔案後若要立刻在 container 跑：
```bash
docker cp backend/app/foo.py vibevoice-backend:/app/app/foo.py
docker cp backend/tests/test_foo.py vibevoice-backend:/app/tests/test_foo.py
docker compose exec backend pytest tests/test_foo.py
```
對 routes 變更需 `docker compose restart backend` 或 `docker compose up -d --build backend` 才生效（uvicorn 不開 reload）。

### 5.7 Frontend 必須跑過 `npm install`

`frontend/node_modules` 不在 git。第一次 clone 後必跑：
```bash
cd frontend && npm install && npm run typecheck
```
否則 `npx tsc --noEmit` 會把所有 `import` 都報錯，誤判 code 有問題。

## 六、 接手檢查清單

第一次進入此專案時：

1. 讀 SPEC.md §0（接手須知）+ §3（架構）+ §14（里程碑），約 30 分鐘。
2. `git log` 確認當前里程碑進度（最近 commit 訊息為里程碑進度線索）。
3. 跑 `make up` 啟動 redis / backend / worker / frontend；M2 後若 `/data/app.db` 是空的，跑 `docker compose exec backend alembic upgrade head`。
4. `cd frontend && npm install` 後 `npm run dev`，瀏覽器開 http://localhost:5173 看 Projects 頁。
5. 跑 `make test-backend`，確認 pytest 全綠（M3 完成時為 148+ tests）。
6. 開始實作前先看對應章節：
   - M3.5（Dataset CRUD + 多格式匯入）：SPEC.md §9
   - M4（Training）：SPEC.md §10
   - M5（長音檔切段）：SPEC.md §6.5
   - M6（v1 API）：SPEC.md §17 整章
   - M7（Compose + qc_simulator）：SPEC.md §12 + §14.2 M7
7. 實作期間若改 backend code 但容器內 pytest 沒抓到變更，看 §5.6（`docker cp` 推入 container）。
8. 如要動 TranscriptEditor / editorStore，先看 §4.12（最新 store 值對齊）與 §4.13（test engine 隔離），這兩條是 M3 階段花很多 commit 修才釐清的坑。
