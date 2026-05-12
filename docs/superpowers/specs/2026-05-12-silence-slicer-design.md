# Silence-based Audio Splitter 設計

> **For agentic workers:** REQUIRED SUB-SKILL: 後續用 `superpowers:writing-plans` 寫實作計畫,再用 `superpowers:subagent-driven-development` 派 subagent 執行。

**目標:** 把長音檔切段策略從「固定時間 + overlap」改成「silence detection」,切點對齊自然句邊界、無 overlap、merge 階段拿掉 SequenceMatcher dedup。徹底解決 editor 看到時間區段重複的問題。

**架構:** vendor `flutydeer/audio-slicer` 的 `slicer2.py`(MIT、~110 行、純 numpy)成 `app/utils/silence_slicer.py`。`audio_splitter.split_long_audio` 重寫切點演算法:讀 PCM 進 numpy → Slicer 找 silence ranges → 累計成 ≤ `chunk_duration_sec` 的 chunk → ffmpeg 切 mp3。`merge_chunk_results` 拿掉 dedup。

**Tech Stack:** ffmpeg(已有)+ numpy(已有)+ vendored audio-slicer(新 vendor、MIT)。**不引入** librosa / soundfile / scipy。

---

## 1. 動機

### 1.1 現況問題

`audio_splitter.split_long_audio` 用固定時間切(預設每 55s chunk + 5s overlap):

- 切點純時間、忽略 silence、會在字中間切斷
- 靠 5s overlap 容錯邊界字、相鄰 chunk 各自獨立推論
- merge 階段用 SequenceMatcher 文字相似度 0.7 在 overlap 區做 dedup
- 仍會發生:vLLM 對同段語音在兩個 chunk 中產出文字差異略大的 segments → dedup 抓不到 → editor 看到時間軸重複的兩條 segments

### 1.2 換成 silence-based 切點的好處

- 切點 100% 在 silence(無語音)區、不切斷字
- 每 chunk 是完整語句邊界、vLLM context 不被破壞
- 不需要 overlap → 不需要 dedup → editor 不會看到重複時間段
- 推論精度應提升(完整句子比邊界切斷更穩)

### 1.3 不在此議題

- 速度優化(silence detection 對長檔可能比 ffmpeg 稍慢、可接受)
- 替代演算法(VAD / energy peak):audio-slicer 已是社群驗證過的方案
- speaker diarization(跨 chunk speaker_id 對齊仍是 backlog)

---

## 2. 範圍

### 2.1 In scope

- vendor audio-slicer `slicer2.py` 進 `app/utils/silence_slicer.py`
- 重寫 `split_long_audio` 用 silence ranges 切點
- 簡化 `merge_chunk_results`(拿掉 dedup)
- 新增 silence detection 設定(threshold / min_length / min_interval / hop_size / max_sil_kept)
- 廢棄 `split_overlap_sec` 設定(保留欄位 backward compat、不再使用)
- 既有 chunk-level retry(`transcribe_with_retry`)邏輯不變
- 既有 並行 chunk 推論(`asyncio.Semaphore + gather`)邏輯不變

### 2.2 Out of scope

- 替代 audio-slicer 為自家實作(直接 vendor 即可)
- librosa 整合(我們用 ffmpeg + numpy.frombuffer 自己讀 PCM)
- silence detection 動態調參(由 config 一次設定)
- 多 channel 處理(既有 pipeline 已用 `-ac 1` 強制 mono)

---

## 3. 資料流

```
[input_path] (任意格式音檔)
    ↓ ffmpeg -i ... -ar 16000 -ac 1 -f s16le -
[16-bit PCM bytes stdout]
    ↓ numpy.frombuffer(int16) → astype(float32) / 32768.0
[1D numpy array, float32, range -1.0 to 1.0]
    ↓ Slicer(sr=16000, threshold=-40, ...).slice_ranges(waveform)
[list of (begin_sample, end_sample)]
    ↓ accumulate_chunks(max_chunk_sec=55)
[list of (chunk_start_sec, chunk_end_sec)]
    ↓ for each, ffmpeg -ss start -t dur -i input -ar 16k -ac 1 -c:a libmp3lame chunk.mp3
[list of Chunk(path, start_offset_sec, end_offset_sec, is_split=True)]
```

對應現況:差別只在「切點選擇」階段、`Chunk` 結構不變、後續 `transcribe_with_retry` / `merge_chunk_results` 流程 80% 復用。

---

## 4. silence_slicer.py(vendor)

