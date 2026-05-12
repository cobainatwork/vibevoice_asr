# YouTube 匯入功能實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 `superpowers:subagent-driven-development`(推薦)或 `superpowers:executing-plans` 逐 task 執行。Steps 用 `- [ ]` checkbox 追蹤。

**Goal:** 讓使用者輸入 YouTube URL,系統下載音訊 + 人工字幕。音訊照常走 ASR pipeline,字幕存 DB 給 Editor 對照模式(diff highlight 標差異)。

**Architecture:** 新增 `youtube_fetch_job` worker 任務(下載 audio + subtitle)→ 復用既有 `transcribe_job` 跑 ASR。字幕存 `Job.reference_subtitles`,Editor 用 Levenshtein ratio 比對 ASR 跟字幕、< 80% 標紅。

**Tech Stack:** yt-dlp(subprocess)+ ffmpeg(既有)+ OpenCC s2tw(既有)+ Levenshtein ratio TS 實作。

**Spec Reference:** `docs/superpowers/specs/2026-05-12-youtube-import-design.md`

---

## Task 切分總覽

| Task | 範圍 | 依賴 |
|---|---|---|
| 1 | Backend data model + migration + ErrorCode + schemas | — |
| 2 | Backend `subtitle_parser` util(VTT / SRT / normalize) | — |
| 3 | Backend `youtube_fetcher` service(probe / fetch) | Task 1 |
| 4 | Backend `youtube_job_runner` orchestration | Task 2, 3 |
| 5 | Backend queue + worker + API route | Task 1, 4 |
| 6 | Frontend types + api client + EditorSource 擴充 | Task 5 |
| 7 | Frontend UploadDropzone tab + Offline.tsx 接 URL | Task 6 |
| 8 | Frontend subtitleDiff + editorStore + TranscriptEditor 對照模式 | Task 6 |

---

## Task 1: Backend data model + migration + ErrorCode + schemas

**Files:**
- Modify: `backend/app/models.py`(JobSource enum + Job 欄位)
- Modify: `backend/app/errors.py`(ErrorCode + HTTP_STATUS_FOR_CODE)
- Modify: `backend/app/schemas.py`(JobOut + YoutubeImportIn)
- Create: `backend/migrations/versions/<rev>_youtube_import_job_fields.py`
- Modify: `frontend/src/api/types.ts`(JobOut + JobSource enum)

### Steps

- [ ] **Step 1: 寫 model 測試先 fail**

`backend/tests/test_models_youtube.py`:
```python
"""驗證 Job model 新欄位 + JobSource enum 新成員。"""
from app.models import Job, JobSource


def test_jobsource_youtube_fetch_exists():
    assert JobSource.YOUTUBE_FETCH.value == "youtube_fetch"


def test_job_has_source_url_column():
    assert "source_url" in {c.name for c in Job.__table__.columns}


def test_job_has_reference_subtitles_column():
    cols = {c.name for c in Job.__table__.columns}
    assert "reference_subtitles" in cols
    assert "reference_subtitle_lang" in cols
```

- [ ] **Step 2: 跑測試確認 fail**

```
docker compose exec backend pytest -v tests/test_models_youtube.py
```

Expected: 3 個 test fail(AttributeError: JobSource has no YOUTUBE_FETCH / KeyError on columns)。

- [ ] **Step 3: 改 `models.py`**

`JobSource` enum 加成員(位置在第 44-48 行附近):
```python
class JobSource(str, enum.Enum):
    ADMIN_UPLOAD = "admin_upload"
    YOUTUBE_FETCH = "youtube_fetch"
    V1_API_ASYNC = "v1_api_async"
    V1_API_SYNC = "v1_api_sync"
    V1_API_WS = "v1_api_ws"
```

`Job` class 在 `finished_at` 前加 3 個欄位(位置:第 175 行 `finished_at` 之後、`__table_args__` 之前):
```python
    source_url: Mapped[str | None] = mapped_column(String(500))
    reference_subtitles: Mapped[list[dict] | None] = mapped_column(JSON)
    reference_subtitle_lang: Mapped[str | None] = mapped_column(String(16))
```

- [ ] **Step 4: 跑測試確認 pass**

```
docker compose exec backend pytest -v tests/test_models_youtube.py
```

Expected: 3 PASS。

- [ ] **Step 5: 加 ErrorCode**

`backend/app/errors.py` `ErrorCode` enum 結尾加新區塊(位置:在 `INTERNAL_ERROR = "internal_error"` 之前):
```python
    # === YouTube import errors ===
    YOUTUBE_INVALID_URL = "youtube_invalid_url"
    YOUTUBE_VIDEO_UNAVAILABLE = "youtube_video_unavailable"
    YOUTUBE_VIDEO_TOO_LONG = "youtube_video_too_long"
    YOUTUBE_NO_AUDIO = "youtube_no_audio"
    YOUTUBE_FETCH_FAILED = "youtube_fetch_failed"
```

`HTTP_STATUS_FOR_CODE` dict 對應加(在 `INTERNAL_ERROR: 500` 之前):
```python
    ErrorCode.YOUTUBE_INVALID_URL: 400,
    ErrorCode.YOUTUBE_VIDEO_UNAVAILABLE: 404,
    ErrorCode.YOUTUBE_VIDEO_TOO_LONG: 400,
    ErrorCode.YOUTUBE_NO_AUDIO: 422,
    ErrorCode.YOUTUBE_FETCH_FAILED: 502,
```

- [ ] **Step 6: 加 schemas**

`backend/app/schemas.py` 在 `JobOut`(第 140-160 行)末尾的 `finished_at: datetime | None` 之後加:
```python
    source_url: str | None = None
    reference_subtitles: list[dict] | None = None
    reference_subtitle_lang: str | None = None
```

在 `JobCreatedOut` 之前(約第 163 行)加新 input schema:
```python
class YoutubeImportIn(BaseModel):
    url: HttpUrl
    project_id: int
```

- [ ] **Step 7: 產 alembic migration**

```
docker compose exec backend alembic revision --autogenerate -m "youtube_import_job_fields"
```

檢查產生的 migration 檔(`backend/migrations/versions/<rev>_youtube_import_job_fields.py`)應該包含:
- `op.add_column("jobs", sa.Column("source_url", sa.String(500), nullable=True))`
- `op.add_column("jobs", sa.Column("reference_subtitles", sa.JSON(), nullable=True))`
- `op.add_column("jobs", sa.Column("reference_subtitle_lang", sa.String(16), nullable=True))`
- JobSource enum 變更:SQLite 對 enum 用 VARCHAR、autogenerate 可能不偵測,需手動驗 `source` 欄位仍接受新值(SQLite 不限制、Postgres 才需要 `ALTER TYPE`)

如果 autogenerate 沒抓到 enum 變更,手動補上 Postgres 相容語法(本專案目前用 SQLite,可暫不處理):
```python
# 註解保留供未來 Postgres migration 使用
# op.execute("ALTER TYPE jobsource ADD VALUE 'youtube_fetch'")
```

- [ ] **Step 8: 套用 migration、跑既有 test 驗無 regression**

```
docker compose exec backend alembic upgrade head
```

```
docker compose exec backend pytest -v
```

Expected: 既有 229+ tests 全綠 + 新加 3 test PASS。

- [ ] **Step 9: 改 frontend types**

`frontend/src/api/types.ts` 第 49 行 `JobSource` type 改:
```typescript
export type JobSource =
  | "admin_upload"
  | "youtube_fetch"
  | "v1_api_async"
  | "v1_api_sync"
  | "v1_api_ws";
```

`JobOut` interface(第 51-71 行)在 `finished_at` 之後加:
```typescript
  source_url: string | null;
  reference_subtitles: Segment[] | null;
  reference_subtitle_lang: string | null;
```

- [ ] **Step 10: 跑前端 typecheck**

```
cd frontend
npm run typecheck
```

Expected: 0 errors。

- [ ] **Step 11: Commit**

```
git add backend/app/models.py backend/app/errors.py backend/app/schemas.py backend/migrations/versions/ backend/tests/test_models_youtube.py frontend/src/api/types.ts
git commit -m "feat(youtube): Job 加 source_url / reference_subtitles 欄位 + 5 個錯誤碼"
```

---

## Task 2: Backend `subtitle_parser` util

**Files:**
- Create: `backend/app/utils/subtitle_parser.py`
- Create: `backend/tests/test_subtitle_parser.py`

### Steps

- [ ] **Step 1: 寫 VTT parser 測試**

