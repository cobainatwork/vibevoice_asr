# M5 完整版（partial retry + 並行 chunk 推論）設計

> **記錄日**：2026-05-10
> **觸發點**：M3.5 Linux 實機測試暴露 vLLM 對長音檔生成不穩定，M5 minimal 切段後
> 仍每段 partial（10 分鐘檔覆蓋率 ~85%），達不到 v1 API 嚴格契約能 ship 的水平。
> 配合「ASR 系統的職責是準確率」原則，partial fail 必須降到 < 3% 才能進 M6。

## 一、 背景

### 1.1 當前狀態（M5 minimal viable）

`backend/app/services/audio_splitter.py` 已實作：
- `split_long_audio`：固定時間切段（55s chunk + 5s overlap、50s 步進）
- `merge_chunk_results`：offset 加 + overlap dedup（SequenceMatcher 相似度 ≥ 0.7）

但 vLLM 推論本身對長音檔生成不穩、對 13 chunks（10 分鐘檔）仍有 ~15% chunk 觸發
repetition detection、`result.partial=True`、最終 transcript 留下大量 gap。

### 1.2 為何 M5 minimal 不夠

`docs/superpowers/backlog/2026-05-10-asr-quality-risks.md` 已記錄：M6 v1 API
brainstorming 決議走「嚴格契約」（done = 完整覆蓋；partial → failed），核心理由
是 ASR 系統的職責是輸出品質、不該把 partial 的判斷推給 QC 端。但 ~15% fail 比例
頻繁觸發、QC 端不可用。M5 完整版要把這個比例壓到 < 3%。

## 二、 目標

| 指標 | M5 minimal | M5 完整版目標 |
|---|---|---|
| 10 分鐘檔 partial chunk 比例 | ~15% | **< 3%** |
| 13 chunks 處理時間 | 60-100s（序列） | **10-20s**（並行） |
| pytest 覆蓋 | 既有 219 | + 5-8 條 retry / 並行 test |
| 對 admin / Job model 的破壞 | 無 | 無（`chunks_total` / `chunks_done` 語義不變） |

## 三、 不目標

留作 backlog、本次不做：

- **silence boundary detection**：當前固定時間切，可能切在詞中間。partial retry
  會 cover 大部分這類 case、邊際效益遞減。實作要 ffmpeg `silencedetect` 解析 +
  最近邊界選取邏輯，複雜度跳一階。
- **跨 chunk speaker_id 對齊**：當前 user 在 editor 手動修。本層屬 dataset 品質
  改進、不阻擋 M6 / QC 整合。
- **改 vLLM prompt 策略**（譬如不傳 hotwords / 改 system prompt）：探索性、效果
  不確定，需 A/B 實測，不在工程 spec 範圍。
- **vLLM 升版**：vibevoice plugin 跟 v0.14.x 綁定、升版高風險。

## 四、 設計決策

### 4.1 partial retry 策略（核心）

**遞迴切半 chunk-level retry**：

```
depth 0: 55s chunk → vLLM
  ├─ result.partial == False → ✓ 用此 result（chunks_done++）
  └─ result.partial == True  → 進入 depth 1 retry
       depth 1: 切成 2 個 ~30s sub-chunks（含 5s overlap）
                並行跑 vLLM
         ├─ 兩個都 partial == False → ✓ merge 兩個 sub-chunk segments、用此結果
         ├─ 任一 partial == True   → 該 sub-chunk 進入 depth 2 retry
                                      depth 2: 切成 2 個 ~17s sub-sub-chunks
                                               並行跑 vLLM
                                       ├─ partial == False → ✓
                                       └─ partial == True → 達 retry 上限、接受 partial
```

**為何切半 + 上限 2 次**：

- 切半保持邏輯簡單（每深度都同 split-into-2 邏輯）
- 上限 2 次（最深 17s）：實測 vLLM 對 ~17s 對話穩定處理、再切短意義不大
- 達上限仍 partial → 視為極少數邊際 case、用既有 `merge_chunk_results` 的 partial
  容忍邏輯收進結果

**觸發條件純依 `result.partial`**：不另引入「coverage_pct < threshold」這層、
保持跟既有 `vllm_client._detect_repetition` 行為一致。

### 4.2 並行 chunk 推論

**`asyncio.Semaphore(N)` 控併發**：

```python
sem = asyncio.Semaphore(settings.chunk_concurrency)  # 預設 8

async def transcribe_one(chunk):
    async with sem:
        return await vllm_client.transcribe(...)

results = await asyncio.gather(*[transcribe_one(c) for c in chunks])
```

**為何 8 並發預設**：

- vLLM 端 `VLLM_MAX_NUM_SEQS=64`，8 是其 1/8、留空間給其他 admin 路徑同時 transcribe
- backend HTTPX 預設 connection pool 100、8 不會成為瓶頸
- 13 chunks 大致兩波（8 + 5）跑完、總時間 ~10-20s