### 4.1 來源

`https://github.com/flutydeer/audio-slicer/blob/main/slicer2.py`,MIT license。

### 4.2 整合方式

直接複製 `Slicer` class 內容到 `backend/app/utils/silence_slicer.py`,**不要**整個 module copy(避免 main / librosa import):

```python
"""
Silence-based audio slicer.

Adapted from flutydeer/audio-slicer (MIT license).
Original: https://github.com/flutydeer/audio-slicer/blob/main/slicer2.py

Strip 原版的 main / librosa load,只保留 Slicer class(純 numpy);
我們的 caller 自行用 ffmpeg + numpy.frombuffer 讀 PCM。
"""
from __future__ import annotations

import numpy as np


class SilenceSlicer:
    """RMS-based silence detection slicer。"""

    def __init__(
        self,
        sr: int,
        threshold: float = -40.0,
        min_length: int = 5000,
        min_interval: int = 300,
        hop_size: int = 20,
        max_sil_kept: int = 5000,
    ): ...

    def slice_ranges(self, waveform: np.ndarray) -> list[tuple[int, int]]:
        """回 [(begin_sample, end_sample), ...],對應切片在 waveform 中的範圍。"""
        ...
```

`slice_ranges` 是 audio-slicer 內部 helper,public 用法是 `slice()`(回 audio chunks)。我們**不要** audio chunks、只要 sample ranges 換算成秒,所以暴露 `slice_ranges`。

實作層面我們直接 copy upstream `Slicer` class、改名 `SilenceSlicer`、加 module docstring 標 attribution。

### 4.3 License & Attribution

`app/utils/silence_slicer.py` 頂部 docstring:
```python
"""
Adapted from flutydeer/audio-slicer (MIT License).
Original: https://github.com/flutydeer/audio-slicer

Copyright (c) 2023 flutydeer
"""
```

repo 根 `NOTICE` 或 `LICENSES/` 加 audio-slicer MIT 全文(非必須、但 nice-to-have)。

---

## 5. audio_splitter.py 改動

### 5.1 `split_long_audio` 重寫

**新流程**:

```python
def split_long_audio(input_path, output_dir, max_chunk_sec=None, threshold_sec=None):
    settings = get_settings()
    max_chunk_sec = max_chunk_sec or settings.split_chunk_duration_sec
    threshold_sec = threshold_sec or settings.auto_split_threshold_sec

    duration = get_duration_sec(input_path)
    if duration <= threshold_sec:
        return [Chunk(path=input_path, start_offset_sec=0.0, end_offset_sec=duration, is_split=False)]

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
        # 整段無 silence 切點(罕見)→ fallback 固定時間切
        return _fallback_fixed_split(input_path, output_dir, duration, max_chunk_sec)

    # 3. 累計成 chunk:把連續多個 silence 片組成 ≤ max_chunk_sec 的 chunk
    chunk_time_ranges = _accumulate_to_chunks(sample_ranges, sr, max_chunk_sec)

    # 4. ffmpeg 切實體 mp3
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks = []
    for i, (start_sec, end_sec) in enumerate(chunk_time_ranges):
        chunk_path = output_dir / f"chunk_{i:03d}.mp3"
        _ffmpeg_extract_chunk(input_path, chunk_path, start_sec, end_sec - start_sec, i, output_dir)
        chunks.append(Chunk(
            path=chunk_path,
            start_offset_sec=start_sec,
            end_offset_sec=end_sec,
            is_split=True,
        ))

    logger.info(
        "split_long_audio: %s (%.1fs) → %d chunks (silence-based, max_chunk=%ds)",
        input_path.name, duration, len(chunks), max_chunk_sec,
    )
    return chunks
```

### 5.2 `_load_pcm_mono_16k`(新增 helper)

```python
def _load_pcm_mono_16k(input_path: Path) -> tuple[np.ndarray, int]:
    """ffmpeg → 16kHz mono PCM stdout → numpy float32 array。

    -f s16le -:輸出 raw 16-bit little-endian PCM 到 stdout(不寫檔)。
    """
    sr = ASR_AUDIO_SAMPLE_RATE_HZ  # 16000
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
        raise AppError(ErrorCode.AUDIO_UNREADABLE, f"ffmpeg PCM decode failed: {stderr}") from e
    except subprocess.TimeoutExpired as e:
        raise AppError(ErrorCode.AUDIO_UNREADABLE, "ffmpeg PCM decode timeout") from e

    pcm_int16 = np.frombuffer(result.stdout, dtype=np.int16)
    waveform = pcm_int16.astype(np.float32) / 32768.0  # normalize to [-1, 1]
    return waveform, sr
```