`backend/tests/test_subtitle_parser.py`:
```python
"""VTT / SRT 解析 + s2tw 正規化。"""
import pytest
from app.utils.subtitle_parser import parse_vtt, parse_srt, normalize_subtitle


VTT_BASIC = """WEBVTT

00:00:01.000 --> 00:00:04.500
你好世界

00:00:05.200 --> 00:00:08.000
這是第二段字幕
"""

VTT_MULTILINE = """WEBVTT

00:01:00.000 --> 00:01:05.000
第一行
接續第二行

00:01:06.000 --> 00:01:10.000
單行
"""

VTT_INLINE_TAGS = """WEBVTT

00:00:01.000 --> 00:00:03.000
<v Speaker1>含 inline tag 的字幕</v>
"""

VTT_SHORT_TIMESTAMP = """WEBVTT

01:00.000 --> 01:05.000
短時間戳 MM:SS.mmm 也要支援
"""


def test_parse_vtt_basic():
    segs = parse_vtt(VTT_BASIC)
    assert len(segs) == 2
    assert segs[0]["start_time"] == pytest.approx(1.0)
    assert segs[0]["end_time"] == pytest.approx(4.5)
    assert segs[0]["text"] == "你好世界"
    assert segs[0]["speaker_id"] == 0


def test_parse_vtt_multiline_cue():
    segs = parse_vtt(VTT_MULTILINE)
    assert len(segs) == 2
    assert segs[0]["text"] == "第一行 接續第二行"


def test_parse_vtt_strips_inline_tags():
    segs = parse_vtt(VTT_INLINE_TAGS)
    assert len(segs) == 1
    assert segs[0]["text"] == "含 inline tag 的字幕"


def test_parse_vtt_short_timestamp_format():
    segs = parse_vtt(VTT_SHORT_TIMESTAMP)
    assert len(segs) == 1
    assert segs[0]["start_time"] == pytest.approx(60.0)
    assert segs[0]["end_time"] == pytest.approx(65.0)


def test_parse_vtt_empty():
    assert parse_vtt("WEBVTT\n\n") == []


SRT_BASIC = """1
00:00:01,000 --> 00:00:04,500
你好世界

2
00:00:05,200 --> 00:00:08,000
這是第二段
"""


def test_parse_srt_basic():
    segs = parse_srt(SRT_BASIC)
    assert len(segs) == 2
    assert segs[0]["start_time"] == pytest.approx(1.0)
    assert segs[1]["text"] == "這是第二段"


def test_normalize_subtitle_s2tw():
    """簡體 → 繁體(透過 OpenCC),空格壓縮、trim。"""
    raw = [
        {"start_time": 0.0, "end_time": 1.0, "speaker_id": 0, "text": "  软件优化   "},
    ]
    out = normalize_subtitle(raw)
    # OpenCC s2tw 後預期「軟體最佳化」(zh-TW 慣用詞)、空格壓縮
    assert out[0]["text"] == "軟體最佳化"
```

- [ ] **Step 2: 跑測試確認 fail**

```
docker compose exec backend pytest -v tests/test_subtitle_parser.py
```

Expected: 全部 ModuleNotFoundError(app.utils.subtitle_parser 不存在)。

- [ ] **Step 3: 寫 `subtitle_parser.py`**

`backend/app/utils/subtitle_parser.py`:
```python
"""
VTT / SRT 字幕解析 + s2tw 正規化。

YouTube 下載字幕的兩個格式:
- VTT(WebVTT)— yt-dlp 預設、含豐富 cue settings
- SRT(SubRip)— fallback 格式

解析後 Segment 結構與 ASR 一致(start_time / end_time / speaker_id / text),
方便 Editor 對照模式直接拿來比對。

YT 字幕沒 speaker 資訊 → speaker_id 固定 0(內部 0-indexed 慣例)。
"""
from __future__ import annotations

import re

from app.utils.parser import _to_traditional

_TIMESTAMP_RE = re.compile(
    r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})"
)
_INLINE_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RUN_RE = re.compile(r"\s+")


def parse_vtt(text: str) -> list[dict]:
    """解析 WEBVTT 內容為 segment list。"""
    return _parse_cues(text, time_sep=".")


def parse_srt(text: str) -> list[dict]:
    """解析 SubRip 內容為 segment list。"""
    return _parse_cues(text, time_sep=",")


def normalize_subtitle(segments: list[dict]) -> list[dict]:
    """OpenCC s2tw + 空白壓縮 + trim。"""
    out: list[dict] = []
    for s in segments:
        cleaned = _WHITESPACE_RUN_RE.sub(" ", s["text"]).strip()
        out.append({
            "start_time": s["start_time"],
            "end_time": s["end_time"],
            "speaker_id": s["speaker_id"],
            "text": _to_traditional(cleaned),
        })
    return out


# === Helpers ===


def _parse_cues(text: str, time_sep: str) -> list[dict]:
    """共用 cue 解析。SRT 用 ',' 分秒、VTT 用 '.'。"""
    segments: list[dict] = []
    blocks = re.split(r"\n\s*\n", text.strip())
    for block in blocks:
        seg = _parse_one_cue(block, time_sep)
        if seg is not None:
            segments.append(seg)
    return segments


def _parse_one_cue(block: str, time_sep: str) -> dict | None:
    lines = [ln for ln in block.splitlines() if ln.strip()]
    if not lines:
        return None

    # 找含 "-->" 的時間軸行
    time_line_idx = next(
        (i for i, ln in enumerate(lines) if "-->" in ln),
        None,
    )
    if time_line_idx is None:
        return None

    try:
        start, end = _parse_time_range(lines[time_line_idx])
    except ValueError:
        return None

    text_lines = lines[time_line_idx + 1:]
    if not text_lines:
        return None

    # 移除 inline tags(WebVTT 的 <v>, <i>, <b> 等)
    text = " ".join(text_lines)
    text = _INLINE_TAG_RE.sub("", text)
    text = _WHITESPACE_RUN_RE.sub(" ", text).strip()
    if not text:
        return None

    return {
        "start_time": start,
        "end_time": end,
        "speaker_id": 0,
        "text": text,
    }


def _parse_time_range(line: str) -> tuple[float, float]:
    """解析 "HH:MM:SS.mmm --> HH:MM:SS.mmm" 或 "MM:SS.mmm --> ...";SRT 用 ','。"""
    # 把「-->」前後切開,各自 parse
    parts = line.split("-->")
    if len(parts) != 2:
        raise ValueError(f"bad time range: {line}")
    return _parse_timestamp(parts[0]), _parse_timestamp(parts[1])


def _parse_timestamp(ts: str) -> float:
    """支援 HH:MM:SS.mmm / MM:SS.mmm / HH:MM:SS,mmm(SRT)。"""
    ts = ts.strip().split()[0]  # 去掉 cue settings 等 trailing 內容
    m = _TIMESTAMP_RE.match(ts)
    if m is None:
        raise ValueError(f"bad timestamp: {ts}")
    h = int(m.group(1) or 0)
    mm = int(m.group(2))
    s = int(m.group(3))
    ms_str = m.group(4)
    ms = int(ms_str.ljust(3, "0")[:3])
    return h * 3600 + mm * 60 + s + ms / 1000
```

- [ ] **Step 4: 跑測試確認 pass**

```
docker compose exec backend pytest -v tests/test_subtitle_parser.py
```

Expected: 7 PASS。

- [ ] **Step 5: 跑 ruff / mypy 驗風格**

```
docker compose exec backend ruff check app/utils/subtitle_parser.py tests/test_subtitle_parser.py
```

```
docker compose exec backend mypy app/utils/subtitle_parser.py
```

Expected: 0 errors。

- [ ] **Step 6: Commit**

```
git add backend/app/utils/subtitle_parser.py backend/tests/test_subtitle_parser.py
git commit -m "feat(subtitle): VTT / SRT parser + OpenCC s2tw 正規化"
```

---

## Task 3: Backend `youtube_fetcher` service

**Files:**
- Create: `backend/app/services/youtube_fetcher.py`
- Create: `backend/tests/test_youtube_fetcher.py`

### Steps

- [ ] **Step 1: 寫 probe 測試(mock subprocess)**

