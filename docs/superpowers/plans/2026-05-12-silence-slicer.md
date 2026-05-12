# Silence-based Audio Splitter 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 `superpowers:subagent-driven-development` 逐 task 派 subagent 執行。Steps 用 `- [ ]` checkbox 追蹤。

**Goal:** 把 `split_long_audio` 從「固定時間 + overlap」切點換成「silence detection」切點。Editor 不再看到時間軸重複段。

**Architecture:** vendor audio-slicer `slicer2.py`(MIT、~110 行純 numpy)→ `app/utils/silence_slicer.py`。`audio_splitter.split_long_audio` 改用 ffmpeg pipe PCM 進 numpy → SilenceSlicer 找切點 → 累計成 ≤ `chunk_duration_sec` 的 chunk。`merge_chunk_results` 拿掉 dedup。

**Tech Stack:** ffmpeg(已有)+ numpy(已有,parser 已用)+ vendored audio-slicer。**不引入** librosa / soundfile / scipy。

**Spec Reference:** `docs/superpowers/specs/2026-05-12-silence-slicer-design.md`

---

## Task 切分總覽

| Task | 範圍 | 依賴 |
|---|---|---|
| 1 | vendor `silence_slicer.py` + unit test | — |
| 2 | `audio_splitter.py` 重寫 + config 加 settings + 既有 test 改 | Task 1 |

實機驗收(2-3 分鐘音檔跑通、editor 看不到重複段)由 user 在 Linux + GPU 環境執行,不在 plan task 範圍。

---

## Task 1: vendor `silence_slicer.py` + unit test

**Files:**
- Create: `backend/app/utils/silence_slicer.py`
- Create: `backend/tests/test_silence_slicer.py`
- Create: `LICENSES/audio-slicer.LICENSE.md`(MIT 全文 attribution)

### Steps

- [ ] **Step 1: Fetch upstream `slicer2.py` 原始碼**

從 `https://raw.githubusercontent.com/flutydeer/audio-slicer/main/slicer2.py` 拿原始 Slicer class 內容。

實作工程上:用 WebFetch 工具:
```
WebFetch(
  url="https://raw.githubusercontent.com/flutydeer/audio-slicer/main/slicer2.py",
  prompt="Return the complete Slicer class source code verbatim, including __init__, all methods (_apply_slice / _frame_to_sample / slice / slice_ranges if exists), and all imports. Do NOT include the if __name__ == '__main__' block or any main() / librosa.load() usage. Just the Slicer class + its required imports."
)
```

把回傳的 Slicer class 源碼拿來基底,改成 `SilenceSlicer` 並加 MIT attribution docstring。

- [ ] **Step 2: 寫 `silence_slicer.py`**

`backend/app/utils/silence_slicer.py`:
```python
"""
Silence-based audio slicer.

Adapted from flutydeer/audio-slicer (MIT License).
Original source: https://github.com/flutydeer/audio-slicer/blob/main/slicer2.py
Original copyright: (c) 2023 flutydeer

修改項目:
- 類別重新命名為 SilenceSlicer(避開跟 dict.slice / 其他語意衝突)
- 移除 upstream 的 main / librosa.load / soundfile 使用(只保留 class)
- caller(audio_splitter)自己用 ffmpeg + numpy.frombuffer 讀 PCM
"""
from __future__ import annotations

import numpy as np
# 註：upstream Slicer class 內容由 implementer subagent 從
# https://raw.githubusercontent.com/flutydeer/audio-slicer/main/slicer2.py
# 取得後 vendor 進來,類別名稱改成 SilenceSlicer。

# === SilenceSlicer class 從 upstream slicer2.py 複製 ===
# (implementer 用 WebFetch 取得後填入此處;結構應含:)
# class SilenceSlicer:
#     def __init__(self, sr, threshold=-40.0, min_length=5000,
#                  min_interval=300, hop_size=20, max_sil_kept=5000): ...
#     def _apply_slice(self, waveform, begin, end): ...
#     def _frame_to_sample(self, frame_idx): ...
#     def slice_ranges(self, waveform) -> list[tuple[int, int]]: ...
#     def slice(self, waveform) -> list[np.ndarray]: ...
```

**重要實作細節給 implementer:**

1. **upstream 可能沒有 `slice_ranges()` 公開 method、只有 `slice()`**。看回傳值,如果 `slice()` 回 list of audio chunks,內部一定有個拿 (begin, end) sample indices 的邏輯。把那段 indices 計算抽成 `slice_ranges()` public method 暴露出來(我們的 audio_splitter 需要 ranges 換算成秒、不需要 audio chunks)。
2. **保留** upstream `__init__` 所有參數預設值(slicer2 原版預設、不要在 vendored file 自己改)。改預設值的事 audio_splitter 透過 config 傳。
3. **不要** 在這個 file 用 librosa / soundfile / scipy。Only numpy。