**設定可由 `.env` 覆寫**：`CHUNK_CONCURRENCY=8`（新增 settings field）

### 4.3 retry 跟並行的交互

**retry sub-chunks 也走並行**（同一個 Semaphore）：

- 原 chunk partial → 切成 2 個 sub-chunks → 兩個 sub-chunks 並發排隊
- sub-chunk 也 partial → 各自再切成 2 個 sub-sub-chunks → 4 個並發排隊
- 全部走同一 `asyncio.Semaphore`、被併發上限控管

**最壞情況**：13 個原 chunks 都 partial、深度 2、每個產生 4 個 sub-sub-chunks
→ 總 vLLM call 數 13 × (1 + 2 + 4) = 91 次。8 並發約 12 波、~120-180s 完成。
極少發生（real world 多數 chunk 第一輪就成功）。

### 4.4 進度追蹤（`chunks_total` / `chunks_done`）

**保持原始切數的語義**：

| 欄位 | 計算方式 |
|---|---|
| `chunks_total` | 原始 `split_long_audio` 切出的數量（不含 retry sub-chunks） |
| `chunks_done` | 完成的**原始** chunks 數（含 retry 後仍 partial 視為完成） |
| `progress` | `chunks_done / chunks_total` |

retry 是內部實作細節、不外暴露。frontend 顯示 `13/13 (100%)` 對應原始切數，不必
知道 retry 多深。

### 4.5 partial 結果 merge

retry sub-chunks 的 segments 用既有 `merge_chunk_results` 規則合併：
- offset_sec 加總（sub-chunk 的 start_offset_sec 是 parent chunk 的 offset + sub
  在 parent 內部的偏移）
- overlap 區內文字相似度 >= 0.7 視為重複、保留前者

最終 merge 進原 chunk 的「位置」（取代原 chunk 的 segments）。

## 五、 架構

### 5.1 模組改動

```
backend/app/
├── config.py                       # +1 setting: chunk_concurrency
├── services/
│   ├── audio_splitter.py           # 加 split_chunk_recursive helper（切半遞迴）
│   ├── job_runner.py               # _transcribe_all_chunks 改用 asyncio.gather + Semaphore
│   └── vllm_client.py              # 不動
└── utils/
    └── ... (no change)
```

### 5.2 主流程（`_do_transcribe`）

```
audio file
  ↓
split_long_audio（不變）
  ↓ chunks: list[Chunk]（原始切數）
  ↓
sem = asyncio.Semaphore(N)
  ↓
results = asyncio.gather(*[
    transcribe_with_retry(chunk, depth=0, max_depth=2, sem=sem)
    for chunk in chunks
])
  ↓
（每個 chunk 完成後）chunks_done++、寫 DB
  ↓
merge_chunk_results(chunks, results)  # 原 chunks 排列、不變
  ↓
寫 Job.segments / status=DONE
```

### 5.3 `transcribe_with_retry` 函數

```python
async def transcribe_with_retry(
    chunk: Chunk,
    *,
    depth: int,
    max_depth: int,
    sem: asyncio.Semaphore,
    settings: Settings,
    hotwords: list[str],
) -> ChunkOutcome:
    """遞迴 chunk-level retry。回傳 ChunkOutcome（segments + raw_text + 是否 partial）。

    depth 0 = 原始 chunk（55s）
    depth N>0 = retry sub-chunk（每深度切半）
    """
    audio_bytes, mime = await load_chunk_audio(chunk)
    duration = chunk.end_offset_sec - chunk.start_offset_sec
    async with sem:
        result = await vllm_client.transcribe(audio_bytes, mime, duration, hotwords)

    segs, _ = parse_transcription(result["raw_text"])
    if not result["partial"] or depth >= max_depth:
        return ChunkOutcome(segments=segs, raw_text=result["raw_text"],
                            partial=result["partial"], depth_reached=depth)

    # Partial、未達上限 → 切半遞迴
    sub_chunks = split_chunk_in_half(chunk, depth=depth + 1)
    sub_outcomes = await asyncio.gather(*[
        transcribe_with_retry(sc, depth=depth + 1, max_depth=max_depth, sem=sem,
                              settings=settings, hotwords=hotwords)
        for sc in sub_chunks
    ])
    merged_segs = merge_chunk_results(sub_chunks, [o.segments for o in sub_outcomes])
    any_partial = any(o.partial for o in sub_outcomes)
    return ChunkOutcome(
        segments=merged_segs,
        raw_text="\n--- sub-chunk ---\n".join(o.raw_text for o in sub_outcomes),
        partial=any_partial,
        depth_reached=max(o.depth_reached for o in sub_outcomes),
    )
```

### 5.4 `split_chunk_in_half` helper