`backend/tests/test_youtube_fetcher.py`:
```python
"""yt-dlp probe / fetch wrapper。一律 mock subprocess、不對 YouTube 真連線。"""
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest

from app.errors import AppError, ErrorCode
from app.services.youtube_fetcher import (
    VideoInfo,
    probe,
    fetch_audio_and_subtitle,
)


@pytest.mark.asyncio
async def test_probe_success():
    """yt-dlp 回 title|duration|available → VideoInfo。"""
    fake_stdout = b"My Video|125.5|public\n"
    fake_stderr = b""

    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(fake_stdout, fake_stderr))
    proc.returncode = 0

    with patch(
        "app.services.youtube_fetcher.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        info = await probe("https://youtu.be/abc")

    assert info.title == "My Video"
    assert info.duration_sec == pytest.approx(125.5)
    assert info.available is True


@pytest.mark.asyncio
async def test_probe_video_unavailable():
    """yt-dlp returncode != 0 + stderr 含 'Video unavailable' → YOUTUBE_VIDEO_UNAVAILABLE。"""
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(b"", b"ERROR: Video unavailable"))
    proc.returncode = 1

    with patch(
        "app.services.youtube_fetcher.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        with pytest.raises(AppError) as exc:
            await probe("https://youtu.be/dead")

    assert exc.value.code == ErrorCode.YOUTUBE_VIDEO_UNAVAILABLE


@pytest.mark.asyncio
async def test_probe_generic_failure():
    """非 known pattern 的失敗 → YOUTUBE_FETCH_FAILED。"""
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(b"", b"ERROR: some unknown network issue"))
    proc.returncode = 1

    with patch(
        "app.services.youtube_fetcher.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        with pytest.raises(AppError) as exc:
            await probe("https://youtu.be/xxx")

    assert exc.value.code == ErrorCode.YOUTUBE_FETCH_FAILED


@pytest.mark.asyncio
async def test_fetch_audio_and_subtitle_success(tmp_path: Path):
    """fetch 成功:audio + subtitle 落地。"""
    job_dir = tmp_path / "job1"
    job_dir.mkdir()
    (job_dir / "yt.mp3").write_bytes(b"\x00" * 100)
    (job_dir / "yt.zh-Hant.vtt").write_text("WEBVTT\n\n", encoding="utf-8")

    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(b"", b""))
    proc.returncode = 0

    with patch(
        "app.services.youtube_fetcher.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await fetch_audio_and_subtitle("https://youtu.be/x", job_dir)

    assert result.audio_path == job_dir / "yt.mp3"
    assert result.subtitle_path == job_dir / "yt.zh-Hant.vtt"
    assert result.subtitle_lang == "zh-Hant"


@pytest.mark.asyncio
async def test_fetch_no_subtitle(tmp_path: Path):
    """fetch 成功但無字幕 → subtitle_path / subtitle_lang 為 None。"""
    job_dir = tmp_path / "job1"
    job_dir.mkdir()
    (job_dir / "yt.mp3").write_bytes(b"\x00" * 100)

    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(b"", b""))
    proc.returncode = 0

    with patch(
        "app.services.youtube_fetcher.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await fetch_audio_and_subtitle("https://youtu.be/x", job_dir)

    assert result.audio_path == job_dir / "yt.mp3"
    assert result.subtitle_path is None
    assert result.subtitle_lang is None


@pytest.mark.asyncio
async def test_fetch_no_audio_raises(tmp_path: Path):
    """yt-dlp 成功但找不到 mp3 → YOUTUBE_NO_AUDIO。"""
    job_dir = tmp_path / "job1"
    job_dir.mkdir()

    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(b"", b""))
    proc.returncode = 0

    with patch(
        "app.services.youtube_fetcher.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        with pytest.raises(AppError) as exc:
            await fetch_audio_and_subtitle("https://youtu.be/x", job_dir)

    assert exc.value.code == ErrorCode.YOUTUBE_NO_AUDIO


@pytest.mark.asyncio
async def test_fetch_subprocess_failure(tmp_path: Path):
    """yt-dlp returncode != 0 → YOUTUBE_FETCH_FAILED。"""
    job_dir = tmp_path / "job1"
    job_dir.mkdir()

    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(b"", b"ERROR: download failed"))
    proc.returncode = 1

    with patch(
        "app.services.youtube_fetcher.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        with pytest.raises(AppError) as exc:
            await fetch_audio_and_subtitle("https://youtu.be/x", job_dir)

    assert exc.value.code == ErrorCode.YOUTUBE_FETCH_FAILED
```

- [ ] **Step 2: 跑測試確認 fail**

```
docker compose exec backend pytest -v tests/test_youtube_fetcher.py
```

Expected: ModuleNotFoundError(app.services.youtube_fetcher 不存在)。

- [ ] **Step 3: 寫 `youtube_fetcher.py`**

`backend/app/services/youtube_fetcher.py`:
```python
"""
yt-dlp 包裝層:probe(取 metadata、不下載)+ fetch(下載 audio + subtitle)。

一律 subprocess、不用 yt-dlp 的 python API(版本 API 易破)。
失敗對應 ErrorCode.YOUTUBE_* 系列。

⚠ SECURITY: 只傳已驗證過的 URL 進來、subprocess 不過 shell。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from app.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)

DEFAULT_SUB_LANGS = "zh-Hant,zh-Hans,zh,zh-TW,en"
PROBE_TIMEOUT_SEC = 30
FETCH_TIMEOUT_SEC = 300  # 5 min


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


async def probe(url: str) -> VideoInfo:
    """
    取影片 metadata,不下載。

    yt-dlp `--print "%(title)s|%(duration)s|%(availability)s" --skip-download <url>`
    輸出單行 "Title|125.5|public"。
    """
    cmd = [
        "yt-dlp",
        "--print", "%(title)s|%(duration)s|%(availability)s",
        "--skip-download",
        "--no-warnings",
        url,
    ]
    stdout, stderr, rc = await _run_subprocess(cmd, PROBE_TIMEOUT_SEC)

    if rc != 0:
        _raise_for_yt_dlp_error(stderr)

    line = stdout.decode("utf-8", errors="replace").strip()
    parts = line.split("|")
    if len(parts) < 3:
        raise AppError(
            ErrorCode.YOUTUBE_FETCH_FAILED,
            f"unexpected probe output: {line[:200]}",
        )
    title, dur_str, avail = parts[0], parts[1], parts[2]
    try:
        duration = float(dur_str)
    except ValueError as e:
        raise AppError(
            ErrorCode.YOUTUBE_FETCH_FAILED,
            f"bad duration in probe: {dur_str}",
        ) from e

    return VideoInfo(
        title=title,
        duration_sec=duration,
        available=avail.lower() in ("public", "unlisted", "needs_auth"),
    )


async def fetch_audio_and_subtitle(
    url: str,
    job_dir: Path,
    sub_langs: str = DEFAULT_SUB_LANGS,
) -> FetchResult:
    """
    下載 audio(MP3)+ 字幕(VTT,人工上傳優先)。

    輸出檔案命名:`yt.mp3` / `yt.<lang>.vtt`。
    無字幕時 subtitle_path / subtitle_lang 為 None。
    """
    cmd = [
        "yt-dlp",
        "-x", "--audio-format", "mp3", "--audio-quality", "4",
        "--write-subs",
        "--no-write-auto-subs",
        "--sub-langs", sub_langs,
        "--sub-format", "vtt",
        "-o", str(job_dir / "yt.%(ext)s"),
        "--no-warnings",
        url,
    ]
    _, stderr, rc = await _run_subprocess(cmd, FETCH_TIMEOUT_SEC)

    if rc != 0:
        _raise_for_yt_dlp_error(stderr)

    audio_path = job_dir / "yt.mp3"
    if not audio_path.exists():
        raise AppError(
            ErrorCode.YOUTUBE_NO_AUDIO,
            "yt-dlp succeeded but mp3 not produced",
        )

    subtitle_path, subtitle_lang = _find_subtitle(job_dir, sub_langs)
    return FetchResult(
        audio_path=audio_path,
        subtitle_path=subtitle_path,
        subtitle_lang=subtitle_lang,
    )


# === Helpers ===


async def _run_subprocess(
    cmd: list[str], timeout_sec: int,
) -> tuple[bytes, bytes, int]:
    """執行 subprocess、timeout、回 (stdout, stderr, returncode)。"""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_sec,
        )
    except TimeoutError as e:
        proc.kill()
        await proc.wait()
        raise AppError(
            ErrorCode.YOUTUBE_FETCH_FAILED,
            f"yt-dlp timeout after {timeout_sec}s",
        ) from e
    return stdout, stderr, proc.returncode or 0


def _raise_for_yt_dlp_error(stderr: bytes) -> None:
    """把 yt-dlp stderr 分類成對應 ErrorCode。"""
    msg = stderr.decode("utf-8", errors="replace").lower()
    if "video unavailable" in msg or "private video" in msg or "removed" in msg:
        raise AppError(
            ErrorCode.YOUTUBE_VIDEO_UNAVAILABLE,
            stderr.decode("utf-8", errors="replace")[:500],
        )
    if "age" in msg and "restricted" in msg:
        raise AppError(
            ErrorCode.YOUTUBE_VIDEO_UNAVAILABLE,
            stderr.decode("utf-8", errors="replace")[:500],
        )
    raise AppError(
        ErrorCode.YOUTUBE_FETCH_FAILED,
        stderr.decode("utf-8", errors="replace")[:500],
    )


def _find_subtitle(
    job_dir: Path, sub_langs: str,
) -> tuple[Path | None, str | None]:
    """依語言優先序找命中字幕檔。"""
    for lang in sub_langs.split(","):
        candidate = job_dir / f"yt.{lang.strip()}.vtt"
        if candidate.exists():
            return candidate, lang.strip()
    return None, None
```