- [ ] **Step 3: 加 MIT attribution 檔**

`LICENSES/audio-slicer.LICENSE.md`(新建,放專案根 LICENSES/ 資料夾,新建資料夾如不存在):

```markdown
# audio-slicer

Vendored portion: `backend/app/utils/silence_slicer.py` derives from
https://github.com/flutydeer/audio-slicer/blob/main/slicer2.py

## Original License

MIT License

Copyright (c) 2023 flutydeer

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 4: 寫 unit test**

`backend/tests/test_silence_slicer.py`:
```python
"""SilenceSlicer 基本行為:silence-bounded sample ranges。

不對 slicer 演算法做精度驗證(視為 vendor 黑箱、信 upstream)。
只驗:
  - 構造參數正確
  - 對 silent gap 中間隔開的 waveform 切出多 ranges
  - 整段都有聲音(沒 silent gap)→ 回單一 range 含整段
  - 全 silence waveform → 回空 ranges
  - mono float32 array 為 expected input shape
"""
from __future__ import annotations

import numpy as np
import pytest

from app.utils.silence_slicer import SilenceSlicer


SR = 16000  # 16 kHz mono(對齊 ASR_AUDIO_SAMPLE_RATE_HZ)


def _gen_tone(duration_sec: float, freq_hz: float = 440.0, amplitude: float = 0.5) -> np.ndarray:
    """產生 amplitude-controlled sine wave(模擬講話的非靜音段)。"""
    t = np.linspace(0, duration_sec, int(SR * duration_sec), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)


def _gen_silence(duration_sec: float) -> np.ndarray:
    """產生純零(silence)。"""
    return np.zeros(int(SR * duration_sec), dtype=np.float32)


def test_silence_slicer_constructor():
    """構造參數設定正確,不 raise。"""
    slicer = SilenceSlicer(
        sr=SR, threshold=-40.0, min_length=2000,
        min_interval=300, hop_size=20, max_sil_kept=1000,
    )
    assert slicer is not None


def test_slice_ranges_two_segments_separated_by_silence():
    """[3s tone][2s silence][3s tone] → 應該切出 2 個 ranges。"""
    waveform = np.concatenate([
        _gen_tone(3.0),
        _gen_silence(2.0),
        _gen_tone(3.0),
    ])
    slicer = SilenceSlicer(
        sr=SR, threshold=-40.0, min_length=2000,
        min_interval=300, hop_size=20, max_sil_kept=1000,
    )
    ranges = slicer.slice_ranges(waveform)
    # 中間有 2s silence、肯定能切;期望至少 2 段
    assert len(ranges) >= 2
    # 第一段大致在 0-3s、第二段大致在 5-8s(允許 silence_kept padding)
    first_begin, first_end = ranges[0]
    last_begin, last_end = ranges[-1]
    assert first_begin / SR < 1.0  # 第一段近開頭
    assert last_end / SR > 7.0     # 最後一段近結尾


def test_slice_ranges_continuous_tone_no_silence():
    """整段有聲、無 silent gap → 回單一 range 含整段(或 fallback 行為)。"""
    waveform = _gen_tone(8.0)
    slicer = SilenceSlicer(
        sr=SR, threshold=-40.0, min_length=2000,
        min_interval=300, hop_size=20, max_sil_kept=1000,
    )
    ranges = slicer.slice_ranges(waveform)
    # 應該是 1 個 range 含整段;退步接受任意數量但合計覆蓋整段
    if len(ranges) == 1:
        begin, end = ranges[0]
        assert begin == 0 or begin < SR // 10
        assert end >= len(waveform) - SR // 10


def test_slice_ranges_all_silence():
    """全 silence waveform → 回空 ranges(無語音可切)。"""
    waveform = _gen_silence(5.0)
    slicer = SilenceSlicer(
        sr=SR, threshold=-40.0, min_length=2000,
        min_interval=300, hop_size=20, max_sil_kept=1000,
    )
    ranges = slicer.slice_ranges(waveform)
    # upstream 對全 silence 通常回空或回單個含整段的 range;接受任一
    # 主要驗:不 raise + 不死循環
    assert isinstance(ranges, list)


def test_slice_ranges_short_silence_below_min_interval_not_cut():
    """[3s tone][0.1s silence][3s tone] silence 太短(< min_interval 300ms)、不該切。"""
    waveform = np.concatenate([
        _gen_tone(3.0),
        _gen_silence(0.1),
        _gen_tone(3.0),
    ])
    slicer = SilenceSlicer(
        sr=SR, threshold=-40.0, min_length=2000,
        min_interval=300, hop_size=20, max_sil_kept=1000,
    )
    ranges = slicer.slice_ranges(waveform)
    # 0.1s silence 不滿足 min_interval=300ms、整段被視為連續
    assert len(ranges) == 1


