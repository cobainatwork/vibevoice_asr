# YouTube 匯入功能設計（YouTube Import）

> **For agentic workers:** REQUIRED SUB-SKILL: 後續用 `superpowers:writing-plans` 寫實作計畫,再用 `superpowers:subagent-driven-development` 依 plan 派 subagent 執行。

**目標:** 讓使用者輸入 YouTube URL,系統下載音訊 + 人工字幕,音訊照常走 ASR pipeline,字幕存 DB 作為對照參考。Editor 提供 diff highlight 與並排顯示,協助校正員快速辨識 ASR 跟 YT 字幕差異段。

**架構:** 新增 `youtube_fetch_job` 走 worker 非同步下載 → 復用既有 `transcribe_job` 跑 ASR。字幕存 `Job.reference_subtitles`,Editor 提供 toggle 顯示對照。

**技術棧:** yt-dlp(subprocess)+ ffmpeg(既有)+ OpenCC(既有 s2tw)+ Python SequenceMatcher(字幕 diff)。

---

## 1. 系統脈絡與用途前提

### 1.1 用途定位

**僅供內部研究 / LoRA fine-tuning dataset 製作。** 不對外發布、不商業化、不 redistribute YouTube 內容。

### 1.2 法律前提

YouTube ToS 嚴格禁止下載非自家或非授權影片。本功能設計用於以下情境之一:

- 自家頻道內容
- Creative Commons 授權影片
- 客戶 / 合作方授權影片
- 內部研究用途(本專案明確選定情境)

UI 在 YouTube URL 輸入框旁加 disclaimer:「請確認影片授權狀態,本功能僅供內部研究 / dataset 製作使用」。使用者送出視為已確認。

### 1.3 跟既有 pipeline 的關係

```
既有:[Upload File] → Job(audio) → transcribe_job → segments

新增:[YouTube URL] → Job(source_url) → youtube_fetch_job
                                          ├─ 下載 audio
                                          ├─ 下載字幕 → Job.reference_subtitles
                                          └─ enqueue transcribe_job → segments
```

`transcribe_job` 不需要修改,完全復用。`Job.audio_path` 等欄位由 `youtube_fetch_job` 填好後再 enqueue。

---

## 2. 範圍

### 2.1 In scope

- 單支 YouTube 影片(`youtube.com/watch` / `youtu.be/` / `youtube.com/shorts/`)
- 抓 audio(MP3)+ 人工上傳字幕(VTT)
- 字幕語言優先:zh-Hant → zh-Hans → zh → zh-TW → en
- 沿用 `max_audio_duration_sec` 上限(預檢用 `yt-dlp --print duration`,超限直接拒)
- Editor 提供「對照模式」toggle:
  - 並排顯示 ASR segment 跟對應時段的 YT 字幕
  - SequenceMatcher 算相似度,< 80% 標紅底框
- 完整錯誤碼:`YOUTUBE_INVALID_URL` / `YOUTUBE_VIDEO_UNAVAILABLE` / `YOUTUBE_VIDEO_TOO_LONG` / `YOUTUBE_NO_AUDIO` / `YOUTUBE_FETCH_FAILED`

### 2.2 Out of scope(本次不做)

- Playlist / channel 批次匯入
- YouTube 自動生成字幕(品質差、跟 ASR 比對價值低)
- 多語字幕同時保留(只抓優先序中首個命中)
- 字幕直接當 dataset label(不跑 ASR)
- 影片畫面 / 縮圖
- v1 API 對外 YouTube 端點(QC 系統不需要,純內部工具)

---

## 3. Data Model 變更

### 3.1 `backend/app/models.py`

`JobSource` enum 新增成員:

```python
class JobSource(str, Enum):
    ADMIN_UPLOAD = "admin_upload"
    YOUTUBE_FETCH = "youtube_fetch"  # 新增
    V1_API_SYNC = "v1_api_sync"
    V1_API_ASYNC = "v1_api_async"
    V1_API_WS = "v1_api_ws"
```

`Job` model 新增三個欄位:

```python
class Job(Base):
    # ...既有欄位
    source_url = Column(String(500), nullable=True)
    reference_subtitles = Column(JSON, nullable=True)  # list[Segment] 或 None
    reference_subtitle_lang = Column(String(16), nullable=True)  # 命中語言碼,如 "zh-Hant"
```

### 3.2 Alembic migration

`backend/alembic/versions/xxxx_youtube_import.py`:

```python
def upgrade() -> None:
    op.add_column("jobs", sa.Column("source_url", sa.String(500), nullable=True))
    op.add_column("jobs", sa.Column("reference_subtitles", sa.JSON(), nullable=True))
    op.add_column("jobs", sa.Column("reference_subtitle_lang", sa.String(16), nullable=True))

def downgrade() -> None:
    op.drop_column("jobs", "reference_subtitle_lang")
    op.drop_column("jobs", "reference_subtitles")
    op.drop_column("jobs", "source_url")
```

### 3.3 Schema(`app/schemas.py`)

`JobOut` 新增 optional 欄位回傳:

```python
class JobOut(BaseModel):
    # ...既有
    source_url: str | None = None
    reference_subtitles: list[Segment] | None = None
    reference_subtitle_lang: str | None = None
```

新增 input schema:

```python
class YoutubeImportIn(BaseModel):
    url: HttpUrl
    project_id: int
```

---

## 4. API 端點

### 4.1 `POST /api/admin/transcribe/from_youtube`

```
Request:
  Content-Type: application/json
  Body: { "url": "https://www.youtube.com/watch?v=xxx", "project_id": 1 }

Response 202:
  { "job_id": "uuid-str" }

Errors:
  400 YOUTUBE_INVALID_URL    URL 格式不符
  404 PROJECT_NOT_FOUND      project_id 不存在
  502 YOUTUBE_FETCH_FAILED   probe 階段失敗(網路 / yt-dlp 異常)
  404 YOUTUBE_VIDEO_UNAVAILABLE 影片下架 / 私人 / 地區限制
  400 YOUTUBE_VIDEO_TOO_LONG 影片超過 max_audio_duration_sec
```

### 4.2 行為

1. 驗 URL 格式(regex 比對 `youtube.com/watch` / `youtu.be/` / `youtube.com/shorts/`)
2. 驗 `project_id` 存在
3. `yt_fetcher.probe(url)` 取 duration / title / availability,**不下載**
   - 失敗對應錯誤碼直接 4xx / 5xx 上拋
4. 驗 duration ≤ `max_audio_duration_sec`
5. 建 `Job` row:
   - `source=YOUTUBE_FETCH`
   - `source_url=url`
   - `filename=<video_title>.mp3`(yt-dlp probe 拿到)
   - `audio_path=""`(下載完才填)
   - `duration_sec=<probed duration>`
   - `status=PENDING`
   - `used_hotwords=list(project.hotwords or [])`
6. `enqueue_youtube_fetch(job_id)` → Redis queue
7. `Job.status=QUEUED`
8. 回 `202 { job_id }`

GET / DELETE / cancel / audio / segments 等既有端點不變,自動支援新 Job(因為 source_url / reference_subtitles 是 nullable 加在 JobOut)。

---

## 5. Worker / Service 層

### 5.1 `backend/app/services/youtube_fetcher.py`(新增)

```python
@dataclass
class VideoInfo:
    title: str
    duration_sec: float
    available: bool

@dataclass
class FetchResult:
    audio_path: Path
    subtitle_path: Path | None
    subtitle_lang: str | None

async def probe(url: str) -> VideoInfo: ...
    # yt-dlp --print "%(title)s|%(duration)s|%(availability)s" --skip-download
    # 解析後回 VideoInfo
    # 失敗 raise AppError(YOUTUBE_VIDEO_UNAVAILABLE / YOUTUBE_FETCH_FAILED)

async def fetch_audio_and_subtitle(
    url: str,
    job_dir: Path,
    sub_langs: str = "zh-Hant,zh-Hans,zh,zh-TW,en",
) -> FetchResult: ...
    # yt-dlp -x --audio-format mp3 --audio-quality 4 \
    #        --write-subs --sub-langs <sub_langs> --sub-format vtt \
    #        --no-write-auto-subs \
    #        -o "<job_dir>/yt.%(ext)s" \
    #        <url>
    # 完成後掃 job_dir 找 yt.mp3 / yt.<lang>.vtt
    # 失敗 raise AppError(YOUTUBE_FETCH_FAILED / YOUTUBE_NO_AUDIO)
```

實作要點:

- `asyncio.create_subprocess_exec`,**不**用 shell=True
- timeout 5 min(`asyncio.wait_for`)
- stderr 摘要當 error_message
- subtitle_lang 從生成的檔名取(例:`yt.zh-Hant.vtt` → `"zh-Hant"`)

### 5.2 `backend/app/utils/subtitle_parser.py`(新增)