- [ ] **Step 4: 跑測試確認 pass**

```
docker compose exec backend pytest -v tests/test_youtube_fetcher.py
```

Expected: 7 PASS。

- [ ] **Step 5: 補 pyproject 依賴**

`backend/pyproject.toml` `[tool.poetry.dependencies]` 區塊加:
```toml
yt-dlp = "^2026.4.30"
```

- [ ] **Step 6: 重 build backend image 並驗 yt-dlp 可用**

```
docker compose build backend
```

```
docker compose exec backend yt-dlp --version
```

Expected: 印出版本字串(`2026.x.x` 或更新)。

- [ ] **Step 7: 跑 ruff / mypy**

```
docker compose exec backend ruff check app/services/youtube_fetcher.py tests/test_youtube_fetcher.py
```

```
docker compose exec backend mypy app/services/youtube_fetcher.py
```

Expected: 0 errors。

- [ ] **Step 8: Commit**

```
git add backend/app/services/youtube_fetcher.py backend/tests/test_youtube_fetcher.py backend/pyproject.toml backend/poetry.lock
git commit -m "feat(youtube): yt-dlp wrapper(probe + fetch)、subprocess mock 測試"
```

---

## Task 4: Backend `youtube_job_runner` orchestration

**Files:**
- Create: `backend/app/services/youtube_job_runner.py`
- Create: `backend/tests/test_youtube_job_runner.py`

### Steps

- [ ] **Step 1: 寫 orchestration 測試**

`backend/tests/test_youtube_job_runner.py`:
```python
"""youtube_fetch_job 流程整合:probe → fetch → parse → enqueue transcribe。"""
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest

from app.models import Job, JobSource, JobStatus, Project
from app.services.youtube_fetcher import FetchResult, VideoInfo
from app.services.youtube_job_runner import run_youtube_fetch_job


@pytest.mark.asyncio
async def test_youtube_fetch_job_success_with_subtitle(
    app_client, sync_session, tmp_path,
):
    """完整成功路徑:有字幕 → reference_subtitles 寫入 → enqueue transcribe。"""
    # arrange:project + job(source=YOUTUBE_FETCH, status=QUEUED)
    project = Project(name="p1")
    sync_session.add(project)
    sync_session.commit()

    job = Job(
        id="job-yt-1",
        project_id=project.id,
        source=JobSource.YOUTUBE_FETCH,
        source_url="https://youtu.be/abc",
        filename="placeholder.mp3",
        audio_path="",
        duration_sec=120.0,
        status=JobStatus.QUEUED,
    )
    sync_session.add(job)
    sync_session.commit()

    # mock fetcher + enqueue
    sub_file = tmp_path / "yt.zh-Hant.vtt"
    sub_file.write_text(
        "WEBVTT\n\n00:00:01.000 --> 00:00:05.000\n你好\n",
        encoding="utf-8",
    )
    fake_fetch = FetchResult(
        audio_path=tmp_path / "yt.mp3",
        subtitle_path=sub_file,
        subtitle_lang="zh-Hant",
    )

    with patch(
        "app.services.youtube_job_runner.youtube_fetcher.fetch_audio_and_subtitle",
        AsyncMock(return_value=fake_fetch),
    ), patch(
        "app.services.youtube_job_runner.enqueue_transcribe",
        AsyncMock(return_value="job-yt-1"),
    ) as mock_enqueue:
        await run_youtube_fetch_job("job-yt-1")

    # assert
    sync_session.expire_all()
    job = sync_session.get(Job, "job-yt-1")
    assert job.audio_path == str(tmp_path / "yt.mp3")
    assert job.reference_subtitle_lang == "zh-Hant"
    assert job.reference_subtitles is not None
    assert len(job.reference_subtitles) == 1
    assert job.reference_subtitles[0]["text"] == "你好"
    assert job.status == JobStatus.QUEUED
    mock_enqueue.assert_awaited_once_with("job-yt-1")


@pytest.mark.asyncio
async def test_youtube_fetch_job_no_subtitle(app_client, sync_session, tmp_path):
    """無字幕 → reference_subtitles 為 None、仍 enqueue transcribe。"""
    project = Project(name="p2")
    sync_session.add(project)
    sync_session.commit()

    job = Job(
        id="job-yt-2",
        project_id=project.id,
        source=JobSource.YOUTUBE_FETCH,
        source_url="https://youtu.be/no-sub",
        filename="placeholder.mp3",
        audio_path="",
        duration_sec=60.0,
        status=JobStatus.QUEUED,
    )
    sync_session.add(job)
    sync_session.commit()

    fake_fetch = FetchResult(
        audio_path=tmp_path / "yt.mp3",
        subtitle_path=None,
        subtitle_lang=None,
    )
    with patch(
        "app.services.youtube_job_runner.youtube_fetcher.fetch_audio_and_subtitle",
        AsyncMock(return_value=fake_fetch),
    ), patch(
        "app.services.youtube_job_runner.enqueue_transcribe",
        AsyncMock(return_value="job-yt-2"),
    ):
        await run_youtube_fetch_job("job-yt-2")

    sync_session.expire_all()
    job = sync_session.get(Job, "job-yt-2")
    assert job.reference_subtitles is None
    assert job.reference_subtitle_lang is None
    assert job.audio_path == str(tmp_path / "yt.mp3")


@pytest.mark.asyncio
async def test_youtube_fetch_job_fetch_failed(app_client, sync_session):
    """fetch_audio_and_subtitle raise AppError → Job.status=FAILED + error_code 記錄。"""
    from app.errors import AppError, ErrorCode

    project = Project(name="p3")
    sync_session.add(project)
    sync_session.commit()

    job = Job(
        id="job-yt-3",
        project_id=project.id,
        source=JobSource.YOUTUBE_FETCH,
        source_url="https://youtu.be/dead",
        filename="placeholder.mp3",
        audio_path="",
        duration_sec=60.0,
        status=JobStatus.QUEUED,
    )
    sync_session.add(job)
    sync_session.commit()

    with patch(
        "app.services.youtube_job_runner.youtube_fetcher.fetch_audio_and_subtitle",
        AsyncMock(side_effect=AppError(
            ErrorCode.YOUTUBE_VIDEO_UNAVAILABLE,
            "Video unavailable",
        )),
    ):
        await run_youtube_fetch_job("job-yt-3")

    sync_session.expire_all()
    job = sync_session.get(Job, "job-yt-3")
    assert job.status == JobStatus.FAILED
    assert job.error is not None
    assert "youtube_video_unavailable" in job.error


@pytest.mark.asyncio
async def test_youtube_fetch_job_missing_job_id(app_client):
    """job_id 不存在 → 靜默 return(視為 cancelled / deleted)。"""
    await run_youtube_fetch_job("nonexistent-job-id")
    # 不 raise 即可
```

> Notes:
> - `app_client` / `sync_session` fixture 來自既有 `conftest.py`(同 M3.5 dataset 測試模式)。若 fixture 不存在或介面不同、實作 subagent 必須先看 `backend/tests/conftest.py` 對齊真實 fixture name。

- [ ] **Step 2: 跑測試確認 fail**

```
docker compose exec backend pytest -v tests/test_youtube_job_runner.py
```

Expected: ModuleNotFoundError。

- [ ] **Step 3: 寫 `youtube_job_runner.py`**

