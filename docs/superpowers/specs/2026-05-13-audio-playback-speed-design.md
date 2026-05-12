# Audio Playback Speed 調整設計

> **For agentic workers:** REQUIRED SUB-SKILL: 後續用 `superpowers:writing-plans` 寫 plan、再用 `superpowers:subagent-driven-development` 派 subagent 執行。

**目標:** Project 加 `playback_speed` 設定(預設 1.0),ASR 推論前用 ffmpeg `atempo` filter 調整音檔速度,對齊「客服快語速」場景。Segments 時間戳推論後 scale 回原 timeline,user 在 editor 看到的時間軸跟原檔對齊。

**架構:** `audio_preprocessor.py` 加 `maybe_adjust_speed`,在 `maybe_denoise` 之後 / splitter 之前跑。`job_runner.run_transcribe` 串接,推論完 segments scale 還原。Dataset source 用原檔(不變,跟 denoise 同設計)。

**Tech Stack:** ffmpeg(已有,`atempo` filter)+ numpy(scale 用)。**無新依賴**。

---

## 1. 動機

QC 客服音檔語速快(約 1.5× 正常),vLLM 對快語音辨識率低。把音檔拉長到正常語速、推論完再 scale 時間戳回原 timeline,辨識精度提升、user 看 editor 仍跟原檔對齊。

跟 denoise 設計同模式(原檔保留、temp file 推論用),不影響 dataset 訓練料(原檔)。

---

## 2. 範圍

### 2.1 In scope

- `Project` 加 `playback_speed: float`(預設 1.0、range 0.5-2.0)
- `ProjectIn / ProjectPatch / ProjectOut` 加欄位 + pydantic validator
- Alembic migration `0006_project_playback_speed`
- `audio_preprocessor.maybe_adjust_speed` 新 helper
- `job_runner.run_transcribe` 整合(`maybe_denoise → maybe_adjust_speed → splitter`)
- 推論完 segments 時間戳 scale 回原 timeline
- Temp file cleanup(try/finally、同 denoise 模式)
- Frontend `ProjectFormModal` 加數字輸入
- Frontend `types.ts` ProjectOut 加欄位

### 2.2 Out of scope

- 動態語速偵測(SNR / 語速分析自動決定 speed)
- Per-job override(走 Project 統一設定、跟 denoise 同模式)
- pitch correction(`atempo` 已內建只改時間不改 pitch、不需要額外處理)
- 影片速度同時調整(我們 audio-only)
- v1 API metadata override

---

## 3. 決定(已 user 確認)

| # | 議題 | 決定 |
|---|---|---|
| 1 | 欄位名稱 / 概念 | A:`playback_speed`(跟 ffmpeg / VLC 一致:1.0=原速、< 1=慢、> 1=快)|
| 2 | 預設值 | 1.0(不變) |
| 3 | UI 範圍 | 0.5-2.0(ffmpeg `atempo` 單次限制) |
| 4 | 跟 denoise 順序 | 先 denoise、後 speed(noisereduce 在原速 audio 上算 noise profile 較準) |
| 5 | 設定位置 | Project 層 |

---

## 4. Data Model

### 4.1 `backend/app/models.py`

`Project` class 內 `denoise_enabled` 之後加:

```python
    playback_speed: Mapped[float] = mapped_column(
        Float, default=1.0, nullable=False, server_default=text("1.0"),
    )
```

### 4.2 Alembic migration `0006_project_playback_speed.py`

```python
"""project_playback_speed

Project 加 playback_speed (float, 預設 1.0)。
ASR 推論前用 ffmpeg atempo 調速,推論完 segments 時間戳 scale 回原 timeline。

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "playback_speed",
            sa.Float(),
            server_default=sa.text("1.0"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("playback_speed")
```

### 4.3 `schemas.py`

```python
class ProjectIn(BaseModel):
    # ...既有
    playback_speed: float = Field(default=1.0, ge=0.5, le=2.0)

class ProjectPatch(BaseModel):
    # ...既有
    playback_speed: float | None = Field(default=None, ge=0.5, le=2.0)

class ProjectOut(BaseModel):
    # ...既有
    playback_speed: float
```

不需要 field_validator(`Field(ge=, le=)` 已 enforce)。