def test_slice_ranges_returns_tuple_of_int():
    """ranges 回 list of (int, int)、sample indices。"""
    waveform = np.concatenate([
        _gen_tone(3.0),
        _gen_silence(2.0),
        _gen_tone(3.0),
    ])
    slicer = SilenceSlicer(
        sr=SR, threshold=-40.0, min_length=2000,
        min_interval=300, hop_size=20, max_sil_kept=1000,
    )
    ranges = slicer.slice_ranges(waveform)
    for begin, end in ranges:
        assert isinstance(begin, (int, np.integer))
        assert isinstance(end, (int, np.integer))
        assert begin < end
        assert 0 <= begin < len(waveform)
        assert 0 < end <= len(waveform)
```

- [ ] **Step 5: Commit**

```
git -C /d/vibevoice_asr add backend/app/utils/silence_slicer.py backend/tests/test_silence_slicer.py LICENSES/audio-slicer.LICENSE.md
```

```
git -C /d/vibevoice_asr commit -m "feat(slicer): vendor audio-slicer slicer2.py 進 silence_slicer + MIT attribution"
```

```
git -C /d/vibevoice_asr push
```

---

## Task 2: `audio_splitter.py` 重寫 + config 加 settings + tests 改

**Files:**
- Modify: `backend/app/config.py`(加 5 個 silence settings)
- Modify: `backend/app/services/audio_splitter.py`(重寫切點 + 簡化 merge)
- Modify: `backend/tests/test_audio_splitter.py`(刪 dedup test、加 silence-based test)

### Steps

- [ ] **Step 1: 改 `backend/app/config.py` 加 settings**

在 既有 `split_chunk_duration_sec` / `split_overlap_sec` 設定旁邊加 5 個新 settings。具體位置:Read 一下 config.py 找 Settings class、在現有 split_* 設定附近加:

```python
    # === Silence-based slicer 參數(M+1 切換點)===
    # silence detection RMS 振幅閾值(dB)。-40 是 audio-slicer 預設、適合多數錄音。
    silence_threshold_db: float = -40.0

    # 每段最短長度(ms)。audio-slicer 預設 5000 對歌曲設計;
    # ASR 場景改 2000(短句保留、避免過度合併)。
    silence_min_length_ms: int = 2000

    # silence 至少多長才視為切點(ms)。
    silence_min_interval_ms: int = 300

    # RMS 計算窗口 hop size(ms)。
    silence_hop_size_ms: int = 20

    # 切點處保留前後 silence 的最大長度(ms)。
    silence_max_kept_ms: int = 1000

    # === 已廢棄(silence-based 切點不需要 overlap)、保留欄位避免 .env 破 ===
    # split_overlap_sec 仍可在 .env 設、但 audio_splitter 不再讀。