`backend/app/services/youtube_job_runner.py`:
```python
"""
YouTube fetch job orchestration。

流程:
  1. 取 Job 從 DB(status 應為 QUEUED)
  2. 標 RUNNING
  3. youtube_fetcher.fetch_audio_and_subtitle(下載 audio + 字幕)
  4. 字幕解析 + s2tw 正規化 → Job.reference_subtitles
  5. 寫 Job.audio_path / reference_subtitles / reference_subtitle_lang
  6. status 改 QUEUED(交棒給 transcribe_job)
  7. enqueue_transcribe(復用既有 ASR pipeline)

失敗 → Job.status=FAILED + Job.error 記 ErrorCode + detail。
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.db import SessionLocal
from app.errors import AppError, ErrorCode
from app.models import Job, JobStatus
from app.services import youtube_fetcher
from app.services.queue import enqueue_transcribe
from app.utils.subtitle_parser import normalize_subtitle, parse_vtt
from app.config import get_settings

logger = logging.getLogger(__name__)


async def run_youtube_fetch_job(job_id: str) -> None:
    """Entry point — 由 worker.youtube_fetch_job 呼叫。"""
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if job is None:
            logger.info("youtube_fetch_job %s not found, skip", job_id)
            return

        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        await db.flush()
        await db.commit()

    try:
        await _execute_fetch(job_id)
    except AppError as e:
        await _mark_failed(job_id, e.code, e.detail)
    except Exception as e:  # noqa: BLE001
        logger.exception("youtube_fetch_job unexpected error: %s", job_id)
        await _mark_failed(job_id, ErrorCode.YOUTUBE_FETCH_FAILED, str(e)[:500])


# === Helpers ===


async def _execute_fetch(job_id: str) -> None:
    settings = get_settings()
    job_dir = settings.upload_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if job is None or job.source_url is None:
            raise AppError(
                ErrorCode.YOUTUBE_FETCH_FAILED,
                "job source_url missing",
            )
        url = job.source_url

    fetch = await youtube_fetcher.fetch_audio_and_subtitle(url, job_dir)

    ref_subs: list[dict] | None = None
    ref_lang: str | None = None
    if fetch.subtitle_path is not None:
        text = fetch.subtitle_path.read_text(encoding="utf-8")
        parsed = parse_vtt(text)
        ref_subs = normalize_subtitle(parsed)
        ref_lang = fetch.subtitle_lang

    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if job is None:
            return
        job.audio_path = str(fetch.audio_path)
        job.reference_subtitles = ref_subs
        job.reference_subtitle_lang = ref_lang
        job.status = JobStatus.QUEUED  # 交棒給 transcribe_job
        await db.flush()
        await db.commit()

    await enqueue_transcribe(job_id)


async def _mark_failed(
    job_id: str, code: ErrorCode, detail: str,
) -> None:
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if job is None:
            return
        job.status = JobStatus.FAILED
        job.error = f"{code.value}: {detail}"
        job.finished_at = datetime.utcnow()
        await db.flush()
        await db.commit()
```

- [ ] **Step 4: 跑測試確認 pass**

```
docker compose exec backend pytest -v tests/test_youtube_job_runner.py
```

Expected: 4 PASS。

- [ ] **Step 5: 跑 ruff / mypy**

```
docker compose exec backend ruff check app/services/youtube_job_runner.py tests/test_youtube_job_runner.py
```

```
docker compose exec backend mypy app/services/youtube_job_runner.py
```

Expected: 0 errors。

- [ ] **Step 6: Commit**

```
git add backend/app/services/youtube_job_runner.py backend/tests/test_youtube_job_runner.py
git commit -m "feat(youtube): job runner 統合 fetch → parse → enqueue transcribe"
```

---

## Task 5: Backend queue + worker + API route

**Files:**
- Modify: `backend/app/services/queue.py`(加 enqueue_youtube_fetch)
- Modify: `backend/app/worker.py`(註冊 youtube_fetch_job)
- Modify: `backend/app/routes/admin/jobs.py`(加 POST `/transcribe/from_youtube`)
- Create: `backend/tests/test_routes_youtube_import.py`

### Steps

- [ ] **Step 1: 寫 API route 測試**

`backend/tests/test_routes_youtube_import.py`:
```python
"""POST /api/admin/transcribe/from_youtube 端點。"""
from unittest.mock import AsyncMock, patch
import pytest

from app.models import Job, JobSource, JobStatus, Project
from app.services.youtube_fetcher import VideoInfo


@pytest.mark.asyncio
async def test_transcribe_from_youtube_success(app_client, sync_session):
    """成功:probe pass → 建 Job + enqueue。"""
    project = Project(name="p1")
    sync_session.add(project)
    sync_session.commit()

    with patch(
        "app.routes.admin.jobs.youtube_fetcher.probe",
        AsyncMock(return_value=VideoInfo(
            title="Test Video", duration_sec=120.0, available=True,
        )),
    ), patch(
        "app.routes.admin.jobs.enqueue_youtube_fetch",
        AsyncMock(return_value="fake-job-id"),
    ):
        resp = await app_client.post(
            "/api/admin/transcribe/from_youtube",
            json={"url": "https://www.youtube.com/watch?v=abc", "project_id": project.id},
        )

    assert resp.status_code == 202
    body = resp.json()
    assert "job_id" in body

    # DB 應該有一個對應的 Job
    sync_session.expire_all()
    jobs = sync_session.query(Job).filter_by(source=JobSource.YOUTUBE_FETCH).all()
    assert len(jobs) == 1
    assert jobs[0].source_url == "https://www.youtube.com/watch?v=abc"
    assert jobs[0].status == JobStatus.QUEUED


@pytest.mark.asyncio
async def test_transcribe_from_youtube_invalid_url(app_client, sync_session):
    """非 YouTube URL → 400 YOUTUBE_INVALID_URL。"""
    project = Project(name="p1")
    sync_session.add(project)
    sync_session.commit()

    resp = await app_client.post(
        "/api/admin/transcribe/from_youtube",
        json={"url": "https://vimeo.com/12345", "project_id": project.id},
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == "youtube_invalid_url"


@pytest.mark.asyncio
async def test_transcribe_from_youtube_project_not_found(app_client):
    """project_id 不存在 → 404。"""
    resp = await app_client.post(
        "/api/admin/transcribe/from_youtube",
        json={"url": "https://www.youtube.com/watch?v=abc", "project_id": 9999},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "project_not_found"


@pytest.mark.asyncio
async def test_transcribe_from_youtube_video_too_long(app_client, sync_session):
    """probe 回 duration 超過 max_audio_duration_sec → 400。"""
    project = Project(name="p1")
    sync_session.add(project)
    sync_session.commit()

    with patch(
        "app.routes.admin.jobs.youtube_fetcher.probe",
        AsyncMock(return_value=VideoInfo(
            title="Long", duration_sec=99999.0, available=True,
        )),
    ):
        resp = await app_client.post(
            "/api/admin/transcribe/from_youtube",
            json={"url": "https://www.youtube.com/watch?v=long", "project_id": project.id},
        )

    assert resp.status_code == 400
    assert resp.json()["code"] == "youtube_video_too_long"


@pytest.mark.asyncio
async def test_transcribe_from_youtube_video_unavailable(app_client, sync_session):
    """probe raise YOUTUBE_VIDEO_UNAVAILABLE → 404。"""
    from app.errors import AppError, ErrorCode

    project = Project(name="p1")
    sync_session.add(project)
    sync_session.commit()

    with patch(
        "app.routes.admin.jobs.youtube_fetcher.probe",
        AsyncMock(side_effect=AppError(
            ErrorCode.YOUTUBE_VIDEO_UNAVAILABLE, "Video unavailable",
        )),
    ):
        resp = await app_client.post(
            "/api/admin/transcribe/from_youtube",
            json={"url": "https://www.youtube.com/watch?v=dead", "project_id": project.id},
        )

    assert resp.status_code == 404
    assert resp.json()["code"] == "youtube_video_unavailable"
```

- [ ] **Step 2: 跑測試確認 fail**

```
docker compose exec backend pytest -v tests/test_routes_youtube_import.py
```

Expected: 404 / AttributeError(`/transcribe/from_youtube` 不存在 / enqueue_youtube_fetch 沒定義)。

- [ ] **Step 3: 改 `queue.py` 加 enqueue_youtube_fetch**

`backend/app/services/queue.py` 在 `enqueue_transcribe` 之後(約第 37 行後)加:
```python
async def enqueue_youtube_fetch(job_id: str) -> str:
    """Enqueue 一個 youtube_fetch_job。"""
    pool = await get_pool()
    await pool.enqueue_job(
        "youtube_fetch_job", job_id,
        _job_id=f"youtube_fetch:{job_id}",
    )
    return job_id
```

- [ ] **Step 4: 改 `worker.py` 註冊 youtube_fetch_job**

`backend/app/worker.py` 在 `transcribe_job` 之後(約第 39 行後)加:
```python
async def youtube_fetch_job(ctx: dict, job_id: str) -> str:
    """YouTube 下載 + 字幕解析、完成後接力給 transcribe_job。"""
    from app.services.youtube_job_runner import run_youtube_fetch_job

    logger.info("youtube_fetch_job started: %s", job_id)
    await run_youtube_fetch_job(job_id)
    logger.info("youtube_fetch_job finished: %s", job_id)
    return job_id
```