```python
def split_chunk_in_half(parent: Chunk, depth: int) -> list[Chunk]:
    """把 parent chunk 切成兩個 sub-chunks（含 overlap），ffmpeg 寫到 chunks_dir/depth_N/。

    overlap 比例隨 depth 縮放：
      depth 0 → 1: parent 55s → sub 30s + 5s overlap → 步進 25s（兩段覆蓋 55s）
      depth 1 → 2: parent 30s → sub 17s + 3s overlap → 步進 14s

    overlap 隨切短按比例縮、保持「邊界容錯比例」相對一致。
    """
```

### 5.5 chunks_dir 結構

```
data/uploads/{job_id}/chunks/
├── chunk_000.mp3        # depth 0 原 chunk
├── chunk_001.mp3
├── ...
└── depth_1/
    ├── chunk_005_sub_0.mp3   # 原 chunk_005 partial、retry 切半
    ├── chunk_005_sub_1.mp3
    └── depth_2/
        ├── chunk_005_sub_0_sub_0.mp3
        └── ...
```

job 完成後（成功或 fail）整個 `chunks/` 目錄清掉（既有邏輯，不變）。

## 六、 設定

### 6.1 新增 `Settings` field

```python
# backend/app/config.py
chunk_concurrency: int = 8  # 並行 chunk 推論上限（包含 retry sub-chunks）
chunk_retry_max_depth: int = 2  # partial chunk retry 最多遞迴幾層
```

### 6.2 `.env` 範例

```bash
# === ASR Pipeline ===
CHUNK_CONCURRENCY=8
CHUNK_RETRY_MAX_DEPTH=2
```

## 七、 風險與權衡

| 風險 | 影響 | 緩解 |
|---|---|---|
| retry 全部都 partial 的 worst case 處理時間爆增 | 13 × 7 次 = 91 vLLM call、8 並發 ~12 波 ~3 分鐘 | 實測中極少發生；可加 timeout 上限 watchdog 保險 |
| 並行加重 vLLM 負載 | 多用戶同時 transcribe 時擠爆 | `chunk_concurrency` 預設 8、留 vLLM `max_num_seqs=64` 充裕空間 |
| sub-chunk overlap 過小 → 詞被切斷邊界容錯不夠 | 邊界詞遺失 | overlap 隨深度按比例縮（5s → 3s）、merge 邏輯仍按 SequenceMatcher 0.7 dedup |
| sub-chunk segments offset 計算錯誤 | 時間軸錯位 | 嚴格 unit test 覆蓋 sub-chunk offset = parent.start_offset_sec + sub_offset_in_parent |
| retry depth 偵測 hysteresis（depth 1 全 partial 但 depth 0 raw_text 其實涵蓋大半） | 重複工 | 不偵測、接受可能重複工；real world impact 小 |

## 八、 驗收標準

### 8.1 功能驗收

跑既有 13 chunk 案例（10 分鐘音檔 `華厚%`）：

- `chunks_total = 13`（原始切數、不變）
- `chunks_done = 13`
- `n_segs` ≥ 100（之前 minimal 是 97、retry 後應更多）
- 對應 segment 時間軸 gap：所有 gap < 5s（之前有多個 30-50s gap）
- `Job.error` 為 NULL 或最多 1 個 chunk partial（< 8% 比例）

### 8.2 效能驗收

- 處理時間 ≤ 30s（10 分鐘檔，之前 60-100s）
- 並發 8 chunks vLLM HTTP 連線健康、無 connection pool exhaustion

### 8.3 自動測試

新增 `backend/tests/test_chunk_retry.py`：

- `test_no_retry_when_partial_false`
- `test_retry_once_then_success`
- `test_retry_twice_reaches_max_depth`
- `test_split_chunk_in_half_offsets_correct`
- `test_concurrent_transcribe_via_semaphore`（mock vllm_client）
- `test_chunks_done_counter_excludes_retry_sub_chunks`

### 8.4 lint / type / security

- ruff 0
- mypy 0
- pytest 既有 219 + 新加 → 全 pass
- bandit 0 high+/medium

## 九、 後續 backlog（M5 完整版範圍外）

依優先順序：

1. **silence boundary detection**：partial retry 不能 cover 的 case（譬如某段對話本身
   速度太快、模型對 fast speech 不穩）、配合 silence 邊界切點可進一步降 fail 比例
2. **跨 chunk speaker_id 對齊**：dataset 品質改進、user editor 手動修現可接受
3. **vLLM prompt strategy 探索**：A/B 實測「不傳 hotwords / 不同 system prompt」對
   partial 比例的影響
4. **可變 chunk concurrency**：依 vLLM 當前負載動態調整（譬如 admin queue 多時降到 4、空閒時拉到 16）

## 十、 關聯文件

- `docs/superpowers/backlog/2026-05-10-asr-quality-risks.md` — 觸發本 spec 的風險紀錄
- `SPEC.md §6.5` — 原始 M5 切段需求
- `backend/app/services/audio_splitter.py` — minimal 版本的基礎
- `backend/app/services/job_runner.py` — 主流程整合點