### 5.3 `_accumulate_to_chunks`(新增 helper)

```python
def _accumulate_to_chunks(
    sample_ranges: list[tuple[int, int]],
    sr: int,
    max_chunk_sec: float,
) -> list[tuple[float, float]]:
    """把連續 silence-bounded 片累計成 ≤ max_chunk_sec 的 chunk。

    每個 silence range 是 (begin_sample, end_sample),代表一段「非靜音」內容。
    我們累計多段直到下一段加進去會超過 max_chunk_sec 為止,然後斷成一個 chunk。

    回時間秒 (start_sec, end_sec)。
    """
    if not sample_ranges:
        return []

    max_samples = int(max_chunk_sec * sr)
    chunks: list[tuple[float, float]] = []
    current_start = sample_ranges[0][0]
    current_end = sample_ranges[0][1]

    for begin, end in sample_ranges[1:]:
        # 嘗試把這段併進當前 chunk
        if end - current_start <= max_samples:
            current_end = end
        else:
            # 超過上限,先 commit 當前 chunk、開新 chunk
            chunks.append((current_start / sr, current_end / sr))
            current_start = begin
            current_end = end

    # 最後一個 chunk
    chunks.append((current_start / sr, current_end / sr))
    return chunks
```

### 5.4 `_fallback_fixed_split`(新增、處理 edge case)

```python
def _fallback_fixed_split(
    input_path: Path, output_dir: Path, duration: float, max_chunk_sec: float,
) -> list[Chunk]:
    """整段無 silence 切點時的 fallback:固定時間切、無 overlap。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[Chunk] = []
    i = 0
    start = 0.0
    while start < duration - 0.01:
        end = min(duration, start + max_chunk_sec)
        chunk_path = output_dir / f"chunk_{i:03d}.mp3"
        _ffmpeg_extract_chunk(input_path, chunk_path, start, end - start, i, output_dir)
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
```

### 5.5 `merge_chunk_results` 簡化

拿掉 SequenceMatcher dedup(silence-based 切點無 overlap、不需要):

```python
def merge_chunk_results(
    chunks: list[Chunk],
    chunk_segments: list[list[dict]],
) -> list[dict]:
    """合併各 chunk 的 segments 為單一時間軸。

    silence-based 切點下,chunk 之間無 overlap → 直接加 offset、sort、不 dedup。

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
```

拿掉的部分:
- `OVERLAP_DUP_SIMILARITY` 常數
- `_is_overlap_duplicate` helper
- `_text_similarity` helper(可保留供未來用 / 或一併刪)
- `merge_chunk_results` 的 `overlap_sec` 參數

### 5.6 `split_chunk_in_half` / `split_chunk_in_half_metadata` 保留

這兩個 helper 給 `transcribe_with_retry`(chunk-level recursive retry)用、不受切點演算法影響、保留不動。

---

## 6. config.py 新增 settings

```python
# === Silence-based slicer 參數 ===

# silence detection RMS 振幅閾值(dB)。-40 是 audio-slicer 預設、適合多數錄音。
silence_threshold_db: float = -40.0

# 每段最短長度(ms)。audio-slicer 預設 5000 對歌曲設計,
# ASR 場景改 2000(短句也保留、避免合併太多短句到一個 chunk)。
silence_min_length_ms: int = 2000

# silence 至少多長才視為切點(ms)。300 過濾掉短停頓(如句中換氣)、
# 對話換手通常 > 300ms。
silence_min_interval_ms: int = 300

# RMS 計算窗口 hop size(ms)。
silence_hop_size_ms: int = 20

# 切點處保留前後 silence 的最大長度(ms)。1000 = 邊界各留 0.5s silence
# 避免邊界字被砍。
silence_max_kept_ms: int = 1000
```

廢棄(保留欄位 backward compat,新版 code 不再讀):
```python
# 已廢棄(silence-based 切點不需要 overlap)、留欄位避免 .env / migration 破。
split_overlap_sec: int = 0
```

---

## 7. 邊界 case 與風險