`WorkerSettings.functions` list(約第 84-89 行)加 `youtube_fetch_job`:
```python
functions: list[Any] = [
    transcribe_job,
    youtube_fetch_job,
    training_job,
    merge_lora_job,
    webhook_delivery_job,
]
```

- [ ] **Step 5: 改 `routes/admin/jobs.py` 加 POST `/transcribe/from_youtube`**

`backend/app/routes/admin/jobs.py` 在 `transcribe_admin` 函式(第 35-57 行)之後加新端點:
```python
import re

from app.schemas import YoutubeImportIn
from app.services import youtube_fetcher
from app.services.queue import enqueue_youtube_fetch

YOUTUBE_URL_RE = re.compile(
    r"^https?://(www\.)?(youtube\.com/(watch\?v=|shorts/)|youtu\.be/)",
    re.IGNORECASE,
)


@router.post("/transcribe/from_youtube", response_model=JobCreatedOut, status_code=202)
async def transcribe_from_youtube(
    payload: YoutubeImportIn,
    db: AsyncSession = Depends(get_db),
):
    """從 YouTube URL 建 Job + 下載音訊 + 抓字幕、完成後自動跑 ASR。"""
    settings = get_settings()
    url = str(payload.url)
    if not YOUTUBE_URL_RE.match(url):
        raise http_error(
            ErrorCode.YOUTUBE_INVALID_URL,
            f"not a supported YouTube URL: {url[:200]}",
        )

    project = await _ensure_project(db, payload.project_id)
    info = await youtube_fetcher.probe(url)

    if info.duration_sec > settings.max_audio_duration_sec:
        raise http_error(
            ErrorCode.YOUTUBE_VIDEO_TOO_LONG,
            f"video {info.duration_sec:.1f}s exceeds limit "
            f"{settings.max_audio_duration_sec}s",
        )

    job = Job(
        project_id=project.id,
        source=JobSource.YOUTUBE_FETCH,
        source_url=url,
        filename=f"{info.title}.mp3",
        audio_path="",  # youtube_fetch_job 完成後才填
        duration_sec=info.duration_sec,
        status=JobStatus.PENDING,
        used_hotwords=list(project.hotwords or []),
    )
    db.add(job)
    await db.flush()

    await enqueue_youtube_fetch(job.id)
    job.status = JobStatus.QUEUED
    await db.flush()

    logger.info(
        "youtube fetch enqueued: job_id=%s project_id=%d duration=%.1f url=%s",
        job.id, project.id, info.duration_sec, url[:100],
    )
    return JobCreatedOut(job_id=job.id)
```

- [ ] **Step 6: 跑測試確認 pass**

```
docker compose exec backend pytest -v tests/test_routes_youtube_import.py
```

Expected: 5 PASS。

- [ ] **Step 7: 跑全部後端測試確認無 regression**

```
docker compose exec backend pytest -v
```

Expected: 既有 229+ + 新加 19 個全綠。

- [ ] **Step 8: 跑 ruff / mypy / bandit**

```
docker compose exec backend ruff check app/
```

```
docker compose exec backend mypy app/
```

```
docker compose exec backend bandit -r app/ -ll
```

Expected: 0 errors / 0 high severity。

- [ ] **Step 9: Commit**

```
git add backend/app/services/queue.py backend/app/worker.py backend/app/routes/admin/jobs.py backend/tests/test_routes_youtube_import.py
git commit -m "feat(youtube): API route + worker 註冊 + enqueue helper"
```

---

## Task 6: Frontend types + api client + EditorSource 擴充

**Files:**
- Modify: `frontend/src/api/jobs.ts`(加 transcribeFromYoutube)
- Modify: `frontend/src/lib/editorSource.ts`(EditorLoadResult 加 refSubs / refLang)

### Steps

- [ ] **Step 1: 改 `api/jobs.ts`**

`frontend/src/api/jobs.ts` 在 `upload` 之後加:
```typescript
transcribeFromYoutube: (url: string, projectId: number) =>
  api.post<JobCreatedOut>(`${ADMIN}/transcribe/from_youtube`, {
    url,
    project_id: projectId,
  }),
```

- [ ] **Step 2: 改 `lib/editorSource.ts`**

`EditorLoadResult` interface(第 5-10 行)加:
```typescript
export interface EditorLoadResult {
  segments: Segment[];
  audioUrl: string;
  durationSec: number;
  title: string;
  // 新增:YT 對照參考字幕(只有 source=YOUTUBE_FETCH 的 Job 才有)
  referenceSubtitles: Segment[] | null;
  referenceSubtitleLang: string | null;
}
```

`jobEditorSource` 的 `load()`(第 22-32 行)在 return 中加:
```typescript
async load() {
  const job = await jobsApi.get(jobId);
  return {
    segments: job.segments ?? [],
    audioUrl: jobsApi.audioUrl(jobId),
    durationSec: job.duration_sec ?? 0,
    title: job.filename,
    referenceSubtitles: job.reference_subtitles ?? null,
    referenceSubtitleLang: job.reference_subtitle_lang ?? null,
  };
}
```

`datasetEditorSource` 的 `load()`(第 46-58 行)也要對齊加(dataset 不會有 YT 字幕、固定 null):
```typescript
async load() {
  const item = await datasetsApi.get(itemId);
  return {
    segments: item.label.segments.map((s) => ({
      speaker_id: s.speaker + 1,
      text: s.text,
      start_time: s.start,
      end_time: s.end,
    })),
    audioUrl: datasetsApi.audioUrl(itemId),
    durationSec: item.duration_sec,
    title: `Dataset #${itemId}`,
    referenceSubtitles: null,
    referenceSubtitleLang: null,
  };
}
```

- [ ] **Step 3: 跑 typecheck**

```
cd frontend
npm run typecheck
```

Expected: 0 errors。

- [ ] **Step 4: Commit**

```
git add frontend/src/api/jobs.ts frontend/src/lib/editorSource.ts
git commit -m "feat(youtube): frontend api client + EditorSource 帶 reference_subtitles"
```

---

## Task 7: Frontend UploadDropzone tab + Offline.tsx 接 URL

**Files:**
- Modify: `frontend/src/components/UploadDropzone.tsx`(加 tab)
- Modify: `frontend/src/pages/Offline.tsx`(接 onYoutubeUrl)
- Create: `frontend/src/lib/youtubeUrl.ts`(URL 驗證 regex)

### Steps

- [ ] **Step 1: 寫 URL 驗證 helper + test**

`frontend/src/lib/youtubeUrl.ts`:
```typescript
const YT_URL_RE = /^https?:\/\/(www\.)?(youtube\.com\/(watch\?v=|shorts\/)|youtu\.be\/)/i;

export function isYoutubeUrl(url: string): boolean {
  return YT_URL_RE.test(url.trim());
}
```

`frontend/src/lib/youtubeUrl.test.ts`(如果專案有 vitest / jest;若沒測試框架本步驟改成手動 sanity check):
```typescript
import { describe, it, expect } from "vitest";
import { isYoutubeUrl } from "./youtubeUrl";

describe("isYoutubeUrl", () => {
  it.each([
    ["https://www.youtube.com/watch?v=abc", true],
    ["https://youtube.com/watch?v=abc", true],
    ["https://youtu.be/abc", true],
    ["https://www.youtube.com/shorts/abc", true],
    ["http://youtube.com/watch?v=abc", true],
    ["https://vimeo.com/12345", false],
    ["not a url", false],
    ["", false],
  ])("%s → %s", (url, expected) => {
    expect(isYoutubeUrl(url)).toBe(expected);
  });
});
```

> **Note:** 如果前端尚未引入 vitest,本檔不寫;改成在 `Offline.tsx` 整合測試時手動 cover。

- [ ] **Step 2: 改 `UploadDropzone.tsx` 加 tab**

完整重寫 `frontend/src/components/UploadDropzone.tsx`:
```tsx
import { useRef, useState } from "react";
import { UploadCloud, Loader2, Youtube } from "lucide-react";
import { isYoutubeUrl } from "../lib/youtubeUrl";

interface Props {
  onFile: (f: File) => Promise<void>;
  onYoutubeUrl?: (url: string) => Promise<void>;
  accept?: string;
  disabled?: boolean;
}

type Tab = "file" | "youtube";

