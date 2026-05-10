# ASR 品質保證風險清單

> **記錄日**：2026-05-10
> **狀態**：已暴露但未完整解決，admin 路徑可接受、v1 API 上線前必修
> **觸發點**：M6 v1 API brainstorming 第一個議題
> **上下文**：M3.5 完成後 Linux + GPU 實機測試暴露的 vLLM repetition 行為，本檔
> 集中記錄相關設計風險與已嘗試的緩解措施

---

## 一、 核心觀察：vLLM 對長音檔生成不穩定

### 1.1 現象

10 分鐘中文商業會議錄製檔上傳測試（檔名 `華厚%`）：

| 階段 | chunk 設定 | n_segs | partial chunk 比例 | 覆蓋率推估 |
|---|---|---|---|---|
| 不切段（M5 前） | N/A | 3 | 1/1 = 100% | ~5%（前 30 秒就 repetition） |
| 切 13 段 + 舊 detection（200/10/3） | 55s + 5s overlap | 45 | 7/13 ≈ 54% | ~30% |
| 切 13 段 + 放寬 detection（300/15/4） | 55s + 5s overlap | 97 | 2/13 ≈ 15% | ~85% |

舊 detection 在中文商業對話的密集自然重複（「就是」「我們」「品項」「易發票」）會誤判為 repetition loop、提前中斷生成。放寬 window / substring length / occurrences 後 false positive 大幅減少。

### 1.2 殘餘問題

放寬 detection 後仍有約 15% chunk 是真 repetition loop（vLLM 模型本身對某些音訊內容不穩定）。原因推測：
- VibeVoice ASR 模型對 long-form 中文商業對話的訓練資料覆蓋不足
- 多人快速來回 + 含有大量領域特定詞彙（譬如「賣 A 開 B」「易發票」）增加生成壓力
- vLLM v0.14.1 對長 generation 的 attention / sampling 處理可能有 regression

### 1.3 已採取的緩解

- **長音檔自動切段**（M5 minimal）：`audio_splitter.split_long_audio` 60s threshold、55s chunk + 5s overlap、固定時間切（不做 silence detection）
- **放寬 repetition detection**：`REPETITION_WINDOW_CHARS` 200 → 300、`MIN_SUBSTRING_LEN` 10 → 15、`MIN_OCCURRENCES` 3 → 4
- **parser truncated salvage**：vLLM 串流被截在 segment 中間時、用 `json.JSONDecoder.raw_decode` 救出已完整的前段而非全部丟棄
- **OpenCC s2tw 後處理**：上游模型偏簡體輸出，parser 統一轉繁體（保留 raw_text 原樣）

---

## 二、 v1 API 契約風險（M6 必修）

### 2.1 兩條轉錄路徑差異

| 路徑 | 用途 | partial 處理 |
|---|---|---|
| Admin（M3.5 完成） | 人工標註製作 fine-tune 資料 | 標註人員在 editor 看到 gap、手動補錄或標記 |
| v1 API（M6 範圍、未實作） | QC 系統自動化整合 | **必須對 QC 暴露 partial 狀態，不能默默吞掉** |

目前 backend 對兩條路徑用同一個 `job_runner.run_transcribe` 入口、partial 同樣寫進 `Job.error` 欄位。M6 v1 API 必須依此設計對外契約。

### 2.2 M6 brainstorming 進度（2026-05-10 暫停轉 M5 完整版）

#### 已決議題

| 議題 | 決議 |
|---|---|
| 場景 | B（非同步上傳 + 後續查詢） |
| 主路徑 | WSS /api/v1/transcribe（一次性上傳 + 連線中收結果） |
| 短音檔捷徑 | POST /api/v1/transcribe/sync（≤ 2 分鐘） |
| 斷線 fallback | GET /api/v1/jobs/{id}/result |
| Webhook | M6 不做、留 backlog |
| partial 契約 | **嚴格**（done = 完整覆蓋；partial → failed + 人工介入） |
| raw_text 暴露 | **不對外暴露**（ASR 系統職責是準確率、segments 是最終產品） |

#### 決策原則（重要、之後別忘）

> 我們是 ASR 系統、提高準確率是我們的職責。不該把品質判定推給 QC、也不該透過
> raw_text 暗示「原料思維」。partial fail 比例必須在 ship M6 前降到極低
> （目標 < 3%）。**M5 完整版（partial chunk 自動再切再跑）排在 M6 之前 ship**，
> 否則嚴格契約會頻繁觸發 fail、QC 端體驗差、整套契約失去意義。

#### 未決議題（M5 完整版 ship 後續 M6 brainstorming 再決）

- WS idle timeout（SPEC 暫定 60s + ping/pong）
- Rate limit 策略（內測階段傾向不限）
- Error code 對外暴露範圍（傾向收斂到 6-10 個對外 code）
- partial 觸發 fail 後的具體 response shape
- 是否帶 coverage_pct / gap_ranges metadata（嚴格契約下這些變得不必要、待確認）