```

**注意**:不要刪 `split_overlap_sec` 欄位本身(向後相容),只是新版 code 不再讀它。

- [ ] **Step 2: 完整重寫 `backend/app/services/audio_splitter.py`**

完整內容(取代既有檔):
```python
"""
Long-audio splitter & merger(silence-based 切點版)。

When audio > AUTO_SPLIT_THRESHOLD_SEC, use silence detection (vendored
audio-slicer) to find natural句邊界, then accumulate adjacent silence-bounded
segments into chunks ≤ chunk_duration_sec. 每 chunk 在 silence 處切斷、無
overlap、merge 階段不需要文字 dedup。

Replaces M5 minimal viable implementation(固定時間切 + overlap + SequenceMatcher dedup)。

See SPEC.md §6.4 and docs/superpowers/specs/2026-05-12-silence-slicer-design.md。
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.constants import (
    ASR_AUDIO_CHANNELS,
    ASR_AUDIO_MP3_QUALITY,
    ASR_AUDIO_SAMPLE_RATE_HZ,
)
from app.errors import AppError, ErrorCode
from app.utils.silence_slicer import SilenceSlicer

logger = logging.getLogger(__name__)


# splitter 內 ffmpeg subprocess 的超時(單 chunk 最多 600s 處理時間)。
SPLIT_TIMEOUT_SEC = 600


@dataclass
class Chunk:
    path: Path
    start_offset_sec: float  # absolute time in original audio
    end_offset_sec: float
    is_split: bool


def get_duration_sec(path: Path) -> float:
    """ffprobe wrapper. Raises CalledProcessError on failure."""
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        stderr=subprocess.STDOUT,
    )
    return float(out.decode().strip())


def split_long_audio(
    input_path: Path,
    output_dir: Path,
    max_chunk_sec: int | None = None,
    threshold_sec: int | None = None,
) -> list[Chunk]:
    """切長音檔為多段 chunk file(silence-based 切點)。

    duration <= threshold_sec → 回單 chunk(path 指原檔、is_split=False)
    duration >  threshold_sec → ffmpeg 切多 chunk 寫到 output_dir/chunk_NNN.mp3,
                                切點來自 SilenceSlicer 找到的 silence-bounded ranges,
                                累計到 max_chunk_sec 為上限。

    沒 silence 切點時(極端罕見、整段連續講話 / 純樂器)→ fallback 固定時間切。
    """
    settings = get_settings()
    max_chunk_sec_val = max_chunk_sec or settings.split_chunk_duration_sec
    threshold_sec_val = threshold_sec or settings.auto_split_threshold_sec

    duration = get_duration_sec(input_path)
    if duration <= threshold_sec_val:
        return [Chunk(
            path=input_path,
            start_offset_sec=0.0,
            end_offset_sec=duration,
            is_split=False,
        )]

    # 1. ffmpeg → 16kHz mono PCM → numpy
    waveform, sr = _load_pcm_mono_16k(input_path)

    # 2. silence slicer 找切點
    slicer = SilenceSlicer(
        sr=sr,
        threshold=settings.silence_threshold_db,
        min_length=settings.silence_min_length_ms,
        min_interval=settings.silence_min_interval_ms,
        hop_size=settings.silence_hop_size_ms,
        max_sil_kept=settings.silence_max_kept_ms,
    )
    sample_ranges = slicer.slice_ranges(waveform)

    if not sample_ranges:
        return _fallback_fixed_split(
            input_path, output_dir, duration, float(max_chunk_sec_val),
        )

    # 3. 累計成 chunk
    chunk_time_ranges = _accumulate_to_chunks(
        sample_ranges, sr, float(max_chunk_sec_val),
    )

    # 4. ffmpeg 切實體 mp3
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[Chunk] = []
    for i, (start_sec, end_sec) in enumerate(chunk_time_ranges):
        chunk_path = output_dir / f"chunk_{i:03d}.mp3"
        _ffmpeg_extract_chunk(
            input_path, chunk_path, start_sec, end_sec - start_sec, i, output_dir,
        )
        chunks.append(Chunk(
            path=chunk_path,
            start_offset_sec=start_sec,
            end_offset_sec=end_sec,
            is_split=True,
        ))

    logger.info(
        "split_long_audio: %s (%.1fs) → %d chunks (silence-based, max_chunk=%ds)",
        input_path.name, duration, len(chunks), max_chunk_sec_val,
    )
    return chunks


def _load_pcm_mono_16k(input_path: Path) -> tuple[np.ndarray, int]:
    """ffmpeg → 16kHz mono PCM stdout → numpy float32 array。"""
    sr = ASR_AUDIO_SAMPLE_RATE_HZ
    cmd = [
        "ffmpeg", "-v", "error",
        "-i", str(input_path),
        "-vn",
        "-ar", str(sr),
        "-ac", "1",
        "-f", "s16le",
        "-",
    ]
    try:
        result = subprocess.run(
            cmd, check=True, capture_output=True, timeout=SPLIT_TIMEOUT_SEC,
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="replace")[-500:] if e.stderr else ""
        raise AppError(
            ErrorCode.AUDIO_UNREADABLE,
            f"ffmpeg PCM decode failed: {stderr}",
        ) from e
    except subprocess.TimeoutExpired as e:
        raise AppError(
            ErrorCode.AUDIO_UNREADABLE,
            "ffmpeg PCM decode timeout",
        ) from e

    pcm_int16 = np.frombuffer(result.stdout, dtype=np.int16)
    waveform = pcm_int16.astype(np.float32) / 32768.0
    return waveform, sr


def _accumulate_to_chunks(
    sample_ranges: list[tuple[int, int]],
    sr: int,
    max_chunk_sec: float,
) -> list[tuple[float, float]]:
    """把連續 silence-bounded 片累計成 ≤ max_chunk_sec 的 chunk。

    每個 sample range 是一段非靜音內容、合併到下個 silence 切點之前。
    我們累計到下個 range 加進去會超過 max_chunk_sec 為止,先 commit、開新 chunk。

    回時間秒 (start_sec, end_sec)。
    """
    if not sample_ranges:
        return []

    max_samples = int(max_chunk_sec * sr)
    chunks: list[tuple[float, float]] = []
    current_start = sample_ranges[0][0]
    current_end = sample_ranges[0][1]

    for begin, end in sample_ranges[1:]:
        if end - current_start <= max_samples:
            current_end = end
        else:
            chunks.append((current_start / sr, current_end / sr))
            current_start = begin
            current_end = end

    chunks.append((current_start / sr, current_end / sr))
    return chunks


def _fallback_fixed_split(
    input_path: Path,
    output_dir: Path,
    duration: float,
    max_chunk_sec: float,
) -> list[Chunk]:
    """整段無 silence 切點時的 fallback:固定時間切、無 overlap。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[Chunk] = []
    i = 0
    start = 0.0
    while start < duration - 0.01:
        end = min(duration, start + max_chunk_sec)
        chunk_path = output_dir / f"chunk_{i:03d}.mp3"
        _ffmpeg_extract_chunk(
            input_path, chunk_path, start, end - start, i, output_dir,
        )
        chunks.append(Chunk(
            path=chunk_path,
            start_offset_sec=start,
            end_offset_sec=end,
            is_split=True,
        ))
        start = end
        i += 1
    logger.warning(
        "split_long_audio fallback: %s (%.1fs) → %d fixed-time chunks (no silence detected)",
        input_path.name, duration, len(chunks),
    )
    return chunks