| 情境 | 處理 |
|---|---|
| 音檔整段無 silence(極端罕見、純樂器演奏 / 連續講話)| `slice_ranges` 回空 → `_fallback_fixed_split` 走原固定切邏輯 |
| 音檔極多 silence、切點 100+ 個 | `_accumulate_to_chunks` 累計到 max_chunk_sec、chunk 數合理 |
| 音檔 < `auto_split_threshold_sec`(短檔)| `split_long_audio` 第一個 if 走、不切、回單 chunk(行為跟現況一樣) |
| silence threshold -40dB 對極端錄音不適用(雜音重 / 音量低)| 預設用 -40 足夠多數 case、user 可調 settings,極端 case 可 fallback 偵測:slice_ranges 回空 → 退到 fixed split |
| `_load_pcm_mono_16k` 對大檔記憶體壓力 | 1 小時 mono 16kHz int16 = 115MB,float32 normalize 後 = 230MB,可接受。極長檔(>4hr)前置驗證已擋。 |
| ffmpeg `-f s16le -` stdout pipe 對 hour-scale 音檔阻塞 | subprocess.run capture_output 一次性讀完、timeout 600s 保護 |
| audio-slicer slicer2.py 用 `numpy.lib.stride_tricks.as_strided` | 安全用法、無 memory issue;test 覆蓋邊界 case |

---

## 8. 測試策略

### 8.1 Unit tests

| 檔 | 範圍 |
|---|---|
| `test_silence_slicer.py`(新建)| SilenceSlicer 基本切點(silent gap → 兩 ranges)、無 silence(整段 ranges)、長 silence(切多段)、空輸入(empty ranges)|
| `test_audio_splitter.py`(改)| 新增 `test_split_long_audio_silence_based`(mock _load_pcm + silence_slicer、驗 chunk_ranges 邏輯)、`test_accumulate_to_chunks_basic / overflow`、`test_fallback_fixed_split_when_no_silence`、`test_merge_chunk_results_no_dedup`;**刪除** overlap dedup 相關 test |

### 8.2 Integration / 實機

- 跑一支真實長音檔(2-3 分鐘):editor 看不到時間軸重複段
- 比對舊版同支音檔輸出:應減少 / 消除重複 segment、總 segment 數 ≈ 或略少

### 8.3 不做的 test

- audio-slicer slicer2.py 內部演算法的 unit test(視為 vendor 黑箱、信任 upstream)
- 對各種 silence threshold 的 sweep test(預設值固定)

---

## 9. 遷移與相容性

### 9.1 既有 Job 不受影響

已存 Job.segments 是過去 ffmpeg 固定切的結果、不重新處理。新 Job 才走新流程。

### 9.2 既有 `.env` 設定

- `split_overlap_sec=5`:仍可在 .env 內、但被忽略(silence-based 不用)
- `split_chunk_duration_sec=55`:仍生效(累計上限)
- `auto_split_threshold_sec=60`:仍生效(觸發切段門檻)

### 9.3 既有 test 影響

跟 overlap dedup 相關的 test 要刪掉:
- `test_merge_overlap_dedup_*`(SequenceMatcher 路徑)

跟 fixed-time 切的 test 要改成 mock slicer:
- 老 test 假設「duration / chunk_dur → N chunks」、新版要 mock `_load_pcm_mono_16k` + `slice_ranges` 才能控制 chunk 數

---

## 10. 完成條件

- [ ] `backend/app/utils/silence_slicer.py` vendor 完、加 MIT attribution
- [ ] `backend/app/services/audio_splitter.py` 重寫切點演算法 + 簡化 merge
- [ ] `backend/app/config.py` 加 5 個 silence settings + 廢棄 split_overlap_sec
- [ ] `backend/tests/test_silence_slicer.py` 新建(4-6 條 test)
- [ ] `backend/tests/test_audio_splitter.py` 改:刪 dedup test、加 silence-based test
- [ ] backend pytest 全綠
- [ ] ruff / mypy / bandit 全綠
- [ ] 實機 2-3 分鐘音檔:editor 看不到時間軸重複段

---

## 11. Open Questions(本 spec 不解、後續迭代)

- silence detection 對嘈雜環境錄音的調參指南(實機累積 case 後文檔化)
- 切點 visualization 工具(讓 user 在 editor 看到切點位置、debug 用)
- 動態調 threshold(依音檔自動算 RMS 分佈)

---

## 12. 不變條件(Non-Goals)

- 不改 `transcribe_with_retry` chunk-level retry 邏輯
- 不改 chunk 並行推論(asyncio.Semaphore + gather)
- 不改 Chunk dataclass 結構
- 不引入 librosa / soundfile / scipy
- 不改既有 Job / Segment / vLLM client 介面