export function UploadDropzone({
  onFile,
  onYoutubeUrl,
  accept = "audio/*,video/mp4,video/webm,video/quicktime",
  disabled,
}: Props) {
  const [tab, setTab] = useState<Tab>("file");
  const [busy, setBusy] = useState(false);

  return (
    <div className="border border-slate-200 rounded-lg overflow-hidden bg-white">
      <div className="flex border-b border-slate-200 bg-slate-50">
        <TabButton
          active={tab === "file"}
          onClick={() => setTab("file")}
          icon={<UploadCloud className="w-4 h-4" />}
          label="檔案上傳"
        />
        {onYoutubeUrl && (
          <TabButton
            active={tab === "youtube"}
            onClick={() => setTab("youtube")}
            icon={<Youtube className="w-4 h-4" />}
            label="YouTube URL"
          />
        )}
      </div>
      <div className="p-4">
        {tab === "file" ? (
          <FileDropzonePanel
            onFile={onFile}
            accept={accept}
            disabled={disabled}
            busy={busy}
            setBusy={setBusy}
          />
        ) : (
          <YoutubeUrlPanel
            onSubmit={onYoutubeUrl!}
            disabled={disabled}
            busy={busy}
            setBusy={setBusy}
          />
        )}
      </div>
    </div>
  );
}