```python
def parse_vtt(text: str) -> list[Segment]: ...
    # WEBVTT 格式
    # 處理 timestamp `HH:MM:SS.mmm` / `MM:SS.mmm`
    # 處理多行 cue text(換行接續)
    # 移除 cue settings(`align:start`、`<v>` 等 inline tags)

def parse_srt(text: str) -> list[Segment]: ...
    # SubRip 格式(備援,YT 預設 VTT 但偶有 SRT)

def normalize_subtitle(segments: list[Segment]) -> list[Segment]: ...
    # OpenCC s2tw(復用 parser.py 既有 _to_traditional helper、重構成共用 util)
    # 連續空白 → 單一空白、trim
```

Segment 結構沿用 ASR(`start_time`、`end_time`、`speaker_id`、`text`),YT 字幕沒 speaker 資訊→ `speaker_id=0`(內部 0-indexed 慣例)。

### 5.3 `backend/app/services/youtube_job_runner.py`(新增)

```python
async def run_youtube_fetch_job(job_id: str) -> None:
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if job is None:
            return  # cancelled / deleted

        job.status = JobStatus.RUNNING
        await db.flush()

    try:
        # 1. 下載 audio + subtitle
        job_dir = settings.upload_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        fetch = await yt_fetcher.fetch_audio_and_subtitle(job.source_url, job_dir)

        # 2. 解析字幕(若有)
        ref_subs: list[Segment] | None = None
        ref_lang: str | None = None
        if fetch.subtitle_path is not None:
            text = fetch.subtitle_path.read_text(encoding="utf-8")
            if fetch.subtitle_path.suffix == ".vtt":
                ref_subs = parse_vtt(text)
            else:
                ref_subs = parse_srt(text)
            ref_subs = normalize_subtitle(ref_subs)
            ref_lang = fetch.subtitle_lang

        # 3. 更新 Job row(status 設 QUEUED 表示「ASR 排隊中」,transcribe_job 入口會覆蓋為 RUNNING)
        async with SessionLocal() as db:
            job = await db.get(Job, job_id)
            job.audio_path = str(fetch.audio_path)
            job.reference_subtitles = [s.model_dump() for s in ref_subs] if ref_subs else None
            job.reference_subtitle_lang = ref_lang
            job.status = JobStatus.QUEUED
            await db.flush()

        # 4. enqueue 既有 ASR pipeline(transcribe_job 進入時會自行設 RUNNING)
        await enqueue_transcribe(job_id)

    except AppError as e:
        await _mark_failed(job_id, e.code, e.detail)
    except Exception as e:
        logger.exception("youtube_fetch_job unexpected error")
        await _mark_failed(job_id, ErrorCode.YOUTUBE_FETCH_FAILED, str(e)[:500])
```

### 5.4 `backend/app/worker.py`

`WorkerSettings.functions` 加 `youtube_fetch_job`:

```python
async def youtube_fetch_job(ctx: dict, job_id: str) -> None:
    await youtube_job_runner.run_youtube_fetch_job(job_id)
```

### 5.5 `backend/app/services/queue.py`

新增 `enqueue_youtube_fetch(job_id)` helper(對齊既有 `enqueue_transcribe`)。

---

## 6. 錯誤碼

`backend/app/errors.py` `ErrorCode` 新增:

```python
YOUTUBE_INVALID_URL = "youtube_invalid_url"
YOUTUBE_VIDEO_UNAVAILABLE = "youtube_video_unavailable"
YOUTUBE_VIDEO_TOO_LONG = "youtube_video_too_long"
YOUTUBE_NO_AUDIO = "youtube_no_audio"
YOUTUBE_FETCH_FAILED = "youtube_fetch_failed"
```

`HTTP_STATUS_FOR_CODE` 對應:

```python
YOUTUBE_INVALID_URL: 400,
YOUTUBE_VIDEO_UNAVAILABLE: 404,
YOUTUBE_VIDEO_TOO_LONG: 400,
YOUTUBE_NO_AUDIO: 422,
YOUTUBE_FETCH_FAILED: 502,
```

---

## 7. Frontend

### 7.1 `UploadDropzone` 元件擴充

加 tab 切換:

```
┌─────────────────────────────────────┐
│ [檔案上傳] [YouTube URL]            │  ← tab bar
├─────────────────────────────────────┤
│                                     │
│   (檔案 tab:既有 dropzone)          │
│                                     │
│   (URL tab:                         │
│    [https://youtube.com/...]  [送出]│
│    ⚠ 請確認影片授權狀態,本功能僅 │
│       供內部研究 / dataset 製作使用 │
│   )                                 │
└─────────────────────────────────────┘
```

新增 prop:

```typescript
interface UploadDropzoneProps {
  // 既有
  onUpload: (file: File) => Promise<void>;
  // 新增
  onYoutubeUrl?: (url: string) => Promise<void>;
}
```