### 4.4 Frontend types

```typescript
export interface ProjectOut {
  // ...既有
  playback_speed: number;
}

export interface ProjectIn { /* 同上 optional */ }
export interface ProjectPatch { /* 同上 optional */ }
```

---

## 5. Service Layer

### 5.1 `audio_preprocessor.py` 加 `maybe_adjust_speed`

```python
def maybe_adjust_speed(
    input_path: Path,
    *,
    playback_speed: float,
) -> tuple[Path, bool]:
    """若 playback_speed != 1.0,ffmpeg atempo 調速 → temp mp3 → 回 (新 path, True)。

    Disabled(1.0)時直接回 (input_path, False)。Caller 負責 cleanup temp file。

    ffmpeg atempo filter 只改時間不改 pitch,範圍 0.5-2.0(單次)。
    """
    # 用 math.isclose 對齊浮點比較(1.0001 等微差也視為 no-op)
    if math.isclose(playback_speed, 1.0, abs_tol=1e-3):
        return input_path, False

    if not (0.5 <= playback_speed <= 2.0):
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            f"playback_speed {playback_speed} out of range [0.5, 2.0]",
        )

    settings = get_settings()
    fd, temp_str = tempfile.mkstemp(
        suffix=".mp3", prefix="speed_", dir=str(settings.upload_dir),
    )
    os.close(fd)
    temp_path = Path(temp_str)

    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(input_path),
        "-filter:a", f"atempo={playback_speed}",
        "-vn", "-c:a", "libmp3lame", "-q:a", str(ASR_AUDIO_MP3_QUALITY),
        str(temp_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=600)
    except subprocess.CalledProcessError as e:
        temp_path.unlink(missing_ok=True)
        stderr = e.stderr.decode("utf-8", errors="replace")[-500:] if e.stderr else ""
        raise AppError(
            ErrorCode.AUDIO_UNREADABLE,
            f"ffmpeg atempo failed: {stderr}",
        ) from e

    logger.info(
        "speed: adjusted %s → %s @ %s×",
        input_path.name, temp_path.name, playback_speed,
    )
    return temp_path, True


def cleanup_adjusted_speed(temp_path: Path) -> None:
    """跟 cleanup_denoised 同邏輯。"""
    try:
        if temp_path.exists():
            temp_path.unlink()
    except OSError as e:
        logger.warning("cleanup speed temp file failed: %s (%s)", temp_path, e)
```

### 5.2 `job_runner.run_transcribe` 整合

```python
async def run_transcribe(job_id: str) -> None:
    state = await _begin_running(job_id)
    if state is None:
        return

    # Stage 1: maybe denoise
    asr_audio_path, was_denoised = maybe_denoise(
        Path(state["audio_path"]),
        denoise_enabled=state["denoise_enabled"],
    )
    state["audio_path"] = str(asr_audio_path)

    # Stage 2: maybe adjust speed
    speed_adjusted_path, was_speed_adjusted = maybe_adjust_speed(
        Path(state["audio_path"]),
        playback_speed=state["playback_speed"],
    )
    state["audio_path"] = str(speed_adjusted_path)

    try:
        outcome = await _do_transcribe(get_settings(), state)
        # Scale segment timestamps back to original timeline
        if state["playback_speed"] != 1.0:
            outcome["segments"] = _scale_segments(
                outcome["segments"], state["playback_speed"],
            )
        await _persist_success(job_id, state, outcome)
        # ...既有 log
    except AppError as e:
        # ...
    except Exception as e:
        # ...
    finally:
        if was_speed_adjusted:
            cleanup_adjusted_speed(speed_adjusted_path)
        if was_denoised:
            cleanup_denoised(asr_audio_path)


def _scale_segments(segments: list[dict], playback_speed: float) -> list[dict]:
    """Scale segment timestamps × playback_speed 回原 timeline。

    playback_speed=0.7 → audio 變慢 1/0.7 倍長 → segments 時間戳在「慢速版」timeline
    × 0.7 = 回原 timeline。
    """
    out = []
    for s in segments:
        out.append({
            **s,
            "start_time": round(s["start_time"] * playback_speed, 3),
            "end_time": round(s["end_time"] * playback_speed, 3),
        })
    return out
```