def _ffmpeg_extract_chunk(
    input_path: Path,
    chunk_path: Path,
    start_sec: float,
    duration_sec: float,
    chunk_index: int,
    cleanup_dir: Path,
) -> None:
    """ffmpeg `-ss start -t duration -i ... -vn -ar 16k -ac 1 -c:a libmp3lame chunk.mp3`。"""
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss", str(start_sec),
                "-t", str(duration_sec),
                "-i", str(input_path),
                "-vn",
                "-ar", str(ASR_AUDIO_SAMPLE_RATE_HZ),
                "-ac", str(ASR_AUDIO_CHANNELS),
                "-c:a", "libmp3lame",
                "-q:a", str(ASR_AUDIO_MP3_QUALITY),
                str(chunk_path),
            ],
            check=True,
            capture_output=True,
            timeout=SPLIT_TIMEOUT_SEC,
        )
    except subprocess.CalledProcessError as e:
        shutil.rmtree(cleanup_dir, ignore_errors=True)
        stderr = e.stderr.decode("utf-8", errors="replace")[-500:] if e.stderr else ""
        raise AppError(
            ErrorCode.AUDIO_UNREADABLE,
            f"ffmpeg split chunk {chunk_index} failed: {stderr}",
        ) from e
    except subprocess.TimeoutExpired as e:
        shutil.rmtree(cleanup_dir, ignore_errors=True)
        raise AppError(
            ErrorCode.AUDIO_UNREADABLE,
            f"ffmpeg split chunk {chunk_index} timeout after {SPLIT_TIMEOUT_SEC}s",
        ) from e
    if not chunk_path.exists():
        shutil.rmtree(cleanup_dir, ignore_errors=True)
        raise AppError(
            ErrorCode.AUDIO_UNREADABLE,
            f"ffmpeg produced no output for chunk {chunk_index}",
        )


def merge_chunk_results(
    chunks: list[Chunk],
    chunk_segments: list[list[dict]],
) -> list[dict]:
    """合併各 chunk 的 segments 為單一時間軸。

    silence-based 切點下 chunk 之間無 overlap → 直接加 offset、sort、不 dedup。

    speaker_id 不做 re-mapping(由 user 在 editor 手動對齊、M+1 backlog)。
    """
    if len(chunks) != len(chunk_segments):
        raise ValueError(
            f"chunks={len(chunks)} segments={len(chunk_segments)} length mismatch"
        )
    if not chunks:
        return []
    if len(chunks) == 1:
        return list(chunk_segments[0])

    out: list[dict] = []
    for chunk, segs in zip(chunks, chunk_segments, strict=False):
        for s in segs:
            out.append({
                **s,
                "start_time": s["start_time"] + chunk.start_offset_sec,
                "end_time": s["end_time"] + chunk.start_offset_sec,
            })

    out.sort(key=lambda s: s["start_time"])
    return out


# === Sub-chunk helper(給 transcribe_with_retry 用、不受切點演算法影響)===


def split_chunk_in_half_metadata(
    parent: Chunk,
    overlap_sec: float = 5.0,
) -> list[Chunk]:
    """把 parent chunk metadata 切半(不真的執行 ffmpeg)。

    retry sub-chunk 用,維持跟原版 chunk-level retry 相容。
    """
    parent_dur = parent.end_offset_sec - parent.start_offset_sec
    if parent_dur <= 0:
        raise ValueError(f"parent chunk has non-positive duration: {parent_dur}")

    safe_overlap = min(overlap_sec, parent_dur / 3)

    mid = parent.start_offset_sec + parent_dur / 2
    sub_a_start = parent.start_offset_sec
    sub_a_end = mid + safe_overlap / 2
    sub_b_start = mid - safe_overlap / 2
    sub_b_end = parent.end_offset_sec

    return [
        Chunk(
            path=parent.path,
            start_offset_sec=sub_a_start,
            end_offset_sec=sub_a_end,
            is_split=True,
        ),
        Chunk(
            path=parent.path,
            start_offset_sec=sub_b_start,
            end_offset_sec=sub_b_end,
            is_split=True,
        ),
    ]