URL 驗證(送出前 frontend 也做一次,backend 是 source of truth):

```typescript
const YT_URL_RE = /^(https?:\/\/)?(www\.)?(youtube\.com\/(watch\?v=|shorts\/)|youtu\.be\/)/;
```

### 7.2 `frontend/src/api/jobs.ts`

```typescript
export async function transcribeFromYoutube(
  url: string,
  projectId: number,
): Promise<{ job_id: string }> {
  return apiClient.post("/admin/transcribe/from_youtube", {
    url,
    project_id: projectId,
  });
}
```

### 7.3 `TranscriptEditor` 對照模式

新增 toggle(只在 `job.reference_subtitles` 有值時顯示):

```
┌─ TranscriptEditor header ──────────────────────────┐
│ {title}                          [檢視] [對照 ▼]   │
│ ☑ 顯示 YouTube 字幕對照(差異 < 80% 標紅)         │
└────────────────────────────────────────────────────┘
```

開啟對照後 `SegmentListItem` 改顯示:

```
┌─ Segment 5 ────────────────────────────────────┐
│ 00:12.40 → 00:18.20 · Speaker 1                │
│ ASR:  我們今天要討論的主題是機器學習的應用     │
│ YT:   我們今天要討論的是機器學習應用           │ ← 灰字
│ 相似度:78%(< 80%、標紅左邊框)              │
└────────────────────────────────────────────────┘
```

### 7.4 `frontend/src/lib/subtitleDiff.ts`(新增)

```typescript
import type { Segment } from "../api/types";

export interface SubtitleMatch {
  text: string;
  similarity: number;
}

// 取時段交集內的所有 YT 字幕、拼接成單一文字
export function findSubtitleAtTime(
  refSubs: Segment[],
  start: number,
  end: number,
): string { ... }

// SequenceMatcher ratio port(0~1)
export function computeSimilarity(a: string, b: string): number { ... }

export function matchSubtitle(
  refSubs: Segment[] | null,
  asrSegment: Segment,
): SubtitleMatch | null { ... }
```

實作演算法:**Levenshtein ratio**(`1 - editDistance / maxLen`),用 dp 矩陣計算。比 SequenceMatcher 簡單、效能對 < 500 字短句足夠。閾值 `SIMILARITY_THRESHOLD = 0.8` 寫在 `frontend/src/lib/constants.ts`。

### 7.5 EditorStore 擴充

`useEditorStore` 加 state:

```typescript
interface EditorState {
  // 既有
  refSubs: Segment[] | null;       // 新增
  refSubsLang: string | null;      // 新增
  diffMode: boolean;                // 新增,toggle 狀態
  setDiffMode: (on: boolean) => void;
}
```

`init(source)` 從 source 帶入 refSubs(`EditorSource` 介面也要擴充)。

### 7.6 Sidebar 不變

不新增「YouTube 匯入」獨立子頁,共用「離線轉錄」(`/projects/:id/offline`)頁面、僅內部 dropzone 加 tab。

---

## 8. yt-dlp 依賴管理

### 8.1 安裝

`backend/pyproject.toml`:

```toml
[tool.poetry.dependencies]
yt-dlp = "^2026.4.30"
```

不裝 `youtube-dl`(已停更)、不用 python-API(版本 API 易破)。一律 subprocess。

### 8.2 升級策略

YouTube 對下載器有反爬機制,yt-dlp 每 1-3 個月會釋新版對抗。決策:

- backend Docker image build 階段 `pip install -U yt-dlp` 強制最新
- 不 pin lock 版本(在 `pyproject.toml` 只寫下限)
- 影片下載失敗率高時 rebuild backend image

### 8.3 系統依賴

backend container 還需要 `ffmpeg`(既有 already installed,extract_audio_to_mp3 已用)。yt-dlp 在 `-x --audio-format mp3` 時透過 ffmpeg 轉檔,不需要額外安裝。

---

## 9. 測試策略

### 9.1 Unit tests

| 檔案 | 測試對象 | 重點 case |
|---|---|---|
| `test_subtitle_parser.py` | `parse_vtt` / `parse_srt` / `normalize_subtitle` | 標準 VTT、多行 cue、HH:MM:SS.mmm、MM:SS.mmm、空字幕、inline tags 移除、簡體 → 繁體 |
| `test_youtube_fetcher.py` | `probe` / `fetch_audio_and_subtitle` | mock subprocess 回 stdout / stderr、success / unavailable / too_long / no_subtitle |
| `test_youtube_job_runner.py` | `run_youtube_fetch_job` | 全成功(有字幕)、全成功(無字幕)、probe fail、fetch fail、subtitle parse fail |