function TabButton({
  active, onClick, icon, label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-2 px-4 py-2 text-sm cursor-pointer transition-colors duration-200 ${
        active
          ? "bg-white text-blue-600 border-b-2 border-blue-500"
          : "text-slate-600 hover:bg-slate-100"
      }`}
    >
      {icon} {label}
    </button>
  );
}


function FileDropzonePanel({
  onFile, accept, disabled, busy, setBusy,
}: {
  onFile: (f: File) => Promise<void>;
  accept: string;
  disabled: boolean | undefined;
  busy: boolean;
  setBusy: (b: boolean) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

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
        {busy ? "上傳中..." : "拖入音檔,或點擊選擇"}
      </p>
      <p className="text-xs text-slate-500">
        支援 wav / mp3 / m4a / mp4 / webm;上限 500 MB / 4 小時
      </p>
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


function YoutubeUrlPanel({
  onSubmit, disabled, busy, setBusy,
}: {
  onSubmit: (url: string) => Promise<void>;
  disabled: boolean | undefined;
  busy: boolean;
  setBusy: (b: boolean) => void;
}) {
  const [url, setUrl] = useState("");
  const valid = isYoutubeUrl(url);

  const submit = async () => {
    if (!valid || disabled || busy) return;
    setBusy(true);
    try { await onSubmit(url.trim()); setUrl(""); }
    finally { setBusy(false); }
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
          placeholder="https://www.youtube.com/watch?v=..."
          disabled={disabled || busy}
          className="flex-1 px-3 py-2 border border-slate-300 rounded text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-colors duration-200"
        />
        <button
          type="button"
          onClick={submit}
          disabled={!valid || disabled || busy}
          className="px-4 py-2 bg-blue-500 text-white text-sm rounded cursor-pointer hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-200"
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : "開始"}
        </button>
      </div>
      <div className="text-xs text-slate-500 space-y-1">
        <p>
          請確認影片授權狀態(本功能僅供內部研究 / dataset 製作使用)。
        </p>
        <p>
          不抓取 YouTube 自動生成字幕,僅抓人工上傳字幕。
        </p>
      </div>
      {url && !valid && (
        <p className="text-xs text-red-600">
          URL 格式不符,需為 youtube.com / youtu.be 連結。
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 3: 改 `pages/Offline.tsx` 接 onYoutubeUrl**

`frontend/src/pages/Offline.tsx` 在既有 `onUpload`(第 50-58 行)之後加:
```typescript
const onYoutubeUrl = async (url: string) => {
  try {
    await jobsApi.transcribeFromYoutube(url, projectId);
    toast.success("已啟動 YouTube 下載,完成後自動進入 ASR 排程");
    await fetchJobs();
  } catch {
    // client.ts 已 toast
  }
};
```

替換 `<UploadDropzone onFile={onUpload} />`(第 83 行)為:
```tsx
<UploadDropzone onFile={onUpload} onYoutubeUrl={onYoutubeUrl} />
```

- [ ] **Step 4: typecheck + lint**

```
cd frontend
npm run typecheck
```

```
cd frontend
npm run lint
```

Expected: 0 errors。

- [ ] **Step 5: Commit**

```
git add frontend/src/lib/youtubeUrl.ts frontend/src/components/UploadDropzone.tsx frontend/src/pages/Offline.tsx
git commit -m "feat(youtube): UploadDropzone 加 YouTube URL tab + Offline 頁串接"
```

---

## Task 8: Frontend subtitleDiff + editorStore + TranscriptEditor 對照模式

**Files:**
- Create: `frontend/src/lib/subtitleDiff.ts`
- Modify: `frontend/src/stores/editorStore.ts`(加 refSubs / diffMode)
- Modify: `frontend/src/components/TranscriptEditor.tsx`(加 toggle + 傳 refSubs)
- Modify: `frontend/src/components/SegmentListItem.tsx`(加 reference text 顯示)

### Steps

- [ ] **Step 1: 寫 `lib/subtitleDiff.ts`**

`frontend/src/lib/subtitleDiff.ts`:
```typescript
import type { Segment } from "../api/types";

export const SIMILARITY_THRESHOLD = 0.8;

export interface SubtitleMatch {
  text: string;
  similarity: number;
}

/**
 * 取時段交集內的所有 YT 字幕、拼接成單一文字。
 * 規則:任何跟 [start, end] 有交集的 ref segment 都納入。
 */
export function findSubtitleAtTime(
  refSubs: Segment[],
  start: number,
  end: number,
): string {
  const matched = refSubs.filter(
    (s) => s.start_time < end && s.end_time > start,
  );
  return matched.map((s) => s.text).join(" ").trim();
}

/**
 * Levenshtein distance / max(len(a), len(b)),回 similarity (1 - editDist/max)。
 * 對短字串(< 500 chars)效能足夠。空字串對任何 → 0(完全不同)、雙空 → 1。
 */
export function computeSimilarity(a: string, b: string): number {
  if (a === b) return 1;
  if (a.length === 0 || b.length === 0) return 0;

  const m = a.length;
  const n = b.length;
  const dp: number[] = Array(n + 1).fill(0);
  for (let j = 0; j <= n; j++) dp[j] = j;

  for (let i = 1; i <= m; i++) {
    let prev = dp[0];
    dp[0] = i;
    for (let j = 1; j <= n; j++) {
      const tmp = dp[j];
      if (a[i - 1] === b[j - 1]) {
        dp[j] = prev;
      } else {
        dp[j] = Math.min(prev, dp[j], dp[j - 1]) + 1;
      }
      prev = tmp;
    }
  }
  return 1 - dp[n] / Math.max(m, n);
}

export function matchSubtitle(
  refSubs: Segment[] | null,
  asrSegment: Segment,
): SubtitleMatch | null {
  if (refSubs === null || refSubs.length === 0) return null;
  const refText = findSubtitleAtTime(
    refSubs, asrSegment.start_time, asrSegment.end_time,
  );
  if (!refText) return null;
  return {
    text: refText,
    similarity: computeSimilarity(asrSegment.text, refText),
  };
}
```

- [ ] **Step 2: 改 `stores/editorStore.ts` 加 state**

`EditorState` interface(第 9-32 行)加:
```typescript
interface EditorState {
  // ...既有
  refSubs: Segment[] | null;
  refSubsLang: string | null;
  diffMode: boolean;
  setDiffMode: (on: boolean) => void;
}
```

`INITIAL_STATE`(第 34-44 行)加:
```typescript
const INITIAL_STATE = {
  // ...既有
  refSubs: null as Segment[] | null,
  refSubsLang: null as string | null,
  diffMode: false,
};
```

`init`(第 49-62 行)改:
```typescript
init: async (source) => {
  const loaded = await source.load();
  set({
    source,
    segments: loaded.segments,
    originalSnapshot: JSON.stringify(loaded.segments),
    activeIdx: 0,
    saving: false,
    lastSavedAt: null,
    audioUrl: loaded.audioUrl,
    durationSec: loaded.durationSec,
    title: loaded.title,
    refSubs: loaded.referenceSubtitles,
    refSubsLang: loaded.referenceSubtitleLang,
    diffMode: false,
  });
},
```

在 `setSaving` 之後(第 107 行)加 action:
```typescript
setDiffMode: (on) => set({ diffMode: on }),
```

- [ ] **Step 3: 改 `TranscriptEditor.tsx` 加 toggle**

`frontend/src/components/TranscriptEditor.tsx` 修改 `useEditorSelectors`(第 203-215 行)讓它額外回 `refSubs` / `diffMode`:
```typescript
function useEditorSelectors() {
  const segments = useEditorStore((s) => s.segments);
  const activeIdx = useEditorStore((s) => s.activeIdx);
  const saving = useEditorStore((s) => s.saving);
  const lastSavedAt = useEditorStore((s) => s.lastSavedAt);
  const isDirty = useEditorStore((s) => s.isDirty);
  const audioUrl = useEditorStore((s) => s.audioUrl);
  const title = useEditorStore((s) => s.title);
  const refSubs = useEditorStore((s) => s.refSubs);
  const refSubsLang = useEditorStore((s) => s.refSubsLang);
  const diffMode = useEditorStore((s) => s.diffMode);
  return {
    segments, activeIdx, saving, lastSavedAt, audioUrl, title,
    refSubs, refSubsLang, diffMode,
    dirty: isDirty(),
  };
}
```

`TranscriptEditor` 函式(第 25 行起)的 destructure 加 refSubs / refSubsLang / diffMode、`setDiffMode` 從 store action 取。

在 `<header>` block(第 83-98 行)的 `viewLink` 之前加 diff toggle:
```tsx
{refSubs && (
  <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
    <input
      type="checkbox"
      checked={diffMode}
      onChange={(e) => useEditorStore.getState().setDiffMode(e.target.checked)}
      className="cursor-pointer"
    />
    對照 YouTube 字幕
    {refSubsLang && (
      <span className="text-xs text-slate-400">({refSubsLang})</span>
    )}
  </label>
)}
```

`SegmentListItem` 呼叫(第 113-121 行)加 prop:
```tsx
<SegmentListItem
  key={i}
  segment={seg}
  active={i === activeIdx}
  dirty={isSegmentDirty(seg, originalSegments[i])}
  refSubs={diffMode ? refSubs : null}
  onClick={() => focusSegment(i)}
/>
```

- [ ] **Step 4: 改 `SegmentListItem.tsx` 顯示 reference + diff highlight**

完整重寫 `frontend/src/components/SegmentListItem.tsx`:
```tsx
import { useEffect, useRef } from "react";
import type { Segment } from "../api/types";
import { matchSubtitle, SIMILARITY_THRESHOLD } from "../lib/subtitleDiff";

interface Props {
  segment: Segment;
  active: boolean;
  dirty: boolean;
  refSubs?: Segment[] | null;
  onClick: () => void;
}

export function SegmentListItem({
  segment, active, dirty, refSubs, onClick,
}: Props) {
  const ref = useRef<HTMLButtonElement>(null);
  const match = refSubs ? matchSubtitle(refSubs, segment) : null;
  const isLowSim = match !== null && match.similarity < SIMILARITY_THRESHOLD;

  // active 變化時自動把這段 scroll 到 viewport 內,避免播放位移到視野外。
  // block: "nearest" 只在不可見時 scroll,不會無謂跳動已可見的項目。
  useEffect(() => {
    if (active) {
      ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [active]);

  return (
    <button
      ref={ref}
      type="button"
      onClick={onClick}
      className={`w-full text-left px-3 py-2 border-b border-slate-100 cursor-pointer transition-colors duration-200 ${
        active
          ? "bg-blue-50 border-l-2 border-l-blue-500 pl-2.5"
          : isLowSim
          ? "border-l-2 border-l-red-400 pl-2.5 hover:bg-slate-50"
          : "hover:bg-slate-50"
      }`}
    >
      <div className="flex items-center gap-2 text-xs text-slate-500 font-mono mb-0.5">
        <span>{segment.start_time.toFixed(2)}</span>
        <span>·</span>
        <span>Sp{segment.speaker_id}</span>
        {dirty && (
          <span
            className="ml-auto w-1.5 h-1.5 rounded-full bg-amber-500"
            aria-label="未儲存"
          />
        )}
      </div>
      <div className="text-sm text-slate-900 line-clamp-2">{segment.text}</div>
      {match && (
        <div className="mt-1 text-xs italic text-slate-400 line-clamp-2">
          YT: {match.text}
          <span
            className={`ml-2 not-italic ${
              isLowSim ? "text-red-600" : "text-slate-400"
            }`}
          >
            ({(match.similarity * 100).toFixed(0)}%)
          </span>
        </div>
      )}
    </button>
  );
}
```

設計說明:
- `isLowSim` 為 true 時根 container 用紅色左邊框(`border-l-red-400`),但 active 時讓 blue 邊框優先(active > isLowSim 視覺優先序)。
- match 一定顯示(不只 lowSim 才顯示),讓校正員看到完整對照;相似度數字本身依 lowSim 改色。
- `line-clamp-2` 限制 YT 字幕顯示 2 行,避免長字幕擠掉版面。

- [ ] **Step 5: typecheck + lint**

```
cd frontend
npm run typecheck
```

```
cd frontend
npm run lint
```

Expected: 0 errors。

- [ ] **Step 6: Commit**

```
git add frontend/src/lib/subtitleDiff.ts frontend/src/stores/editorStore.ts frontend/src/components/TranscriptEditor.tsx frontend/src/components/SegmentListItem.tsx
git commit -m "feat(editor): YouTube 字幕對照模式 + Levenshtein 80% 閾值 diff highlight"
```

---

## 完成後驗證(全部 task 跑完)

### Backend

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

Expected:
- pytest:既有 229+ + 新增 19 個全綠
- ruff / mypy / bandit:0 errors / 0 high

### Frontend

```
cd frontend
npm run typecheck
```

```
cd frontend
npm run lint
```

```
cd frontend
npm run build
```

Expected:
- typecheck:0 errors
- lint:0 errors
- build:成功產 `dist/`

### 實機驗收(需 Linux + GPU 環境 + vllm)

1. 在 admin UI 進入「離線轉錄」頁、切「YouTube URL」tab
2. 貼上一支授權影片(短片、< 2 min,有人工字幕)
3. 點「開始」、確認 toast「已啟動 YouTube 下載」
4. JobList 出現新 Job、status 從 `queued`(youtube_fetch_job)→ `running`(transcribe)→ `done`
5. 點進 Job 進 Editor
6. 標頭右上應該出現「對照 YouTube 字幕 (zh-Hant)」checkbox
7. 勾選後 SegmentListItem 下方顯示 YT 字幕灰字
8. 差異大的段(< 80% 相似度)左邊框標紅、相似度數字顯示

---

## Risks / Common Pitfalls

| 風險 | 偵測 | 處理 |
|---|---|---|
| yt-dlp Docker image 內版本太舊、被 YouTube 反爬 | probe / fetch 持續失敗 | `docker compose build backend --no-cache` 強制拉最新 yt-dlp |
| `parse_vtt` 對非標準 VTT(cue settings / styling)壞掉 | test_subtitle_parser fail | parser 已 strip inline tags;edge case 加 test 補 |
| `youtube_fetch_job` 過長(影片下載慢)、worker timeout | worker log 看 5min timeout | 短影片(<10min)應在 1min 內完成、調 FETCH_TIMEOUT_SEC 才行不通 |
| frontend tab UI 在 viewport < 768px 擠壓 | 手機開 admin | 既有 admin 是 desktop-first、本次不處理 mobile |
| 字幕跟 ASR 時間軸偏差大、diff 全部紅 | 校正員回報 | findSubtitleAtTime 用「時段交集」、不要求完全對齊;若仍偏差檢查字幕本身時間軸 |
| OpenCC 容器未裝、normalize 沒效果 | parser.py 模組載入 warning | M3 已裝、retry build image |

---

## Out of Scope(本 plan 不做)

- Playlist / channel 批次匯入
- YouTube 自動生成字幕
- 多語字幕同時保留
- 字幕直接當 dataset label(不跑 ASR)
- v1 API 對外 YouTube 端點

---

## Plan Self-Review Checklist

執行 plan 前自我檢查:

- [x] 所有 task 都有具體 file path + 行號 / 函式範圍
- [x] 每個 step 含完整 code(不放 placeholder「TODO」「TBD」)
- [x] 每個 task 結尾有 commit + 訊息範例
- [x] 測試先寫(RED)、跑驗 fail、再寫 impl、跑驗 pass
- [x] task 之間有明確依賴順序(`Task 切分總覽` 列出)
- [x] 完成條件對應 spec §13(Done Criteria)
- [x] 沒列 spec out-of-scope 範圍的東西
- [x] 命名一致(referenceSubtitles 前後不亂用 reference_subtitles / refSubs 等變體 — TS 用 camelCase、Python 用 snake_case)