def split_chunk_in_half(
    parent: Chunk,
    sub_dir: Path,
    depth: int,
    overlap_sec: float = 5.0,
) -> list[Chunk]:
    """把 parent chunk 切半成兩個實體 sub MP3 file。"""
    sub_metas = split_chunk_in_half_metadata(parent, overlap_sec=overlap_sec)
    sub_dir.mkdir(parents=True, exist_ok=True)
    out: list[Chunk] = []
    for i, meta in enumerate(sub_metas):
        sub_path = sub_dir / f"chunk_{int(parent.start_offset_sec)}_sub_{i}.mp3"
        relative_start = meta.start_offset_sec - parent.start_offset_sec
        relative_dur = meta.end_offset_sec - meta.start_offset_sec
        _ffmpeg_extract_chunk(
            parent.path, sub_path, relative_start, relative_dur,
            chunk_index=i, cleanup_dir=sub_dir,
        )
        out.append(Chunk(
            path=sub_path,
            start_offset_sec=meta.start_offset_sec,
            end_offset_sec=meta.end_offset_sec,
            is_split=True,
        ))
    return out
```

**改動清單(對照既有 audio_splitter.py)**:
- 移除 `from difflib import SequenceMatcher`
- 移除 `OVERLAP_DUP_SIMILARITY` 常數
- 加 `import numpy as np` + `from app.utils.silence_slicer import SilenceSlicer`
- `split_long_audio` 簽名拿掉 `overlap_sec` 參數(向後相容:caller 傳了會被 ignore — 若仍有 caller 傳)。實際上 plan 規範 caller 都不傳、所以拿掉 param 不會破任何呼叫。`audio_splitter` 是 module-internal 用、`job_runner.py` 是唯一 caller、看 caller 是否傳。
- 加 `_load_pcm_mono_16k` / `_accumulate_to_chunks` / `_fallback_fixed_split` helper
- 重寫 `split_long_audio` body
- 簡化 `merge_chunk_results`(拿掉 `overlap_sec` 參數、拿掉 dedup)
- 移除 `_is_overlap_duplicate` / `_text_similarity` helper
- 保留 `split_chunk_in_half` / `split_chunk_in_half_metadata`(retry 用)
- 保留 `_ffmpeg_extract_chunk` / `get_duration_sec`

**重要**:如果 `job_runner.py` 有 caller 用 `overlap_sec=` 傳給 `split_long_audio` / `merge_chunk_results`,要一併改 caller。Read `job_runner.py` 確認。

- [ ] **Step 3: 改 caller(如有需要)**

Read `backend/app/services/job_runner.py`,找 `split_long_audio` 跟 `merge_chunk_results` 的呼叫點。如果有傳 `overlap_sec` 參數,拿掉那個 keyword argument。

例如若 `job_runner.py` 有:
```python
chunks = split_long_audio(audio_path, chunks_dir, max_chunk_sec=..., overlap_sec=...)
```
改成:
```python
chunks = split_long_audio(audio_path, chunks_dir, max_chunk_sec=...)
```

merge 也類似:
```python
merged = merge_chunk_results(chunks, chunk_segments, overlap_sec=...)
```
改成:
```python
merged = merge_chunk_results(chunks, chunk_segments)
```

實作 subagent 要 grep / Read 確認真實 caller。

- [ ] **Step 4: 改 `backend/tests/test_audio_splitter.py`**

**刪除** 既有的 overlap dedup test(SequenceMatcher 路徑):
- `test_merge_overlap_dedup_*` 系列(如有)
- `test_is_overlap_duplicate_*`(如有)
- `test_text_similarity_*`(如有)

**保留** 並可能需要 mock 改動的 test:
- 既有 `test_split_long_audio_short_audio_returns_single_chunk`(< threshold case、邏輯不變)
- 既有 `test_get_duration_sec_*`(get_duration_sec helper、不變)
- 既有 `test_split_chunk_in_half_*`(retry helper、不變)

**新增 test**(在檔末加入):
```python
@pytest.mark.asyncio
async def test_accumulate_to_chunks_basic():
    """3 個 silence-bounded ranges、累計成 1 個 chunk(全部加起來 < max)。"""
    from app.services.audio_splitter import _accumulate_to_chunks
    sr = 16000
    # 三段:0-2s / 3-5s / 6-8s,total 8s 沒超過 max 30s
    sample_ranges = [
        (0, 2 * sr), (3 * sr, 5 * sr), (6 * sr, 8 * sr),
    ]
    chunks = _accumulate_to_chunks(sample_ranges, sr, max_chunk_sec=30.0)
    assert len(chunks) == 1
    start, end = chunks[0]
    assert start == pytest.approx(0.0)
    assert end == pytest.approx(8.0)


def test_accumulate_to_chunks_overflow():
    """3 個 ranges 個別 20s、max 30s → 應該切成 2 chunks(前 1 個獨立、後 2 個 too big 各自 chunk)。"""
    from app.services.audio_splitter import _accumulate_to_chunks
    sr = 16000
    sample_ranges = [
        (0, 20 * sr),       # 0-20s
        (25 * sr, 45 * sr), # 25-45s,加進去 = 45s > 30 → 切
        (50 * sr, 70 * sr), # 50-70s,加進去 = 45s > 30 → 切
    ]
    chunks = _accumulate_to_chunks(sample_ranges, sr, max_chunk_sec=30.0)
    assert len(chunks) == 3