### 9.2 Integration tests

| 檔案 | 範圍 |
|---|---|
| `test_routes_youtube_import.py` | `POST /transcribe/from_youtube` 各錯誤碼、202 成功、project_id 不存在、URL 格式錯 |
| `test_youtube_e2e.py` | mock yt-dlp 後完整走 fetch → parse → enqueue → (mock transcribe_job)→ Job 終態 |

### 9.3 Frontend tests

`subtitleDiff.test.ts`:
- `findSubtitleAtTime` 邊界(完全在區間內 / 部分交集 / 完全在區間外)
- `computeSimilarity` 完全相同(1.0)、完全不同(0.0)、空字串
- `matchSubtitle` refSubs 為 null

`UploadDropzone.test.tsx`:
- tab 切換 render
- URL 驗證 regex
- 送出 callback 呼叫

### 9.4 不做的測試

- 真實 yt-dlp 對 YouTube 的 e2e(不穩定、且違反 ToS、CI 不能跑)
- 字幕格式 fuzz test(M+1 再說)

---

## 10. 風險與緩解

| 風險 | 影響 | 緩解 |
|---|---|---|
| yt-dlp 對抗 YT 反爬、需頻繁更新 | 下載失敗 | image build 階段 `pip install -U yt-dlp`、不 pin 版本 |
| YouTube ToS 灰色 | 法律 / 合規 | 用途限定內部研究、UI disclaimer、不對外 ship |
| 字幕跟 ASR 時間軸對不齊 | diff 比對失準 | 用「時段交集」對齊、不強制 1-to-1 |
| 影片下架 / 私人化後 dataset 失復原性 | 訓練料追溯 | `Job.source_url` 永久保留、audio + subtitle 落地 `data/uploads/{job_id}/` |
| yt-dlp 下載 hang | worker 卡死 | `asyncio.wait_for` timeout 5 min、超時 raise YOUTUBE_FETCH_FAILED |
| 大量並發 YT 下載打爆頻寬 | 系統不穩 | 沿用 worker 既有 `WORKER_REPLICAS` 限制(預設 1)、無需額外控制 |
| 字幕含 HTML / inline tags(`<v>` 等) | text 含雜訊 | parser 用 regex 移除 `<[^>]+>`、保留純文字 |
| 字幕語言誤判 | 對照失效 | `reference_subtitle_lang` 存 yt-dlp 命中的實際語言碼、UI 顯示給校正員 |

---

## 11. Open Questions(本 spec 不解、後續迭代)

- Playlist 批次匯入(M+1)
- 字幕直接當 dataset label(M+1,搭配 dataset_importer)
- 多語影片同時保留多語字幕(M+2)
- yt-dlp 自動升級 schedule(M+2,搭配 cron)
- 對 Bilibili / Vimeo 等其他來源的擴充(M+3)

---

## 12. 實作順序提案(供 plan 階段參考)

1. **Backend data model + migration**(Job 新欄位 / JobSource enum / Alembic)
2. **Backend service layer**(youtube_fetcher / subtitle_parser / youtube_job_runner)
3. **Backend worker / API**(worker 註冊 / `POST /transcribe/from_youtube` 路由)
4. **Backend tests**(unit + integration、mock subprocess)
5. **Frontend lib**(subtitleDiff / api client 擴充)
6. **Frontend UI**(UploadDropzone tab / TranscriptEditor 對照模式 / EditorStore)
7. **Frontend tests + lint + typecheck**
8. **整合驗證**(實機跑一支授權影片、確認端到端通)

---

## 13. 完成條件(Done Criteria)

- [ ] backend 199+ tests 全綠、新加 youtube 相關 tests 至少 12 條
- [ ] ruff / mypy / bandit 全綠
- [ ] frontend `tsc --noEmit` / eslint 0 errors
- [ ] 實機跑授權影片成功:audio 下載 + 字幕下載 + ASR 跑完 + Editor 對照模式可切換 + diff 標紅正確
- [ ] 錯誤碼測試:invalid URL / unavailable / too_long / no_subtitle 都對應正確錯誤訊息
- [ ] yt-dlp Docker image 內版本 ≥ spec 撰寫日的最新版

---

## 14. 不變條件(Non-Goals)

- v1 API(對 QC)**不**新增 YouTube 端點
- 既有 `transcribe_job` / `parser.py` / `WaveformPlayer` 不修改邏輯
- `Project` / `Hotwords` / `Dataset` 等模型不變
- 既有上傳檔案流程不變(只是 UI 元件多 tab)