### 2.3 原本框架（保留作為決策過程紀錄）

#### M6 brainstorming 必須敲定的決策

#### a. response 欄位設計

response 必須暴露足夠資訊讓 QC 端判斷品質：

```json
{
  "job_id": "xxx",
  "status": "done",
  "segments": [...],
  "partial": true,
  "coverage_pct": 0.85,
  "gap_ranges": [
    {"start": 158.3, "end": 200.0},
    {"start": 226.2, "end": 250.0}
  ]
}
```

`gap_ranges` 計算來源：merge_chunk_results 之後相鄰 segments 之間 `start_time - prev.end_time > threshold`（譬如 5 秒）視為 gap。

#### b. partial 是否算「成功」

兩種設計選擇：

- **嚴格契約**：partial → `status="failed"` + `error_code="incomplete_transcription"`，QC 不會誤把不完整當合格
- **寬鬆契約**：partial → `status="done"` 但 metadata 標 `partial=true`，QC 自行判斷

**目前傾向嚴格**：
- v1 是對外契約，done 應該等於「完整覆蓋」
- QC 端可避免誤把 partial 當完整資料寫入下游
- Admin 端反正自己能看 partial 也能編輯、不需要 v1 那麼嚴格

#### c. QC 端建議處理策略（寫進 SDK doc）

- 接受並標記（譬如該案件人工抽驗）
- 拒絕並重送（用不同 idempotency_key 觸發完整重跑）
- 設品管門檻：`coverage_pct < 0.9` 直接 fallback 人工

### 2.3 內部要把 partial 比例壓低（v1 API 上線前）

即使 v1 API 暴露了 partial 狀態、頻繁失敗實質仍不可用。M6 開工前內部要做：

| 修法 | 預估效益 | 工作量 |
|---|---|---|
| chunk 切短到 30s | partial 比例 15% → < 5%，但處理時間翻倍 | 低（改 .env） |
| partial chunk 自動再切再跑（指數退避） | partial 比例 < 5%、處理時間僅 partial 段 + 雙倍 | 中（改 vllm_client / job_runner） |
| 改 vLLM prompt（譬如不傳 hotwords / 改 system prompt） | 不確定，需 A/B 實測 | 中（改 constants 後實測） |
| 升 vLLM 版本 | 不確定且高風險（vibevoice plugin 跟 v0.14.x 綁定） | 高，**不建議** |

---

## 三、 跨 chunk speaker_id 不對齊

### 現象

現有 `merge_chunk_results` 不做跨 chunk speaker re-mapping，同一說話人在不同 chunk 可能被 vLLM 分配不同 speaker_id。

### 影響

- **Admin 路徑**：標註人員在 editor 手動修正、影響有限
- **v1 API 路徑**：QC 端拿到 speaker 切換錯亂的 transcript、品管難解讀

### 建議實作（M6 brainstorming）

- 簡單做法：跨 chunk 用 acoustic similarity 比對 overlap 區段、推算 speaker mapping
- 進階做法：跑 standalone speaker diarization model 後再 align ASR 結果
- M4 LoRA fine-tune 後若模型本身對 speaker 識別更穩、自然解決一部分

---

## 四、 已知次要 backlog（不阻擋 M4 / M6 起動）

聚焦在「ASR 品質與 v1 API 契約」之外、相關的工程改進：

- **`vllm_client` 錯誤碼粒度**：目前所有 vLLM 4xx/5xx 都歸 `vllm_unavailable`。MP4 demux 失敗那種「用戶資料問題」應歸 `INVALID_AUDIO`、不要混在「服務不可用」內
- **v1 sync transcribe 路徑**：M6 實作時需走同樣的 video demux + 切段邏輯（目前 `routes/v1/transcribe_sync.py` 是 stub、邏輯尚未確定）
- **silence detection 切點**：當前固定時間切，可能切在詞中間。實作 `find_silence_points` 用 ffmpeg silencedetect 找最近的靜音邊界
- **chunk 並行推論**：當前序列、12 chunk 約 60-100 秒。並行可大幅縮短處理時間，但要注意 vLLM connection / memory 上限
- **partial chunk 自動 retry strategy**：當前 retry 是同 chunk 升 temperature；可改成「partial 偵測到後從未轉錄處重切短段再跑」

---

## 五、 重新評估時機

以下事件發生時、應重新審視本文件並調整對應策略：

1. **M4 LoRA fine-tune 完成首版**：模型對本領域對話穩定性提升，重測長音檔覆蓋率，partial 比例可能自然下降到 < 3%。屆時很多 mitigation 可移除
2. **M6 v1 API brainstorming 啟動**：第一個議題就是讀本文件、敲定 2.2 的 a/b/c 決策
3. **vLLM 升版考量**：若團隊決定升 vLLM、要評估 vendor/VibeVoice plugin 相容性、並重測本文件提到的所有 metrics