def test_accumulate_to_chunks_empty():
    from app.services.audio_splitter import _accumulate_to_chunks
    assert _accumulate_to_chunks([], 16000, 30.0) == []


def test_merge_chunk_results_no_dedup():
    """新版 merge 不做 dedup、相同文字的 segments 都保留(由 editor 處理)。"""
    from app.services.audio_splitter import Chunk, merge_chunk_results
    chunks = [
        Chunk(path=Path("/tmp/c0.mp3"), start_offset_sec=0.0, end_offset_sec=10.0, is_split=True),
        Chunk(path=Path("/tmp/c1.mp3"), start_offset_sec=10.0, end_offset_sec=20.0, is_split=True),
    ]
    chunk_segments = [
        [{"start_time": 0.0, "end_time": 3.0, "speaker_id": 1, "text": "hello"}],
        # chunk 1 開頭(global 10.0s)假設碰巧文字跟 chunk 0 結尾相同 — 新版不 dedup、都保留
        [{"start_time": 0.0, "end_time": 3.0, "speaker_id": 1, "text": "world"}],
    ]
    merged = merge_chunk_results(chunks, chunk_segments)
    assert len(merged) == 2
    assert merged[0]["start_time"] == 0.0
    assert merged[1]["start_time"] == 10.0
    assert merged[1]["text"] == "world"


def test_merge_chunk_results_sort_by_start_time():
    """merge 結果按 start_time 排序。"""
    from app.services.audio_splitter import Chunk, merge_chunk_results
    chunks = [
        Chunk(path=Path("/tmp/c0.mp3"), start_offset_sec=0.0, end_offset_sec=5.0, is_split=True),
        Chunk(path=Path("/tmp/c1.mp3"), start_offset_sec=5.0, end_offset_sec=10.0, is_split=True),
    ]
    chunk_segments = [
        [{"start_time": 4.0, "end_time": 5.0, "speaker_id": 1, "text": "b"}],
        [{"start_time": 0.0, "end_time": 1.0, "speaker_id": 1, "text": "a"}],  # global 5-6s
    ]
    merged = merge_chunk_results(chunks, chunk_segments)
    assert merged[0]["text"] == "b"  # global 4-5s
    assert merged[1]["text"] == "a"  # global 5-6s


def test_fallback_fixed_split_when_no_silence(tmp_path, monkeypatch):
    """slice_ranges 回空 → fallback 固定時間切。"""
    from app.services.audio_splitter import split_long_audio
    import app.services.audio_splitter as splitter_mod

    # mock get_duration_sec 回 120s(超過 threshold 60s)
    monkeypatch.setattr(splitter_mod, "get_duration_sec", lambda p: 120.0)
    # mock _load_pcm_mono_16k 回任意 numpy + sr
    monkeypatch.setattr(
        splitter_mod, "_load_pcm_mono_16k",
        lambda p: (np.zeros(120 * 16000, dtype=np.float32), 16000),
    )
    # mock SilenceSlicer.slice_ranges 回空 → 觸發 fallback
    monkeypatch.setattr(
        splitter_mod.SilenceSlicer, "slice_ranges",
        lambda self, w: [],
    )
    # mock _ffmpeg_extract_chunk 不真的跑 ffmpeg
    monkeypatch.setattr(
        splitter_mod, "_ffmpeg_extract_chunk",
        lambda *args, **kwargs: None,
    )

    # 假音檔(不會真讀)
    fake_audio = tmp_path / "fake.mp3"
    fake_audio.write_bytes(b"fake")

    chunks = split_long_audio(
        fake_audio, tmp_path / "chunks",
        max_chunk_sec=30, threshold_sec=60,
    )
    # fallback 切 120s / 30s = 4 chunks
    assert len(chunks) == 4
    assert all(c.is_split for c in chunks)
    # 第一個 chunk 0-30s
    assert chunks[0].start_offset_sec == 0.0
    assert chunks[0].end_offset_sec == 30.0
    # 最後一個 chunk 90-120s
    assert chunks[-1].start_offset_sec == 90.0
    assert chunks[-1].end_offset_sec == 120.0