`_begin_running` 加 `state["playback_speed"]`:

```python
state["playback_speed"] = project.playback_speed if project else 1.0
```

### 5.3 為什麼 scale 公式是 `× playback_speed`

```
playback_speed = 0.7(慢)
原音檔 92s @ 1.0×
atempo=0.7 → 慢速版 92/0.7 ≈ 131.4s @ 1.0×(但時間軸拉長 1/0.7)
vLLM 看 131.4s 慢速版、segment 時間戳在 [0, 131.4]
要回原 [0, 92] → × 0.7 = ×playback_speed ✓
```

```
playback_speed = 1.5(快)
原音檔 92s
atempo=1.5 → 快速版 92/1.5 ≈ 61.3s
vLLM 看 61.3s、segment 時間戳在 [0, 61.3]
要回原 [0, 92] → × 1.5 = ×playback_speed ✓
```

公式一致:`new_time = old_time * playback_speed`。

---

## 6. Frontend `ProjectFormModal`

zod schema:
```typescript
playback_speed: z.number().min(0.5).max(2.0).optional(),
```

reset() initial:
```typescript
playback_speed: initial?.playback_speed ?? 1.0,
```

submit values 帶 `playback_speed`。

UI(放在 denoise 區塊之後):
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

---

## 7. 測試

### 7.1 Backend

- `test_audio_preprocessor.py` 加:
  - `test_maybe_adjust_speed_noop_when_1_0`(speed=1.0、return 原 path、was=False)
  - `test_maybe_adjust_speed_writes_temp`(speed=0.7、mock ffmpeg、return temp path、was=True)
  - `test_maybe_adjust_speed_out_of_range`(speed=3.0、AppError)
  - `test_cleanup_adjusted_speed`(刪 temp、missing 安全)
- `test_routes_projects.py` 加:
  - `test_create_project_with_playback_speed`(POST 帶 0.7、assert 0.7)
  - `test_create_project_default_speed`(無 speed、assert 1.0)
  - `test_create_project_speed_out_of_range`(3.0 → 422)
- `test_job_runner_speed.py` 新:
  - mock maybe_adjust_speed → 驗 cleanup 順序
  - 驗 segments × playback_speed scale 結果

### 7.2 Frontend

- typecheck + lint PASS

---

## 8. 邊界 case

| 情境 | 處理 |
|---|---|
| playback_speed=1.0 | maybe_adjust_speed return no-op、不寫 temp |
| playback_speed=1.000001 浮點 | `math.isclose(abs_tol=1e-3)` 視為 no-op |
| playback_speed 超出 0.5-2.0 | Pydantic Field validator 擋(API 422),內層 service 也防禦性檢查 |
| 短音檔(< 5s)atempo 效果 | 接受、效果可能有限 |
| denoise + speed 同時開 | Stage 順序:先 denoise 再 speed,兩個 temp file 都 cleanup |
| 推論失敗、cleanup 順序 | finally 先 cleanup speed temp、再 cleanup denoise temp(後寫的先刪) |

---

## 9. 完成條件

- [ ] `Project` 加 `playback_speed` 欄位 + migration 0006
- [ ] `ProjectIn / ProjectPatch / ProjectOut` schema 加欄位 + Field(ge=0.5, le=2.0)
- [ ] `audio_preprocessor.maybe_adjust_speed` + `cleanup_adjusted_speed` 實作
- [ ] `job_runner.run_transcribe` 整合(denoise → speed → splitter)
- [ ] `job_runner._scale_segments` 實作 + 推論完 scale 邏輯
- [ ] `_begin_running` state dict 加 `playback_speed`
- [ ] Frontend types 加欄位
- [ ] `ProjectFormModal` 加數字輸入
- [ ] Backend tests 全綠
- [ ] Frontend typecheck / lint 0 errors
- [ ] 實機:客服音檔設 0.7、worker log 印 `speed: adjusted ...`、ASR 完成、editor 時間軸跟原檔對齊

---

## 10. 不變條件(Non-Goals)

- `Job.audio_path` 仍指原檔(dataset source 安全)
- v1 API metadata override 不做
- pitch correction 不做(atempo 內建)
- 自動偵測語速不做