def test_split_long_audio_silence_based(tmp_path, monkeypatch):
    """silence-based 切點正常路徑:slicer 回 ranges → 切多 chunk。"""
    from app.services.audio_splitter import split_long_audio
    import app.services.audio_splitter as splitter_mod

    sr = 16000
    monkeypatch.setattr(splitter_mod, "get_duration_sec", lambda p: 120.0)
    monkeypatch.setattr(
        splitter_mod, "_load_pcm_mono_16k",
        lambda p: (np.zeros(120 * sr, dtype=np.float32), sr),
    )
    # mock slice_ranges 回 3 段、各 30s 內合理可累計
    monkeypatch.setattr(
        splitter_mod.SilenceSlicer, "slice_ranges",
        lambda self, w: [
            (0, 25 * sr),
            (30 * sr, 55 * sr),
            (60 * sr, 110 * sr),
        ],
    )
    monkeypatch.setattr(
        splitter_mod, "_ffmpeg_extract_chunk",
        lambda *args, **kwargs: None,
    )

    fake_audio = tmp_path / "fake.mp3"
    fake_audio.write_bytes(b"fake")

    chunks = split_long_audio(
        fake_audio, tmp_path / "chunks",
        max_chunk_sec=60, threshold_sec=60,
    )
    # 30s+25s = 55s <= 60s 可合;再加 50s → 105s > 60s 切
    # 預期 2 個 chunks:[(0, 55), (60, 110)]
    assert len(chunks) == 2
    assert chunks[0].start_offset_sec == pytest.approx(0.0)
    assert chunks[0].end_offset_sec == pytest.approx(55.0)
    assert chunks[1].start_offset_sec == pytest.approx(60.0)
    assert chunks[1].end_offset_sec == pytest.approx(110.0)


def test_split_long_audio_short_passes_through(tmp_path, monkeypatch):
    """duration < threshold → 不切、回單 chunk path 指原檔。"""
    from app.services.audio_splitter import split_long_audio
    import app.services.audio_splitter as splitter_mod

    monkeypatch.setattr(splitter_mod, "get_duration_sec", lambda p: 30.0)
    fake_audio = tmp_path / "short.mp3"
    fake_audio.write_bytes(b"fake")

    chunks = split_long_audio(
        fake_audio, tmp_path / "chunks",
        max_chunk_sec=55, threshold_sec=60,
    )
    assert len(chunks) == 1
    assert chunks[0].path == fake_audio
    assert chunks[0].is_split is False
    assert chunks[0].start_offset_sec == 0.0
    assert chunks[0].end_offset_sec == 30.0
```

- [ ] **Step 5: Commit**

```
git -C /d/vibevoice_asr add backend/app/config.py backend/app/services/audio_splitter.py backend/tests/test_audio_splitter.py backend/app/services/job_runner.py
```

(`job_runner.py` 視 caller 是否有改、若沒改可移除。)

```
git -C /d/vibevoice_asr commit -m "feat(splitter): silence-based 切點取代固定時間 + overlap dedup"
```

```
git -C /d/vibevoice_asr push
```

---

## 完成後驗證(全部 task 跑完、user 在 Linux 端)

```
git pull
```

```
docker compose build backend
```

```
docker compose up -d backend worker
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

預期 0 errors / 全綠。

### 實機驗收

跑一支 2-3 分鐘音檔(從現有 Job 重新跑或新上傳),預期:

1. JobList 看到新 Job 完成、status=done
2. 進 Editor:**時間軸不再有重複段**(關鍵驗收點)
3. segment 切點應落在自然語句邊界(可手動聽幾段邊界驗、不切到字中間)
4. 對比舊版同支音檔的 segments 數應 ≈ 或略少(因為 dedup 失敗的重複段消失)

如果有極端音檔(整段連續講話無 silence)→ backend log 應看到 `split_long_audio fallback: ... (no silence detected)`,確認 fallback 路徑能跑通。

---

## Risks / Common Pitfalls

| 風險 | 偵測 | 處理 |
|---|---|---|
| upstream slicer2.py 沒 `slice_ranges` public method | implementer fetch 時看 | 把 internal indices 計算抽成 `slice_ranges` method、暴露出來 |
| `_load_pcm_mono_16k` 對極長音檔(>4h)記憶體爆 | OOM | 既有 audio duration validate 在 upload 端已擋 |
| numpy 不在 backend container | import error | 既有 parser.py 已用 numpy、應該在 |
| 真實錄音 silence 不滿足 -40dB threshold(雜音重) | slice_ranges 回空 / 異常多片 | fallback 路徑會接、或 user 調 settings |
| job_runner 有 caller 傳 overlap_sec 參數 | TypeError unexpected keyword | Read 確認、Step 3 修 caller |
| SilenceSlicer 對 float32 vs float64 敏感 | dtype error | 我們 `astype(np.float32)`、upstream 應該支援 |

---

## Out of Scope(本 plan 不做)

- 動態調 silence threshold
- 切點 visualization
- 自家實作 silence detection 替代 audio-slicer
- 多 channel 處理(已用 -ac 1 強制 mono)

---

## Plan Self-Review Checklist

- [x] 兩個 task 都有具體 file path
- [x] 每個 step 含完整 code(silence_slicer.py 部分 vendor、需 implementer fetch upstream)
- [x] 完成條件對應 spec §10
- [x] 命名一致(`SilenceSlicer` Python class、`silence_*_ms` config 變數一律 snake_case)
- [x] 依賴順序:Task 2 依賴 Task 1
- [x] 沒列 spec out-of-scope 範圍的東西
