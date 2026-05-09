# VibeVoice-ASR 內部部署平台 — 完整實作規格書

**文件版本**：v1.1
**最後更新**：2026-05-09
**狀態**：開發前定稿（已對齊 QC 整合需求）

> **v1.1 主要變更（vs v1.0）**：
> - 砍掉麥克風即時串流（VAD/WebSocket 即時 ASR）
> - 加入「外部整合 API（v1）」：給 QC 系統用，含 WS 音檔上傳、API Key 認證、Webhook callback、Idempotency
> - Job queue 從 in-process BackgroundTasks → **Arq + Redis**（持久化、可擴展）
> - 加入「scale-ready 架構但 hardware-optional」設計原則
> - 加入「長音檔自動切段」規格
> - Milestone 重排：M4 改為「外部整合 API」並後置至 M6

---

## 0. 文件目的與接手須知

### 0.1 這份文件是給誰的

這份規格書是**單一來源**（single source of truth），給以下對象：

1. **接手開發的工程師（含 Claude）**：拿到本文件 + `vendor/VibeVoice/` + `scripts/bootstrap.sh` 即可開始實作，不需要回看對話歷史。
2. **客戶 / 採購決策者**：硬體規格與部署選項見 §4、§5。
3. **PM / 驗收人員**：里程碑與驗收條件見 §14。
4. **QC 整合工程師**：外部 API 規格見 §17（獨立完整章節，可單獨抽出來給 QC 端工程師看）。

### 0.2 開發環境快速理解清單

接手者請先做：

- [ ] **工作目錄**：本文件所在的目錄（任何位置皆可，scripts 會自動偵測）。本文件中以 `<PROJECT_ROOT>` 表示。
- [ ] 上游 repo 已 clone 在：`<PROJECT_ROOT>/vendor/VibeVoice/`（若不存在，`make setup` 會自動 clone）
- [ ] 確認你的開發 / 部署情境（見下表），影響跑哪些指令
- [ ] 跑 setup 指令 → 環境檢查 + 拉 vendor + build images
- [ ] 讀 §0.4 文件結構導覽，跳到 §14 找當前 milestone

#### 三種開發 / 部署情境

| 情境 | dev 主機 | prod 主機 | dev 端要 GPU 嗎 |
|---|---|---|---|
| (a) 全程 Linux/macOS | Linux/macOS | Linux | 需要（要跑完整 vLLM） |
| (b) 全程 Windows | Windows + WSL2 | Windows + WSL2 | 需要（NVIDIA WSL toolkit） |
| **(c)** **dev Windows / prod Linux** | Windows | Linux | **不需**（dev 不啟 vLLM container） |

#### 指令對照表

| 動作 | Linux / macOS | Windows |
|---|---|---|
| 初次設定 | `make setup` | `.\make.ps1 setup` 或 `make setup`（透過 make.bat） |
| 啟動服務 | `make up` | `.\make.ps1 up` |
| 看 log | `make logs-backend` | `.\make.ps1 logs-backend` |
| 停止 | `make down` | `.\make.ps1 down` |
| 部署驗證 | `./scripts/verify_deployment.sh` | `.\make.ps1 verify` |

> Windows 上 `make.ps1`（PowerShell）與 `make.bat`（cmd 包裝）兩種入口都行，功能對齊 Linux 的 `Makefile`。

#### 跨主機可攜性

- Shell scripts 用 `dirname "${BASH_SOURCE[0]}"` 自動偵測 PROJECT_ROOT
- PowerShell scripts 用 `Split-Path -Parent $MyInvocation.MyCommand.Path` 自動偵測
- docker-compose 用 `./vendor`、`./data` 等相對路徑（相對 compose 檔位置）
- 容器內路徑（`/app`、`/data`）由 docker volume mount 提供，與宿主路徑解耦

**移到新主機 SOP**：

```bash
# 來源主機：打包（排除 .claude 與執行期資料）
tar czf vibevoice_asr.tar.gz --exclude=".claude" --exclude="data" vibevoice_asr/

# 新主機 (Linux / macOS)
tar xzf vibevoice_asr.tar.gz
cd vibevoice_asr
git init && git add . && git commit -m "initial"
make setup && make up

# 新主機 (Windows, PowerShell)
# 解壓後
cd vibevoice_asr
git init; git add .; git commit -m "initial"
.\make.ps1 setup
.\make.ps1 up
```

#### 情境 (c) 特別說明（本專案的主要 dev/prod 模式）

dev on Windows / prod on Linux：

- ✅ Windows dev 機**不需要 GPU**：vLLM container 預設不啟（`profiles: ["manual"]`），dev 機只跑 redis + backend + worker + frontend
- ✅ Backend、frontend、worker、redis 在 Windows Docker Desktop 都能跑（皆為 Linux container）
- ✅ M2-M3.5、M6 等純後端/前端邏輯可在 Windows dev 完成，再 push 至 Linux prod 跑 e2e
- ⚠️ M1（vLLM 部署驗證）必須在 Linux prod 機上做
- ⚠️ M4（training）必須在 Linux prod 機上做（GPU 需求）
- 🌟 開發節奏：Windows 寫 + 跑 unit tests → 推到 Linux prod 機跑整合驗收
- 📁 詳細 Windows 注意事項見 §5.6

### 0.3 寫作慣例與符號

| 符號 | 意思 |
|---|---|
| ✅ | 已從上游 source code 驗證 |
| ⚠️ | 需在實作初期驗證（M1/M1.5） |
| 🔬 | 開放問題或待研究 |
| 🌟 | 重要設計決策 |
| 📁 | 上游檔案路徑（`vendor/VibeVoice/...`） |
| 🚧 | scaffold 已建立，待填內容 |

所有 path 預設相對 `<PROJECT_ROOT>`（本文件所在目錄）。容器內路徑（`/app`、`/data` 等）會明確標示。

### 0.4 文件結構導覽

```
§1   專案概述與範圍
§2   上游 VibeVoice 摘要
§3   系統架構
§4   部署 Profiles（含 VRAM 閾值）
§5   硬體規格建議書
§6   vLLM 推論層（含長音檔切段）
§7   Backend 服務層
§8   Frontend 規格
§9   資料格式（訓練 JSON、6 種匯入格式）
§10  訓練流程
§11  （已刪除：原即時串流章節）
§12  Docker / Compose 配置
§13  目錄結構
§14  實施計劃與里程碑
§15  風險登記
§16  安全性
§17  外部整合 API（QC 系統用）⭐
§18  待驗證項目
§19  詞彙表
附錄  上游檔案速查 / 範例 / 故障排除
```

---

## 1. 專案概述

### 1.1 業務目標

打造一個基於 **microsoft/VibeVoice-ASR-7B** 的內部 ASR 服務平台，給語音質檢（QC）系統使用。具備：

- **對外 ASR API（QC 整合）**：WS 音檔上傳、API Key 認證、Webhook 回送、Rich Transcription 結構化結果
- **管理 UI（內部人員用）**：專案/hotwords 管理、上傳測試、校正工作台、訓練、模型版本切換
- **領域微調（LoRA）**：用 QC 業務的真實資料對 base model 做 LoRA fine-tune，提升專有名詞辨識準確度
- **校正工作台**：把 ASR 輸出當訓練資料的起點，編輯後存為 dataset，供下次微調使用

### 1.2 範圍

**In scope**：
- QC 系統可呼叫的外部 API（v1）：WS 上傳 + REST + Webhook
- 管理 UI（內部使用，無需公網部署）
- LoRA 微調流程（資料管理、訓練、合併、版本管理）
- 多種匯入格式（xlsx/csv/srt/vtt/txt/json）
- 部署 profile 抽象（單卡/雙卡/多卡）
- 長音檔自動切段（>55 分鐘）
- API Key 與 Webhook 管理 UI

**Out of scope**：
- ❌ 麥克風即時串流 ASR（離線優先決策）
- ❌ 一般使用者帳號 / SSO（API Key 即足夠 M2M 場景）
- ❌ 多租戶隔離（內部多專案靠 project 邏輯隔離即可）
- ❌ TTS 功能
- ❌ Mobile App
- ❌ 24/7 SLA 保證

### 1.3 利害關係人

| 角色 | 互動 |
|---|---|
| QC 系統 | 透過 §17 外部 API 呼叫，傳音檔取結果 |
| 內部標註人員 | 用校正工作台修正 ASR 結果，產生訓練資料 |
| 內部營運 | 用管理 UI 看歷史、調 hotwords、跑訓練 |
| 開發者 | 接手本文件 + scaffold |
| DevOps | docker compose 部署，看 §4-§5 |
| 客戶採購 | §5 硬體建議書 |

---

## 2. 上游專案 VibeVoice 摘要

### 2.1 上游基本資訊

- **Repo**：https://github.com/microsoft/VibeVoice
- **License**：MIT
- **語言**：Python 100%
- **本機路徑**：`vendor/VibeVoice/`

### 2.2 我們關心的子目錄

| 子目錄 | 用途 | 我們的依賴 |
|---|---|---|
| 📁 `vibevoice/` | 模型核心 | 訓練 container 直接 import |
| 📁 `vllm_plugin/` | vLLM serving plugin | Docker mount，不修改 |
| 📁 `finetuning-asr/` | LoRA 訓練腳本 | 訓練 container 直接呼叫 |
| 📁 `demo/` | Gradio demo | 參考 prompt 格式（不使用） |
| 📁 `docs/` | 官方文件 | 參考 |

### 2.3 模型介紹

| 模型 | HuggingFace ID | 參數量 | 本專案使用 |
|---|---|---|---|
| VibeVoice-ASR-7B | `microsoft/VibeVoice-ASR` | 7B | ✅ |
| VibeVoice-TTS-1.5B | `microsoft/VibeVoice-TTS` | 1.5B | ❌ |
| VibeVoice-Realtime-0.5B | `microsoft/VibeVoice-Realtime` | 0.5B | ❌ |

ASR-7B 關鍵特性：
- 單次最多 60 分鐘音檔 / 64K tokens
- 50+ 種語言
- 內建 speaker diarization
- 支援 customized hotwords / context（透過 prompt 注入）
- 輸出結構化：Start time / End time / Speaker ID / Content

---

## 3. 系統架構

### 3.1 整體架構圖

```
                    外部                          內部
┌──────────────────────────────┐    ┌──────────────────────────────┐
│  QC 系統                      │    │  Browser (內部人員)             │
│  (語音質檢應用)                │    │  Vite + React Admin UI         │
└────────────┬─────────────────┘    └──────────────┬───────────────┘
             │ WSS / HTTPS                          │ HTTPS
             │ + API Key (Subprotocol)              │ (Cookie / 內網)
             │                                      │
   ┌─────────▼────────────┐              ┌──────────▼──────────┐
   │  /api/v1/*           │              │  /api/admin/*        │
   │  (對外，穩定 schema) │              │  (內部，UI 用)       │
   └─────────┬────────────┘              └──────────┬──────────┘
             │                                      │
             ├──────────────┬───────────────────────┤
             │              │                       │
   ┌─────────▼──────────────▼───────────────────────▼──────────┐
   │  Backend (FastAPI)              port 8080                  │
   │  ├─ routes/v1/      ApiKey-authenticated, schema-stable    │
   │  ├─ routes/admin/   internal UI                            │
   │  ├─ services/       vllm_client, queue, auth, webhook,     │
   │  │                  audio_splitter, training_runner, ...   │
   │  └─ db.py           SQLAlchemy + SQLite (可換 Postgres)    │
   └────┬───────────┬────────────┬────────────┬──────────────┘
        │           │            │            │
   ┌────▼─────┐ ┌──▼──────┐  ┌──▼─────┐  ┌──▼──────────────┐
   │  Redis   │ │ Worker  │  │ Docker │  │  Shared Volumes  │
   │ (Arq)    │ │ (Arq)   │  │ Socket │  │  ./data/         │
   │ - jobs   │ │ ─ x N   │  │  ↓     │  │  ├─ jobs/        │
   │ - idem   │ │ pulls   │  │  控    │  │  ├─ datasets/    │
   │ - cache  │ │ jobs    │  │  制    │  │  ├─ loras/       │
   │ - DLQ    │ │         │  │  下方  │  │  ├─ merged/      │
   └──────────┘ └─────────┘  └──┬─────┘  │  ├─ logs/        │
                               │         │  ├─ hf_cache/    │
                               ▼         │  └─ uploads/     │
                    ┌──────────────────┐ └──────────────────┘
                    │ vLLM Container   │
                    │ Always-on        │
                    │ port 8000        │
                    │ OpenAI API       │
                    └──────────────────┘
                    ┌──────────────────┐
                    │ Training Container│
                    │ On-demand         │
                    │ exits when done   │
                    └──────────────────┘
                              │
                              └──── GPU（依 deployment profile 分配）
```

### 3.2 元件職責

| 元件 | 職責 | 不負責 |
|---|---|---|
| **vLLM container** | 推論 model，serve OpenAI API | 業務邏輯、認證、訓練 |
| **Training container** | 跑一次 LoRA fine-tune | 推論、長駐 |
| **Backend (FastAPI)** | 業務邏輯、認證、orchestration | 模型推論本身、UI 渲染 |
| **Worker (Arq)** | 跑非同步 Job：轉錄、合併、Webhook 投遞 | 接 HTTP 請求 |
| **Redis** | Queue、Idempotency 快取、Webhook 重試佇列 | 持久資料 |
| **SQLite/Postgres** | 持久化 metadata（projects、jobs、users…） | 大檔 |
| **Frontend** | 管理 UI | 模型操作 |
| **Shared volume** | 跨 container 檔案交換 | 計算 |

### 3.3 「Scale-ready 架構但 Hardware-optional」設計原則 🌟

「客戶硬體可能升級，但目前架構不能成為瓶頸」。具體做法：

| 設計面 | 強制做（架構面） | 選配（看硬體） |
|---|---|---|
| Backend 是否 stateless | ✅ 必須（in-memory state 一律放 Redis） | — |
| Worker 可水平擴展 | ✅ 必須（Arq 原生支援） | 開幾個是 ENV 設定 |
| vLLM 可多 instance | ✅ 必須（base_url 接受 list，內建簡單 round-robin） | 真開幾個看 GPU |
| DB 介面抽象 | ✅ 必須（SQLAlchemy；換 Postgres 只改 connection string） | 預設 SQLite |
| 檔案儲存抽象 | ✅ 必須（`FileStore` interface：local / S3 / NFS 三種實作預留） | 預設 local volume |
| Webhook 投遞 | ✅ 必須有 retry + DLQ | — |
| Backpressure | ✅ 必須（queue 滿回 429） | — |
| Idempotency | ✅ 必須（Redis 24h 暫存 idempotency_key→job_id） | — |
| 觀測性 | ✅ 必須暴露 `/metrics`（Prometheus 格式） | 客戶自接 |
| 多機部署 | 🌐 預留（架構不阻擋） | 預設單機 |

這些「必須做」的部分**不會大幅增加開發時間**，因為都是「介面抽象 + 配置驅動」，不是真的實作多套後端。

### 3.4 資料流

#### 3.4.1 QC 整合（外部，主要場景）

```
QC 系統                  Backend                   Worker            vLLM
   │ WS connect + auth      │                         │                 │
   │ ──────────────────────>│                         │                 │
   │ <───── ready ──────────│                         │                 │
   │ start metadata         │                         │                 │
   │ ──────────────────────>│                         │                 │
   │ binary chunks ...      │                         │                 │
   │ ──────────────────────>│ (寫入 uploads/ 邊接收)   │                 │
   │ eof                    │                         │                 │
   │ ──────────────────────>│ enqueue job → Redis ───>│                 │
   │ <─── queued + job_id ──│                         │                 │
   │                        │                         │ pull job        │
   │                        │                         │ POST audio ───>│
   │ <─── progress ─────────│ <─── stream ────────────│ <───────────────│
   │ <─── done + segments ──│                         │                 │
   │ (or close)             │                         │                 │
   │                        │       (若提供 callback_url，Worker POST)  │
   │ <─── HTTP POST ────────────────────────────────  │                 │
   │     callback (HMAC簽)                            │                 │
```

#### 3.4.2 Admin UI 離線轉錄（內部，次要）

```
User → Frontend → POST /api/admin/transcribe (multipart)
                  → Backend 寫檔到 data/uploads/
                  → enqueue job → Redis
                  → 回 202 + job_id
       Worker pulls → vllm_client.transcribe → parse → save segments to DB
       Frontend polls GET /api/admin/jobs/{id}
```

#### 3.4.3 訓練（不論 admin 或 v1，目前只有 admin 可觸發）

```
User → 選 dataset items → POST /api/admin/training
       → 建 TrainingRun → 排入 worker
Worker:
  → prepare staging dir (symlink dataset audio + JSON)
  → if !deployment.can_concurrent_train(): stop vLLM
  → docker run training_container ... (CUDA_VISIBLE_DEVICES per profile)
  → tail logs → broadcast via SSE to frontend
  → on done: merge LoRA → save to data/merged/
  → register ModelVersion
  → start vLLM (if was stopped)
```

---

## 4. 部署 Profiles

### 4.1 五種 Profile 與 VRAM 閾值

**閾值規則**：依「**單卡可用 VRAM**」判定。

| Profile 代號 | 單卡 VRAM | 卡數 | 同時訓練+推論 | 推論加速 |
|---|---|---|---|---|
| `single` | **24-79 GB** | 1 | ❌ 訓練時停 vLLM | 單卡 |
| `single-large` | **≥ 80 GB** | 1 | ✅ 同卡共用 | 單卡 |
| `dual-split` | 24-79 GB × 2 | 2 | ✅ GPU0 推論 / GPU1 訓練 | 單卡 |
| `dual-tp` | 24-79 GB × 2 | 2 | ❌ 訓練時 reconfigure | TP=2 雙倍速 |
| `multi` | ≥ 24 GB × 4+ | 4+ | ✅ | DP / TP / 混合 |

### 4.2 為什麼 80GB 是閾值

ASR-7B 同時 serve + train 的 VRAM 需求估算：

| 任務 | VRAM 需求 |
|---|---|
| vLLM 載 ASR-7B 權重（BF16） | ~14 GB |
| vLLM KV cache（max_model_len=64K, max_num_seqs=64） | ~15-20 GB |
| vLLM 額外 buffer / activation | ~3-5 GB |
| **vLLM 小計** | **~32-39 GB** |
| 訓練：權重凍結 + LoRA params | ~14.2 GB |
| 訓練：optimizer states + gradients（LoRA only） | ~0.3 GB |
| 訓練：activation（grad checkpointing） | ~6-10 GB |
| 訓練：dataset / audio buffers | ~1-2 GB |
| **訓練小計** | **~22-27 GB** |
| **同時運行需求** | **~54-66 GB** |

加上記憶體碎片、CUDA context、安全 buffer 約 10-15 GB → **80 GB 為門檻**。

48GB 卡技術上可降低 vLLM `gpu-memory-utilization` 至 0.5 並縮短 `max-model-len` 至 32K 來「擠」進 single-large 行為，但會犧牲長音檔支援（30 分鐘上限）與並發數（max_num_seqs ≤ 16）。本文件**不推薦**這種折衷。

### 4.3 Profile 行為矩陣

| 行為 | single | single-large | dual-split | dual-tp | multi |
|---|---|---|---|---|---|
| 推論時 GPU 使用 | 整卡 | 50-60% | GPU 0 | 兩卡 TP | DP×TP |
| 訓練時 GPU 使用 | 整卡（vLLM 停） | 40-50%（共用） | GPU 1 | 兩卡（vLLM 停） | 部分卡 |
| 訓練前是否需停 vLLM | ✅ 是 | ❌ 否 | ❌ 否 | ✅ 是 | 視 mapping |
| 推論吞吐量（相對） | 1× | 0.7× | 1× | 1.6-1.8× | 2-4× |
| 推論延遲（相對） | 1× | 1.1× | 1× | 0.6× | 0.6× |
| 訓練吞吐量（相對） | 1× | 0.7× | 1× | 1.7× | 2× |
| 對長音檔（60min）支援 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 推薦並發 QC 呼叫 | 5-15 | 30-60 | 15-30 | 60-100 | 100+ |

### 4.4 Profile 切換流程

Profile 透過環境變數 `DEPLOYMENT_PROFILE` 設定，**啟動前決定**，運行中不切換。

```bash
# .env
DEPLOYMENT_PROFILE=dual-split    # single | single-large | dual-split | dual-tp | multi
GPU_INFERENCE_DEVICES=0
GPU_TRAINING_DEVICES=1
VLLM_TENSOR_PARALLEL=1
VLLM_DATA_PARALLEL=1
VLLM_MAX_MODEL_LEN=65536
VLLM_MAX_NUM_SEQS=64
VLLM_GPU_MEMORY_UTILIZATION=0.85
```

backend 啟動時讀取，產生對應 `DeploymentStrategy` 物件，所有「啟停 vLLM」「跑訓練」等動作都委派給 strategy（見 §7.5.6）。

---

## 5. 硬體規格建議書（給客戶）

### 5.1 推薦分級表

| 等級 | GPU 配置 | 對應 Profile | CPU | RAM | 儲存 | 適用 QC 量級 | 一次成本（自建） |
|---|---|---|---|---|---|---|---|
| **PoC / 試用** | 1× RTX 4090 24GB | `single`* | 16C | 64GB | 1TB NVMe | <100 通/天 | $2-3k |
| **標準 / Demo** | 1× RTX 6000 Ada 48GB | `single` | 16C | 64GB | 1TB NVMe | 100-1000 通/天 | $7-9k |
| **小團隊** | 2× RTX 6000 Ada 48GB | `dual-split` | 32C | 128GB | 2TB NVMe | 1000-3000 通/天，可同時訓練 | $14-18k |
| **單卡高階** | 1× H100 NVL 94GB | `single-large` | 32C | 128GB | 2TB NVMe | 3000-5000 通/天 | $30-40k |
| **企業 / 高並行** | 4× H100 80GB SXM (NVLink) | `multi` | 64C | 256GB | 4TB NVMe | 10000+ 通/天 | $120k+ |

*PoC 等級需設定 `VLLM_MAX_MODEL_LEN=32768`，犧牲長音檔支援。

### 5.2 各組件最低 / 建議規格

#### GPU
- **最低**：24 GB VRAM（max_model_len 須降至 32K，僅支援 ≤30 分鐘音檔）
- **建議**：48 GB VRAM（完整 64K context、60 分鐘音檔）
- **計算能力**：Compute Capability ≥ 8.0（Ampere 以上）
- **必需特性**：BF16 / FP16、Flash Attention 2 相容

#### CPU / RAM / 儲存

| 項目 | 最低 | 建議 |
|---|---|---|
| CPU | 8 cores | 16 cores+ |
| RAM | 32 GB | 64 GB+，企業 128 GB+ |
| Storage | NVMe 500 GB | NVMe 1-2 TB |

**儲存容量規劃**：

| 項目 | 大小 |
|---|---|
| Base model（HF cache） | ~14 GB |
| 每個 fine-tuned merged model | ~14 GB |
| LoRA adapter（未合併） | 50-200 MB / 個 |
| 訓練資料（mp3 ~30MB/小時） | 視專案 |
| Job 暫存音檔 | 自動清理（保留 7 天） |
| Backend SQLite + logs | < 1 GB |

#### 網路
- 首次部署需下載 model（~14 GB），建議 100 Mbps+
- 內網部署可離線分發 model

#### 作業系統與軟體
- **OS**：Ubuntu 22.04 LTS（推薦），RHEL 9
- **Driver**：NVIDIA 535+（CUDA 12.1+）
- **Container**：Docker 24+ + NVIDIA Container Toolkit + Compose v2
- **不推薦**：Windows + WSL2

### 5.3 處理時間預估表（給客戶評估容量用）

假設 RTF 0.4×（單卡 vLLM，無 batching 競爭時）：

| 音檔長度 | 預估處理時間 | 適用 endpoint |
|---|---|---|
| 1 min | 24 s | sync |
| 2 min | 48 s | sync (上限) |
| 5 min | 2 min | async |
| 15 min | 6 min | async |
| 30 min | 12 min | async |
| 60 min | 24 min | async |
| 90 min | 36 min + 切段 overhead | async (auto-split) |
| 4 hr | 96 min + 切段 overhead | async (auto-split, 上限) |

**並發吞吐**：vLLM `max_num_seqs=64`，但實務上同時 8-16 個音檔時 RTF 可能上升至 0.8×。

### 5.4 周邊建議

#### 電源 / 散熱
- RTX 6000 Ada：300W TDP / 卡 → 雙卡 1000W+ 80Plus Gold PSU
- H100 80GB SXM：700W TDP → 需專業伺服器機箱與冷卻
- 機房或機櫃環境溫度 ≤25°C

#### UPS / 備援 / 監控
- 訓練中斷電會白做工 → 至少 1500VA UPS、撐 10 分鐘
- Base model 檔案做備份，避免 HF download 失敗
- 建議 `nvidia-smi` exporter + Prometheus + Grafana
- 監控指標：VRAM、溫度、queue 深度、worker lag、Webhook 投遞失敗率

### 5.5 不建議事項（生產環境）

| 項目 | 原因 |
|---|---|
| ❌ RTX 3090 / 4090 跑 24/7 production | 缺 ECC、長時間穩定性差 |
| ❌ 與其他 GPU 服務共用同卡 | 顯存競爭 |
| ❌ HDD 存 model | 載入慢 5-10 倍 |
| ❌ Windows + WSL2 跑 production GPU 工作 | GPU passthrough 偶有問題；建議 prod 用原生 Linux |
| ❌ ARM 架構 | vLLM image 主要為 x86_64 |
| ❌ 跨主機分散式單一推論 | 延遲過高 |

### 5.6 Windows 開發環境（情境 c）

**dev 在 Windows 不跑 GPU**，所以前述「不建議 Windows」僅針對 production。dev-only 場景下 Windows + Docker Desktop 完全可用：

#### 必要軟體

| 軟體 | 版本 | 說明 |
|---|---|---|
| Docker Desktop for Windows | 4.30+ | 內建 docker compose v2 |
| Git for Windows | 任意 | 提供 git；附帶 Git Bash（可選） |
| PowerShell | 5.1+ 或 7+ | Windows 內建；`make.ps1` 直接可跑 |
| Python (host) | 3.11+ | 跑 `qc_simulator.py`、`seed_demo_project.py` |
| Node.js (host, 可選) | 20+ | 用 `make frontend-dev` 在 host 跑 hot-reload |

不需要：
- ❌ NVIDIA driver / CUDA / WSL2 with GPU support（dev 不跑 vLLM）
- ❌ ffmpeg on host（在 backend container 內）
- ❌ make / bash（用 `.\make.ps1` 取代）

#### Docker Desktop 設定建議

- **Resources → CPUs**：≥ 4
- **Resources → Memory**：≥ 8 GB（backend + worker + redis + frontend 同時跑）
- **Resources → Disk image size**：≥ 60 GB
- **General → Use the WSL 2 based engine**：✅ 勾選（必要，Docker Desktop 預設）
- **General → Start Docker Desktop when you log in**：依需求

#### 已知 Windows 注意事項

| 問題 | 解法 |
|---|---|
| Line endings (LF vs CRLF) | `.gitattributes` 不強制 LF；Docker container 內統一 LF 不受影響 |
| Path 大小寫 | docker-compose 用相對 `./` 已避開；HF cache 在容器內 |
| Docker socket mount | `/var/run/docker.sock` 在 Docker Desktop on Windows 自動轉譯，無需改 |
| `chmod +x` 不適用 | Makefile chmod 步驟在 Windows 跳過；PowerShell 端不需 |
| WSL2 backend file IO 慢 | dev 中如遇 hot-reload 慢，把 source code 放在 WSL filesystem (`\\wsl$\...`) 而非 NTFS 可加速 |

#### Windows PowerShell 執行策略

預設 PowerShell 可能擋 `.ps1` 執行。三種解法（任選）：

```powershell
# 選項 1：永久允許當前使用者跑本機 ps1（推薦）
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

# 選項 2：每次 session 暫時允許
powershell -ExecutionPolicy Bypass -File .\make.ps1 setup

# 選項 3：直接用 make.bat（內建 Bypass，最簡單）
make setup
```

#### Windows dev 工作流

```powershell
# 一次性
.\make.ps1 setup

# 每日
.\make.ps1 up
.\make.ps1 logs-backend       # 觀察
.\make.ps1 frontend-dev       # 另一視窗跑前端 hot-reload
.\make.ps1 test               # 跑 unit tests
.\make.ps1 down

# 推到 Linux prod 整合測試
git push origin main
# (在 Linux prod 主機上 git pull && make up && make verify)
```

#### vLLM 在 Windows dev 上的 mock 替代

若需在 Windows dev 上開發推論相關邏輯但無 GPU：

1. **轉錄走 mock**：backend 加 `MOCK_VLLM=true` 環境變數，回傳固定假 segments（建議在 M2 加入）
2. **Stub vLLM container**：寫一個小 FastAPI 模擬 `/v1/chat/completions` 回固定 SSE 流
3. **遠端 vLLM**：把 `VLLM_BASE_URL` 指到 Linux prod 機（須打通網路）

最簡單是 (1)：開發階段用環境變數切換，整合測試到 Linux 跑真實 vLLM。

---

## 6. vLLM 推論層

### 6.1 部署方式

採用上游官方 Docker image，掛載 `vendor/VibeVoice/` 為 `/app`。

**single profile 啟動**（範例）：
```bash
docker run -d --gpus all --name vibevoice-vllm \
  --ipc=host \
  -p 8000:8000 \
  -e VIBEVOICE_FFMPEG_MAX_CONCURRENCY=64 \
  -e PYTORCH_ALLOC_CONF=expandable_segments:True \
  -v $(pwd)/vendor/VibeVoice:/app \
  -v $HOME/.cache/huggingface:/root/.cache/huggingface \
  -v $(pwd)/data/merged:/merged \
  -w /app \
  --entrypoint bash \
  vllm/vllm-openai:v0.14.1 \
  -c "python3 /app/vllm_plugin/scripts/start_server.py"
```

其他 profile 啟動參數見 §12 docker-compose 與 §7.5.6 deployment 模組。

### 6.2 已驗證 API 規格 ✅

來源：📁 `vendor/VibeVoice/vllm_plugin/tests/test_api.py`

**Endpoint**：`POST http://localhost:8000/v1/chat/completions`（OpenAI-compatible）

#### Request Body

```json
{
  "model": "vibevoice",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful assistant that transcribes audio input into text output in JSON format."
    },
    {
      "role": "user",
      "content": [
        {
          "type": "audio_url",
          "audio_url": {"url": "data:audio/wav;base64,<BASE64>"}
        },
        {
          "type": "text",
          "text": "This is a 351.73 seconds audio, with extra info: Tea Brew,Aiden Host,Rent Byte\n\nPlease transcribe it with these keys: Start time, End time, Speaker ID, Content"
        }
      ]
    }
  ],
  "max_tokens": 32768,
  "temperature": 0.0,
  "top_p": 1.0,
  "stream": true
}
```

#### Hotwords 注入規則

- **有 hotwords**：`"This is a {duration:.2f} seconds audio, with extra info: {hotwords}\n\nPlease transcribe it with these keys: Start time, End time, Speaker ID, Content"`
- **無 hotwords**：省略 `with extra info: ...`
- **格式**：hotwords 為**逗號分隔字串**，前端列表存 `["A", "B", "C"]`，送出前 join 成 `"A,B,C"`
- **數量限制**：未明文，但建議 ≤50 個

#### MIME 對照表

| 副檔名 | MIME |
|---|---|
| .wav | audio/wav |
| .mp3 | audio/mpeg |
| .m4a | audio/mp4 |
| .mp4, .mov, .webm | video/mp4 |
| .flac | audio/flac |
| .ogg, .opus | audio/ogg |

#### Response（串流）

標準 OpenAI SSE 格式，accumulate `delta.content` 後得到完整字串。

**完整字串典型結構**（可能被 ` ```json...``` ` 包覆）：
```json
[
  {"Start time": "0.00", "End time": "3.45", "Speaker ID": "1", "Content": "..."},
  {"Start time": "3.45", "End time": "7.20", "Speaker ID": "2", "Content": "..."}
]
```

### 6.3 已驗證輸出解析 ✅

來源：📁 `vendor/VibeVoice/vibevoice/processor/vibevoice_asr_processor.py:490-565`

**Key 對應**：
```python
key_mapping = {
    "Start time": "start_time",
    "Start": "start_time",
    "End time": "end_time",
    "End": "end_time",
    "Speaker ID": "speaker_id",
    "Speaker": "speaker_id",
    "Content": "text",
}
```

**Type 規範**：
- 時間欄位是**字串**（"3.45"）非 float，Backend 解析時轉 float
- Speaker ID 在輸出是 **"1", "2", ...** 字串（**1-indexed**）
- 訓練資料 JSON 的 `speaker` 欄位是 **0, 1, ...** 整數（**0-indexed**）
- 🌟 **匯入/匯出時須做 0-indexed ↔ 1-indexed 轉換**

### 6.4 長音檔自動切段

當音檔 `duration > AUTO_SPLIT_THRESHOLD_SEC`（預設 3300 秒 = 55 分鐘），backend 自動切段：

#### 切段邏輯

```python
# backend/app/services/audio_splitter.py（規格）

def split_long_audio(input_path: Path, max_chunk_sec: int = 3000,
                     overlap_sec: int = 5) -> list[Chunk]:
    """
    1. ffprobe 取總時長
    2. 若 ≤ max_chunk_sec：回傳 [整段]
    3. 否則：
       a. 用 ffmpeg silencedetect 找最接近 chunk 邊界的靜音點
          ffmpeg -i input -af silencedetect=n=-30dB:d=0.5 -f null -
       b. 切成 [0~split1+overlap, split1~split2+overlap, ...]
       c. 用 ffmpeg -ss / -t 切成獨立 mp3 檔
    4. 回傳 [Chunk(path, start_offset_sec, end_offset_sec), ...]
    """

@dataclass
class Chunk:
    path: Path
    start_offset_sec: float  # 在原音檔中的起始時間
    end_offset_sec: float
    is_split: bool           # 是否為切段結果
```

#### 結果合併

```python
def merge_chunk_results(chunks: list[Chunk],
                        chunk_segments: list[list[Segment]]) -> list[Segment]:
    """
    1. 對每個 chunk 的 segments，把時間 offset 加回原音檔時間軸
    2. Overlap 區段（相鄰 chunk 重疊 5 秒內）：
       - 取後一個 chunk 第一個落在 overlap 內 segment 的開始
       - 截斷前一個 chunk 最後一個落在 overlap 內 segment 的結尾
       - 若兩段文字幾乎相同，丟掉重複那段
    3. Speaker re-mapping (best-effort):
       - chunk[i] 的 Speaker 1/2... 與 chunk[i-1] 末尾 5 秒 segment 比對
       - 用音色 embedding 不可行（沒模型），改用 heuristics:
         * 若 overlap 內兩 chunk 都偵測到 speaker，假設順序對應
         * 否則保留各 chunk 獨立編號（前綴標 chunk 號）
    4. 排序 by start_time，回傳合併結果
    """
```

#### 已知 trade-off（要在 §17 揭露給 QC）

- ⚠️ Speaker 連續性 best-effort，可能斷裂
- ⚠️ Chunk 邊界詞句可能輕微重複（後處理試圖 dedup）
- ⚠️ Hotwords 對每段都生效

### 6.5 已知問題與對策

| 問題 | 來源 | 對策 |
|---|---|---|
| 長音檔可能進入「重複迴圈」 | 📁 `test_api_auto_recover.py` | 偵測重複 → temperature 0.2/0.3/0.4 重試 |
| 影片檔 (.mp4 等) | vLLM 內部 ffmpeg 處理 | 可不額外處理；backend 仍應驗證可解碼 |
| First-token 延遲（冷啟動） | 模型載入 | container always-on、warmup with dummy audio |
| 中文 hotwords 效果 ⚠️ | 待驗證 | M1 用中文音檔測試 |

### 6.6 模型切換流程

當使用者切換專案的 active model：

```
1. 檢查 target ModelVersion 路徑
   - 若 type=base：路徑 = "microsoft/VibeVoice-ASR" (HF)
   - 若 type=merged：路徑 = data/merged/{project_id}/{run_id}/

2. 比對目前 vLLM container 載入的 path
   - 從 /v1/models 查詢
   - 相同 → 跳過

3. 不同 → 重啟 vLLM
   a. docker stop vibevoice-vllm
   b. docker rm vibevoice-vllm
   c. docker run ... -v <new_path>:/model ...
   d. wait_for_ready: poll /v1/models 直到 200 OK，timeout 120 秒

4. 更新 Project.active_model_id

5. 通知前端（SSE broadcast）
```

預估切換時間：30-90 秒。

### 6.7 ⚠️ 待驗證：vLLM 動態 LoRA

vLLM 原生支援 `--enable-lora --max-loras N --lora-modules name=path`，可動態載入 adapter，免重啟。

**M1.5 驗證**：此 flag 是否與 VibeVoice plugin 相容（multimodal model 的 LoRA 支援）。

- 成功 → §6.6 多一條快速路徑（不重啟切 model），可同時 serve 多個專案 adapter
- 失敗 → 維持 §6.6 merge & swap

---

## 7. Backend 服務層

### 7.1 技術選型

| 項目 | 選擇 | 理由 |
|---|---|---|
| Framework | FastAPI 0.110+ | async、OpenAPI、WebSocket |
| Python | 3.11+ | match 上游 |
| ORM | SQLAlchemy 2.0 + Alembic | 主流，可換 DB |
| DB | SQLite 3.40+（預設）/ Postgres（生產可選） | 介面一致 |
| **Queue** | **Arq 0.25+ (Redis)** | async-native、輕量、適合 FastAPI |
| **Cache / Idempotency** | **Redis 7+** | 與 queue 共用 |
| HTTP client | httpx + aiohttp | async streaming |
| Docker control | docker SDK for python | 啟停 vLLM / 跑 training |
| Audio | librosa + soundfile + ffmpeg-python | 預檢、切段 |
| Logging | structlog | 結構化 JSON log |
| Metrics | prometheus_client | `/metrics` endpoint |
| Testing | pytest + pytest-asyncio | 標準 |

### 7.2 資料模型（DB Schema）

```python
# backend/app/models.py

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, DateTime, JSON, ForeignKey, Enum, Float, Text, Boolean, UniqueConstraint
from datetime import datetime
import enum, uuid

# === Enums ===

class JobStatus(str, enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

class JobSource(str, enum.Enum):
    ADMIN_UPLOAD = "admin_upload"        # 內部 UI 上傳
    V1_API_ASYNC = "v1_api_async"        # QC 系統呼叫，非同步
    V1_API_SYNC = "v1_api_sync"          # QC 系統呼叫，同步
    V1_API_WS = "v1_api_ws"              # QC 系統 WS 上傳

class TrainingStatus(str, enum.Enum):
    PENDING = "pending"
    PREPARING = "preparing"
    TRAINING = "training"
    MERGING = "merging"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

class ModelType(str, enum.Enum):
    BASE = "base"
    MERGED = "merged"
    LORA = "lora"

class DatasetSource(str, enum.Enum):
    UPLOADED = "uploaded"
    FROM_TRANSCRIPTION = "from_transcription"
    IMPORTED_XLSX = "imported_xlsx"
    IMPORTED_CSV = "imported_csv"
    IMPORTED_SRT = "imported_srt"
    IMPORTED_VTT = "imported_vtt"
    IMPORTED_TXT = "imported_txt"
    IMPORTED_JSON = "imported_json"

class WebhookDeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    GIVEN_UP = "given_up"  # 重試上限後放棄

# === Tables ===

class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    hotwords: Mapped[list[str]] = mapped_column(JSON, default=list)
    active_model_id: Mapped[int | None] = mapped_column(ForeignKey("model_versions.id"))
    webhook_url: Mapped[str | None] = mapped_column(String(500))
    webhook_secret: Mapped[str | None] = mapped_column(String(64))  # 用於 HMAC
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ApiKey(Base):
    """QC 系統用的 API key。一個 project 可有多個 key（dev/staging/prod）。"""
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)  # "qc_prod"
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # SHA-256
    key_prefix: Mapped[str] = mapped_column(String(8), nullable=False)  # 前 4 碼，UI 顯示
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_used_at: Mapped[datetime | None]
    expires_at: Mapped[datetime | None]


class IntegrationCall(Base):
    """記錄每次 v1 API 呼叫，給 admin UI 看「最近呼叫」用。"""
    __tablename__ = "integration_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id"))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"))
    endpoint: Mapped[str] = mapped_column(String(100))  # "/api/v1/transcribe"
    method: Mapped[str] = mapped_column(String(10))     # "POST" / "WS"
    status_code: Mapped[int]
    duration_ms: Mapped[int]
    source_ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(200))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    source: Mapped[JobSource] = mapped_column(Enum(JobSource))
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id"))
    idempotency_key: Mapped[str | None] = mapped_column(String(100), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    audio_path: Mapped[str] = mapped_column(String(500))  # data/uploads/{job_id}/audio.ext
    duration_sec: Mapped[float | None]
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.PENDING)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    chunks_total: Mapped[int] = mapped_column(Integer, default=1)  # 1 = 不切段
    chunks_done: Mapped[int] = mapped_column(Integer, default=0)
    segments: Mapped[list[dict] | None] = mapped_column(JSON)
    raw_text: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    used_hotwords: Mapped[list[str]] = mapped_column(JSON, default=list)
    used_model_id: Mapped[int | None] = mapped_column(ForeignKey("model_versions.id"))
    callback_url: Mapped[str | None] = mapped_column(String(500))  # v1 API 帶來的
    metadata_extra: Mapped[dict | None] = mapped_column(JSON)  # QC 端帶的自訂欄位
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key", name="uq_job_idempotency"),
    )


class WebhookDelivery(Base):
    """Webhook callback 投遞記錄（含重試）。"""
    __tablename__ = "webhook_deliveries"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    url: Mapped[str] = mapped_column(String(500))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[WebhookDeliveryStatus] = mapped_column(Enum(WebhookDeliveryStatus), default=WebhookDeliveryStatus.PENDING)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None]
    last_response_code: Mapped[int | None]
    last_response_body: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    delivered_at: Mapped[datetime | None]


class DatasetItem(Base):
    __tablename__ = "dataset_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    audio_path: Mapped[str] = mapped_column(String(500))
    label: Mapped[dict] = mapped_column(JSON)
    duration_sec: Mapped[float]
    source: Mapped[DatasetSource] = mapped_column(Enum(DatasetSource))
    source_job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TrainingRun(Base):
    __tablename__ = "training_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    status: Mapped[TrainingStatus] = mapped_column(Enum(TrainingStatus), default=TrainingStatus.PENDING)
    hyperparams: Mapped[dict] = mapped_column(JSON)
    dataset_item_ids: Mapped[list[int]] = mapped_column(JSON)
    output_path: Mapped[str | None] = mapped_column(String(500))
    merged_path: Mapped[str | None] = mapped_column(String(500))
    log_path: Mapped[str] = mapped_column(String(500))
    metrics: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))  # null = base
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[ModelType] = mapped_column(Enum(ModelType))
    path: Mapped[str] = mapped_column(String(500))
    training_run_id: Mapped[str | None] = mapped_column(ForeignKey("training_runs.id"))
    size_gb: Mapped[float | None]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

### 7.3 REST API 規格（Admin）

#### 約定

- Base path：`/api/admin`
- 認證：內網存取，無認證（部署時可在 nginx 層加 IP 白名單）
- Content-Type：`application/json`（除 multipart）
- 錯誤格式：`{"detail": "錯誤訊息", "code": "error_code"}`

#### 7.3.1 Projects

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/admin/projects` | - | `200 [Project, ...]` |
| POST | `/api/admin/projects` | `{name, description?, hotwords?, webhook_url?}` | `201 Project` |
| GET | `/api/admin/projects/{id}` | - | `200 Project` |
| PUT | `/api/admin/projects/{id}` | `{name?, description?, hotwords?, webhook_url?}` | `200 Project` |
| DELETE | `/api/admin/projects/{id}` | - | `204` |

#### 7.3.2 Hotwords（捷徑）

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/admin/projects/{id}/hotwords` | - | `200 string[]` |
| PUT | `/api/admin/projects/{id}/hotwords` | `string[]` | `200 string[]` |

#### 7.3.3 API Keys

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/admin/projects/{id}/api_keys` | - | `200 [ApiKey, ...]` (不含 plain key) |
| POST | `/api/admin/projects/{id}/api_keys` | `{name, expires_at?}` | `201 {key, ...ApiKey}` (**唯一一次回 plain key**) |
| DELETE | `/api/admin/api_keys/{id}` | - | `204` (撤銷) |
| POST | `/api/admin/api_keys/{id}/rotate` | - | `200 {key, ...ApiKey}` (產新 key、舊 key 立即失效) |

#### 7.3.4 Webhook 設定

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/admin/projects/{id}/webhook` | - | `200 {url, secret_prefix, retry_policy}` |
| PUT | `/api/admin/projects/{id}/webhook` | `{url, retry_policy?}` | `200 {url, secret, ...}` (新建 secret 才回 plain) |
| POST | `/api/admin/projects/{id}/webhook/rotate_secret` | - | `200 {secret}` |
| POST | `/api/admin/projects/{id}/webhook/test` | `{}` | `200 {success, response_code, response_body}` |

#### 7.3.5 Jobs

| Method | Path | Body / Query | Response |
|---|---|---|---|
| POST | `/api/admin/transcribe` | `multipart: file, project_id` | `202 {job_id}` |
| GET | `/api/admin/jobs/{id}` | - | `200 Job` |
| GET | `/api/admin/jobs?project_id=&source=&status=` | - | `200 [Job, ...]` |
| GET | `/api/admin/jobs/{id}/audio` | - | 音檔串流 |
| DELETE | `/api/admin/jobs/{id}` | - | `204` |
| POST | `/api/admin/jobs/{id}/cancel` | - | `200 Job` |

#### 7.3.6 Datasets

| Method | Path | Body / Query | Response |
|---|---|---|---|
| GET | `/api/admin/datasets?project_id=X` | - | `200 [DatasetItem, ...]` |
| GET | `/api/admin/datasets/{id}` | - | `200 DatasetItem` |
| POST | `/api/admin/datasets/import` | `multipart: audio, label, project_id, format` | `201 DatasetItem` |
| POST | `/api/admin/datasets/from_job/{job_id}` | `{notes?}` | `201 DatasetItem` |
| PUT | `/api/admin/datasets/{id}` | `{label, notes?}` | `200 DatasetItem` |
| DELETE | `/api/admin/datasets/{id}` | - | `204` |
| GET | `/api/admin/datasets/{id}/audio` | - | 音檔串流 |
| GET | `/api/admin/datasets/templates/{format}` | - | 範本下載 |
| GET | `/api/admin/datasets/{id}/export?format=` | - | 匯出 |

#### 7.3.7 Training

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/admin/training?project_id=X` | - | `200 [TrainingRun, ...]` |
| POST | `/api/admin/training` | `{project_id, dataset_item_ids[], hyperparams}` | `201 TrainingRun` |
| GET | `/api/admin/training/{run_id}` | - | `200 TrainingRun` |
| GET | `/api/admin/training/{run_id}/log` | - | `text/event-stream` (SSE) |
| POST | `/api/admin/training/{run_id}/cancel` | - | `200 TrainingRun` |

#### 7.3.8 Model Versions

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/admin/projects/{id}/models` | - | `200 [ModelVersion, ...]` |
| POST | `/api/admin/projects/{id}/active_model` | `{model_version_id: number \| null}` | `200 Project` |
| DELETE | `/api/admin/models/{id}` | - | `204` |

#### 7.3.9 Integration Calls（活動紀錄）

| Method | Path | Query | Response |
|---|---|---|---|
| GET | `/api/admin/integration_calls?project_id=&limit=&offset=` | - | `200 [IntegrationCall, ...]` |

#### 7.3.10 System

| Method | Path | Response |
|---|---|---|
| GET | `/api/admin/system/health` | `200 {ok, vllm_status, redis_status, db_status}` |
| GET | `/api/admin/system/vllm_status` | `200 {status, model, uptime_sec}` |
| GET | `/api/admin/system/profile` | `200 {profile, gpu_devices, ...}` |
| GET | `/api/admin/system/gpu` | `200 [{index, name, mem_used, mem_total, utilization, temp}, ...]` |
| GET | `/api/admin/system/queue` | `200 {pending, running, workers, oldest_age_sec}` |
| GET | `/metrics` | Prometheus exposition format |

### 7.4 外部整合 API（v1）

詳見 §17 整章。本節只列 endpoint 概要：

| Method | Path | 用途 |
|---|---|---|
| WS | `/api/v1/transcribe` | 主路徑：WS 上傳音檔 + 取結果 |
| POST | `/api/v1/transcribe/sync` | 短音檔同步 (≤2 分鐘) |
| POST | `/api/v1/transcribe/url` | 預留：QC 給 URL 我們去拉（v2，目前不實作） |
| GET | `/api/v1/jobs/{id}` | 查狀態（idempotent，可 polling） |
| GET | `/api/v1/jobs/{id}/result` | 取結果（穩定 schema） |
| GET | `/api/v1/openapi.json` | OpenAPI spec（給 QC 端生 client SDK） |

### 7.5 服務模組

#### 7.5.1 vllm_client

```python
# backend/app/services/vllm_client.py

class VllmClient:
    def __init__(self, base_url: str | list[str], max_retries: int = 3):
        """base_url 可為 list（多 vLLM instance round-robin）"""
    
    async def transcribe(self, audio_bytes: bytes, mime: str,
                         duration_sec: float, hotwords: list[str] | None = None,
                         on_token: Callable[[str], None] | None = None) -> dict:
        """回傳 {raw_text, segments, elapsed_sec, attempts}"""
    
    async def health(self) -> bool: ...
    async def get_loaded_model(self) -> str: ...
```

**Auto-recovery 邏輯**（移植 📁 `vllm_plugin/tests/test_api_auto_recover.py`）：
- 串流期間維護 last 200 字 sliding window
- 偵測：相同 ≥10 字 substring 連續出現 ≥3 次
- 觸發 → 重試 with temperature 0.2/0.3/0.4，max 3 次
- 超過則回傳已生成內容 + `partial: true`

#### 7.5.2 queue（Arq integration）

```python
# backend/app/services/queue.py

from arq import create_pool
from arq.connections import RedisSettings

REDIS_SETTINGS = RedisSettings.from_dsn(os.getenv("REDIS_URL"))

# Job functions（worker 端會註冊）
async def transcribe_job(ctx, job_id: str): ...
async def training_job(ctx, run_id: str): ...
async def webhook_delivery_job(ctx, delivery_id: int): ...
async def merge_lora_job(ctx, run_id: str): ...

# 排入 queue
async def enqueue_transcribe(job_id: str) -> str:
    pool = await create_pool(REDIS_SETTINGS)
    await pool.enqueue_job("transcribe_job", job_id, _job_id=job_id)
    return job_id
```

**Queue 設定**：
- `max_jobs` per worker：依 deployment.vllm_max_concurrent_requests 設定
- `keep_result`：300 秒
- `retry`：3 次（webhook 例外，最多 10 次 exponential backoff）

#### 7.5.3 auth

```python
# backend/app/services/auth.py

import hashlib, secrets

KEY_PREFIX = "vva_"
KEY_LENGTH = 32  # 隨機部分

def generate_api_key() -> tuple[str, str, str]:
    """回傳 (plain_key, key_hash, key_prefix)"""
    rand = secrets.token_urlsafe(24)[:KEY_LENGTH]
    plain = f"{KEY_PREFIX}{rand}"
    key_hash = hashlib.sha256(plain.encode()).hexdigest()
    key_prefix = plain[:8]  # "vva_xxxx"
    return plain, key_hash, key_prefix

async def authenticate(key_or_token: str) -> ApiKey:
    """驗證 API key，回傳 ApiKey 物件，更新 last_used_at"""
    key_hash = hashlib.sha256(key_or_token.encode()).hexdigest()
    api_key = await db.get_by_hash(ApiKey, key_hash)
    if not api_key or not api_key.is_active:
        raise AuthError("Invalid or revoked API key")
    if api_key.expires_at and api_key.expires_at < datetime.utcnow():
        raise AuthError("API key expired")
    api_key.last_used_at = datetime.utcnow()
    return api_key

# FastAPI dependency
async def require_api_key(authorization: str | None = Header(None)) -> ApiKey:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, {"code": "missing_auth", "detail": "..."})
    return await authenticate(authorization[7:])

# WS subprotocol auth
def parse_ws_subprotocol(subprotocol: str | None) -> str:
    """從 'bearer.vva_xxx' 抽出 key"""
    if not subprotocol or not subprotocol.startswith("bearer."):
        raise AuthError("Invalid subprotocol")
    return subprotocol[7:]
```

#### 7.5.4 webhook

```python
# backend/app/services/webhook.py

import hmac, hashlib, json, time

def sign_payload(payload: dict, secret: str) -> tuple[str, str]:
    """回傳 (signature, timestamp)"""
    timestamp = str(int(time.time()))
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    msg = f"{timestamp}.{body}".encode()
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    return f"sha256={sig}", timestamp

async def deliver(delivery_id: int):
    """
    投遞單筆 webhook，含 retry。
    Retry policy:
      - attempts: 1 → 30s → 5min → 30min → 2h → 6h → 12h → give_up
      - max attempts: 7
    成功（2xx）標記 SUCCEEDED；失敗排下次重試
    """
    delivery = await db.get(WebhookDelivery, delivery_id)
    project = await db.get(Project, delivery.job.project_id)
    
    sig, ts = sign_payload(delivery.payload, project.webhook_secret)
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": sig,
        "X-Webhook-Timestamp": ts,
        "X-Webhook-Event": "transcription.completed",
    }
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(delivery.url, json=delivery.payload, headers=headers)
        delivery.last_response_code = resp.status_code
        delivery.last_response_body = resp.text[:1000]
        if 200 <= resp.status_code < 300:
            delivery.status = WebhookDeliveryStatus.SUCCEEDED
            delivery.delivered_at = datetime.utcnow()
        else:
            schedule_retry(delivery)
    except Exception as e:
        delivery.last_error = str(e)
        schedule_retry(delivery)
```

#### 7.5.5 audio_splitter

見 §6.4。

```python
# backend/app/services/audio_splitter.py

@dataclass
class Chunk:
    path: Path
    start_offset_sec: float
    end_offset_sec: float
    is_split: bool

def split_long_audio(input_path: Path, max_chunk_sec: int = 3000,
                     overlap_sec: int = 5) -> list[Chunk]: ...

def merge_chunk_results(chunks: list[Chunk],
                        chunk_segments: list[list[Segment]]) -> list[Segment]: ...
```

#### 7.5.6 deployment

```python
# backend/app/services/deployment.py

class DeploymentStrategy(Protocol):
    profile: str
    def vllm_docker_run_args(self, model_path: str) -> list[str]: ...
    def can_concurrent_train(self) -> bool: ...
    def training_gpu_devices(self) -> str: ...
    def vllm_max_concurrent_requests(self) -> int: ...

# 五個實作：SingleGPU / SingleLargeGPU / DualSplit / DualTP / Multi
# 詳見原 v1.0 規格 §7.5.6（無變動）

def make_strategy() -> DeploymentStrategy:
    profile = os.getenv("DEPLOYMENT_PROFILE", "single")
    return {
        "single": SingleGPU,
        "single-large": SingleLargeGPU,
        "dual-split": DualSplit,
        "dual-tp": DualTP,
        "multi": Multi,
    }[profile]()
```

#### 7.5.7 docker_ctrl

```python
# backend/app/services/docker_ctrl.py

import docker

class DockerCtrl:
    def __init__(self):
        self.client = docker.DockerClient(base_url=os.getenv("DOCKER_HOST", "unix:///var/run/docker.sock"))
    
    async def stop_vllm(self): ...
    async def start_vllm(self, deployment: DeploymentStrategy, model_path: str): ...
    async def restart_vllm_with_model(self, deployment, model_path: str): ...
    async def run_training(self, deployment, run_id: str, command: list[str], 
                           volumes: dict, env: dict) -> AsyncIterator[str]:
        """回傳 log line iterator"""
    async def run_merge(self, run_id: str, adapter_path: Path, output_path: Path): ...
```

**安全限制**：DockerCtrl 只能控制白名單 image / container name：
```python
ALLOWED_CONTAINERS = {"vibevoice-vllm"}
ALLOWED_IMAGES = {"vllm/vllm-openai", "vibevoice-train"}
```

#### 7.5.8 file_store

```python
# backend/app/services/file_store.py

class FileStore(Protocol):
    async def save(self, key: str, data: bytes | AsyncIterator[bytes]) -> str: ...
    async def open(self, key: str) -> AsyncIterator[bytes]: ...
    async def delete(self, key: str) -> None: ...
    async def exists(self, key: str) -> bool: ...
    def url_for(self, key: str) -> str: ...

class LocalFileStore(FileStore):
    """預設實作：寫到 BACKEND_DATA_DIR"""

# 預留：S3FileStore, NfsFileStore（不實作）
```

#### 7.5.9 其他 services

- `parser.py`：解析 vLLM 輸出（§6.3 key mapping）
- `dataset_importer.py`：6 種格式匯入 → 訓練 JSON（§9.2）
- `training_runner.py`：訓練 orchestration（§10）
- `job_runner.py`：轉錄 Job 主流程（呼叫 splitter → vllm_client → parser → enqueue webhook）

### 7.6 配置與環境變數

```bash
# === Deployment ===
DEPLOYMENT_PROFILE=single                  # single | single-large | dual-split | dual-tp | multi
GPU_INFERENCE_DEVICES=0
GPU_TRAINING_DEVICES=0

# === vLLM ===
VLLM_BASE_URL=http://vibevoice-vllm:8000   # 或逗號分隔多個
VLLM_CONTAINER_NAME=vibevoice-vllm
VLLM_TENSOR_PARALLEL=1
VLLM_DATA_PARALLEL=1
VLLM_MAX_MODEL_LEN=65536
VLLM_MAX_NUM_SEQS=64
VLLM_GPU_MEMORY_UTILIZATION=0.85
VLLM_DEFAULT_MODEL=microsoft/VibeVoice-ASR
VLLM_DOCKER_IMAGE=vllm/vllm-openai:v0.14.1

# === Backend ===
BACKEND_PORT=8080
BACKEND_DB_URL=sqlite:////data/app.db
BACKEND_LOG_LEVEL=INFO
BACKEND_DATA_DIR=/data
BACKEND_MAX_UPLOAD_MB=500

# === Audio ===
MAX_AUDIO_DURATION_SEC=14400               # 4 小時硬上限
AUTO_SPLIT_THRESHOLD_SEC=3300              # 55 分鐘以上自動切
SPLIT_CHUNK_DURATION_SEC=3000              # 50 分鐘一段
SPLIT_OVERLAP_SEC=5
SYNC_AUDIO_MAX_DURATION_SEC=120            # /api/v1/transcribe/sync 上限

# === Redis / Queue ===
REDIS_URL=redis://redis:6379/0
WORKER_MAX_JOBS=8                          # 每 worker 並行 job 數
WS_IDLE_TIMEOUT_SEC=60

# === Training ===
TRAIN_DOCKER_IMAGE=vibevoice-train:latest

# === HF ===
HF_HOME=/data/hf_cache
HF_HUB_OFFLINE=0

# === Webhook ===
WEBHOOK_TIMEOUT_SEC=30
WEBHOOK_MAX_ATTEMPTS=7

# === API Key ===
API_KEY_PREFIX=vva_
API_KEY_LENGTH=32

# === Idempotency ===
IDEMPOTENCY_TTL_SEC=86400                  # 24 hr

# === Observability ===
METRICS_ENABLED=true
```

---

## 8. Frontend 規格

### 8.1 技術選型

| 項目 | 選擇 | 版本 |
|---|---|---|
| Build | Vite | 5+ |
| Framework | React + TypeScript | 18 / 5+ |
| Routing | React Router | 6 |
| State | Zustand | 4+ |
| Styling | Tailwind CSS | 3 |
| HTTP | fetch + 自寫 wrapper | - |
| Audio | wavesurfer.js + Regions plugin | 7 |
| Charts | recharts | 2+ |
| Forms | react-hook-form + zod | - |
| Icons | lucide-react | - |

### 8.2 路由與頁面

```
/ ─────────────────────────  專案列表
/projects/:id/hotwords      Hotwords 編輯
/projects/:id/offline       離線轉錄（含 Job 列表）
/projects/:id/datasets      資料集管理
/projects/:id/edit/:itemId  校正工作台 ⭐
/projects/:id/training      訓練（list + new）
/projects/:id/training/:runId  訓練詳情
/projects/:id/models        模型管理
/projects/:id/api_keys      API Keys 管理 🆕
/projects/:id/webhook       Webhook 設定 🆕
/projects/:id/integration_calls  整合呼叫紀錄 🆕
/system                     系統狀態
```

### 8.3 各頁規格

由於頁面內容變動小，這節只列**新增的三頁**，其餘參見 v1.0 規格內容。

#### 8.3.x API Keys 管理（新增）

```
專案：客服質檢

API Keys：
┌──────────────────────────────────────────────────────────┐
│ qc_prod    vva_a1b2 ●●●●●●●●●●  建立 5/9  上次用 5 分鐘前│
│            [輪換][撤銷]                                   │
│ qc_test    vva_x9y8 ●●●●●●●●●●  建立 5/8  從未使用      │
│            [輪換][撤銷]                                   │
└──────────────────────────────────────────────────────────┘
[+ 新增 API Key]

▼ 新增彈窗：
  名稱:        [qc_staging        ]
  過期日:      [2027-05-09]   □ 永久有效
  [取消] [建立]

▼ 建立成功彈窗（唯一一次顯示完整 key）：
  ⚠️ 請立即複製，此 key 不會再次顯示
  vva_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
  [📋 複製]  [我已複製]
```

#### 8.3.x Webhook 設定（新增）

```
專案：客服質檢

Webhook URL:  [https://qc.example.com/asr-callback     ]
Secret:        ●●●●●●●●●●●●●●●● (前 8 碼: a1b2c3d4)  [輪換]
Retry policy:  ☑ 失敗時重試 (最多 7 次, exponential backoff)

[儲存] [立即測試]

▼ 立即測試結果：
  ✅ HTTP 200 (124 ms)
  Response: {"received": true}
```

#### 8.3.x 整合呼叫紀錄（新增）

```
專案：客服質檢   篩選：[最近 24 小時 ▼] [全部 status ▼]

┌──────────────────────────────────────────────────────────────┐
│ 時間       Source IP       Endpoint              Status   耗時│
├──────────────────────────────────────────────────────────────┤
│ 14:30:15   10.1.2.3       WS /api/v1/transcribe  200      4.2s│
│ 14:29:08   10.1.2.3       POST /jobs/abc/result  200      12ms│
│ 14:28:55   10.1.2.3       WS /api/v1/transcribe  202      -   │
│ 14:25:30   10.1.2.4       POST /transcribe/sync  429      8ms │
│            └─ rate limited                                    │
│ 14:20:11   10.1.2.3       WS /api/v1/transcribe  401      2ms │
│            └─ invalid api key                                 │
└──────────────────────────────────────────────────────────────┘

[載入更多]
```

#### 8.3.x 離線頁更新（新增「來源」欄位）

`/projects/:id/offline` 頁的 Job 列表加 source 標籤：

```
┌─────────────────────────────────────────────────────────────┐
│ 🌐 V1-WS    14:30   patient_001.mp3   done       12 min     │
│ 👤 ADMIN    14:25   meeting.m4a       done        8 min     │
│ 🌐 V1-SYNC  14:20   short.wav         done        2 sec     │
└─────────────────────────────────────────────────────────────┘
```

其餘頁面（校正工作台、訓練、模型、資料集）規格無變動。

### 8.4 共用元件

無變動：TranscriptViewer、TranscriptEditor、WaveformPlayer、HotwordsChips、JobList、Sidebar。

新增：
- `ApiKeyDisplay`：顯示 prefix + masked
- `WebhookTestResult`：呼叫 `/webhook/test` 並顯示結果
- `IntegrationCallsTable`：紀錄列表

---

## 9. 資料格式

### 9.1 標準訓練 JSON 🌟

來源：📁 `vendor/VibeVoice/finetuning-asr/toy_dataset/0.json`

```json
{
  "audio_duration": 351.73,
  "audio_path": "0.mp3",
  "segments": [
    {"speaker": 0, "text": "Hey everyone...", "start": 0.0, "end": 38.68},
    {"speaker": 1, "text": "Thanks...",       "start": 38.75, "end": 77.88}
  ],
  "customized_context": ["Tea Brew", "Aiden Host"]
}
```

**欄位定義**：

| 欄位 | 型別 | 必需 | 說明 |
|---|---|---|---|
| `audio_duration` | float (sec) | ✅ | 音檔總長 |
| `audio_path` | string | ✅ | 相對檔名 |
| `segments` | array | ✅ | 段落 |
| `segments[].speaker` | int (**0-indexed**) | ✅ | 講者 |
| `segments[].text` | string | ✅ | 文字 |
| `segments[].start` | float (sec) | ✅ | 開始 |
| `segments[].end` | float (sec) | ✅ | 結束 |
| `customized_context` | string array | ⬜ | hotwords |

**約束**：segments 升冪、無 overlap、speaker 0-indexed 可不連續。

### 9.2 多格式匯入規格

| 格式 | 副檔名 | 必需欄位 | 解析庫 |
|---|---|---|---|
| Excel | .xlsx | start_time, end_time, speaker, text | openpyxl |
| CSV | .csv | 同上 | pandas |
| SRT | .srt | timestamps + text (Speaker N: prefix optional) | pysrt |
| VTT | .vtt | 同上 | webvtt-py |
| JSON | .json | §9.1 schema | 內建 |
| TXT | .txt | `[00:00:00.00] Speaker N: text` 一行一段 | 自寫 regex |

#### Excel 範本

```
| start_time | end_time   | speaker | text                          |
|------------|------------|---------|-------------------------------|
| 0.00       | 3.45       | 0       | 各位早安，今天我們要討論糖尿病  |
| 0:00:03.45 | 0:00:07.20 | 1       | 是的，胰島素分泌不足是主因      |
```

時間支援格式：
- 浮點秒數：`3.45`, `120.5`
- `hh:mm:ss[.ms]`：`0:00:03.45`, `1:23:45`
- `mm:ss[.ms]`：`3:45.5`

Speaker 容錯：
- 純數字 `0`, `1`：直接用（0-indexed）
- 字串 `"Speaker 1"`：抽數字、轉 0-indexed（→ 0）
- 字串 `"Sp1"` 或 `"S1"`：同上

#### SRT/VTT speaker 抽取

正規表達式：`^Speaker\s*(\d+)\s*[:：]\s*(.*)$`
- 匹配 → speaker = 數字 - 1（轉 0-indexed），text = 剩餘
- 不匹配 → speaker = 0

#### TXT 格式

```
[00:00:00.00] Speaker 1: 各位早安，今天我們要討論糖尿病
[00:00:03.45] Speaker 2: 是的，胰島素分泌不足是主因
```

end_time 推算：下一行 start；最後一行用 audio_duration。

### 9.3 範本下載 endpoint

`GET /api/admin/datasets/templates/{format}` 回傳範本檔案：
- xlsx：含 header + 2 行範例
- csv：同上
- srt / vtt / txt / json：2 段範例

範本檔案放在 `backend/templates/`。

### 9.4 匯出格式

| 格式 | endpoint |
|---|---|
| 訓練 JSON | `GET /api/admin/datasets/{id}/export?format=json` |
| SRT | `?format=srt` |
| VTT | `?format=vtt` |
| Excel | `?format=xlsx` |
| TXT | `?format=txt` |

---

## 10. 訓練流程

### 10.1 完整 sequence

```
Frontend                 Backend                   Worker            DockerCtrl       Train Container       vLLM
   │ POST /training         │                         │                  │                  │                  │
   │───────────────────────>│ create TrainingRun       │                  │                  │                  │
   │                        │ enqueue training_job ───>│                  │                  │                  │
   │ <─── run_id ───────────│                         │                  │                  │                  │
   │                        │                         │ pull job          │                  │                  │
   │ GET /training/{id}/log │                         │ status=PREPARING  │                  │                  │
   │ ──── SSE ──────────────│ <─── log_tail ──────────│ symlink dataset   │                  │                  │
   │                        │                         │                   │                  │                  │
   │                        │                         │ if !concurrent ──>│ stop vllm ───────────────────────>│
   │                        │                         │                   │ <─── stopped ─────────────────────│
   │                        │                         │                   │                  │                  │
   │                        │                         │ status=TRAINING   │                  │                  │
   │                        │                         │ docker run ──────>│ run train ───────>│                  │
   │ <─── log line ──── SSE │ <─── append log ────────│ <─── stream ──────│ <─── exec torchrun│                  │
   │                        │                         │ exit_code=0       │                  │                  │
   │                        │                         │ status=MERGING    │                  │                  │
   │                        │                         │ run merge ───────>│ run merge ──────>│                  │
   │                        │                         │ <─── done ────────│                  │                  │
   │                        │                         │ insert ModelVersion                  │                  │
   │                        │                         │ if !concurrent ──>│ start vllm ──────────────────────>│
   │                        │                         │                   │ <─── ready ──────────────────────│
   │                        │                         │ status=DONE       │                  │                  │
   │ <─── done ──── SSE ────│ <─── notify ────────────│                   │                  │                  │
```

### 10.2 資料準備

`prepare_dataset(project_id, dataset_item_ids) -> Path`：
1. 建立 `data/staging/{run_id}/`
2. 對每個 item：
   - symlink audio：`{idx}.{ext}` → 原檔
   - 寫 label：`{idx}.json`，重設 `audio_path = "{idx}.{ext}"`
3. 回傳 staging dir

### 10.3 訓練啟動命令

```bash
torchrun --nproc_per_node=${nproc} \
  /app/finetuning-asr/lora_finetune.py \
  --model_path microsoft/VibeVoice-ASR \
  --data_dir /data \
  --output_dir /output \
  --num_train_epochs ${epochs} \
  --per_device_train_batch_size ${batch_size} \
  --gradient_accumulation_steps ${grad_accum} \
  --learning_rate ${lr} \
  --lora_r ${lora_r} \
  --lora_alpha ${lora_alpha} \
  --lora_dropout ${lora_dropout} \
  --warmup_ratio ${warmup_ratio} \
  --weight_decay ${weight_decay} \
  --max_audio_length ${max_audio_length} \
  --gradient_checkpointing \
  --bf16 \
  --logging_steps 5 \
  --save_steps 100 \
  --save_total_limit 2 \
  --report_to none
```

### 10.4 LoRA 合併

訓練完成後跑短命 container：
```python
import torch
from peft import PeftModel
from vibevoice.modular.modeling_vibevoice_asr import VibeVoiceASRForConditionalGeneration

base = VibeVoiceASRForConditionalGeneration.from_pretrained(
    "microsoft/VibeVoice-ASR", torch_dtype=torch.bfloat16)
model = PeftModel.from_pretrained(base, "/adapter")
model = model.merge_and_unload()
model.save_pretrained("/merged", safe_serialization=True)
```

### 10.5 故障處理

| 錯誤 | 偵測 | 處理 |
|---|---|---|
| OOM | exit code != 0 + log "CUDA out of memory" | 自動建議降 batch / 開 grad ckpt |
| Dataset 為空 | preparing 階段 | 直接 fail |
| Container 啟動失敗 | docker SDK exception | retry 1 次 |
| 使用者取消 | API 呼叫 | docker stop + status=CANCELLED |
| Disk full | exit code | 提示清理 data/loras/ |

---

## 11.（已刪除）

v1.0 的「即時串流流程」整章移除。

---

## 12. Docker / Compose 配置

### 12.1 docker-compose.yml

```yaml
version: "3.9"

services:
  redis:
    image: redis:7-alpine
    container_name: vibevoice-redis
    ports:
      - "${REDIS_PORT:-6379}:6379"
    volumes:
      - ./data/redis:/data
    command: redis-server --appendonly yes
    restart: unless-stopped

  vllm:
    image: ${VLLM_DOCKER_IMAGE:-vllm/vllm-openai:v0.14.1}
    container_name: vibevoice-vllm
    profiles: ["manual"]   # 由 backend 控制啟停
    ipc: host
    ports:
      - "8000:8000"
    environment:
      - VIBEVOICE_FFMPEG_MAX_CONCURRENCY=64
      - PYTORCH_ALLOC_CONF=expandable_segments:True
    volumes:
      - ./vendor/VibeVoice:/app
      - ${HF_HOME:-./data/hf_cache}:/root/.cache/huggingface
      - ./data/merged:/merged
    working_dir: /app
    entrypoint: ["bash", "-c"]
    command: ["python3 /app/vllm_plugin/scripts/start_server.py"]
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]

  backend:
    build:
      context: .
      dockerfile: docker/backend.Dockerfile
    container_name: vibevoice-backend
    ports:
      - "${BACKEND_PORT:-8080}:8080"
    environment:
      - DEPLOYMENT_PROFILE=${DEPLOYMENT_PROFILE:-single}
      - VLLM_BASE_URL=http://host.docker.internal:8000
      - REDIS_URL=redis://redis:6379/0
      - BACKEND_DB_URL=sqlite:////data/app.db
      - BACKEND_DATA_DIR=/data
    env_file:
      - .env
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./data:/data
      - ./vendor/VibeVoice:/vendor/VibeVoice:ro
    depends_on:
      - redis
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped

  worker:
    build:
      context: .
      dockerfile: docker/backend.Dockerfile
    container_name: vibevoice-worker
    command: ["arq", "app.worker.WorkerSettings"]
    environment:
      - DEPLOYMENT_PROFILE=${DEPLOYMENT_PROFILE:-single}
      - VLLM_BASE_URL=http://host.docker.internal:8000
      - REDIS_URL=redis://redis:6379/0
      - BACKEND_DB_URL=sqlite:////data/app.db
      - BACKEND_DATA_DIR=/data
    env_file:
      - .env
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./data:/data
      - ./vendor/VibeVoice:/vendor/VibeVoice:ro
    depends_on:
      - redis
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped
    deploy:
      replicas: ${WORKER_REPLICAS:-1}

  frontend:
    build:
      context: ./frontend
      dockerfile: ../docker/frontend.Dockerfile
    container_name: vibevoice-frontend
    ports:
      - "${FRONTEND_PORT:-5173}:80"
    environment:
      - VITE_API_BASE=http://localhost:8080
    restart: unless-stopped
```

### 12.2 backend.Dockerfile

```dockerfile
FROM python:3.11-slim

# 系統依賴：ffmpeg, docker CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates curl gnupg \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update && apt-get install -y docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/pyproject.toml backend/poetry.lock* ./
RUN pip install --no-cache-dir poetry && poetry config virtualenvs.create false \
    && poetry install --no-root --without dev

COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/templates ./templates
COPY backend/alembic.ini ./

# entrypoint 預設給 backend；worker 用 docker-compose command override
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### 12.3 train.Dockerfile

```dockerfile
FROM nvcr.io/nvidia/pytorch:24.07-py3

WORKDIR /app

# 上游 VibeVoice 在 docker run 時 mount
RUN pip install --no-cache-dir \
    peft==0.12.0 \
    transformers>=4.45.0 \
    accelerate \
    librosa soundfile

# entry 由 docker run 帶 command 指定
```

### 12.4 frontend.Dockerfile

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY ../docker/nginx.conf /etc/nginx/conf.d/default.conf
```

### 12.5 啟動順序

```bash
# Bootstrap（一次性）
make setup

# 啟動全部
make up
# 等同於：
#   docker compose up -d redis backend worker frontend
#   backend 會在啟動時自動拉起 vllm container

# 停止
make down
```

---

## 13. 目錄結構

```
<PROJECT_ROOT>/                     # 任意路徑，scripts 自動偵測
├── SPEC.md                         ⭐ 本文件
├── Makefile                        bootstrap / up / down / test
├── .env.example
├── .gitignore
├── docker-compose.yml
│
├── docker/
│   ├── backend.Dockerfile
│   ├── frontend.Dockerfile
│   ├── train.Dockerfile
│   └── nginx.conf
│
├── vendor/
│   └── VibeVoice/                  上游 clone（已完成）
│
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── migrations/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       └── 0001_initial.py     初始 schema
│   ├── templates/                  匯入範本
│   │   ├── dataset_template.xlsx
│   │   ├── dataset_template.csv
│   │   ├── dataset_template.srt
│   │   ├── dataset_template.vtt
│   │   ├── dataset_template.txt
│   │   └── dataset_template.json
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 FastAPI entry
│   │   ├── worker.py               Arq WorkerSettings
│   │   ├── config.py
│   │   ├── constants.py            常數集中（prompt 模板、mime_map、key_mapping）
│   │   ├── errors.py               錯誤碼目錄
│   │   ├── db.py
│   │   ├── models.py               SQLAlchemy ORM
│   │   ├── schemas.py              Pydantic
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── admin/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── projects.py
│   │   │   │   ├── jobs.py
│   │   │   │   ├── datasets.py
│   │   │   │   ├── training.py
│   │   │   │   ├── models.py
│   │   │   │   ├── api_keys.py
│   │   │   │   ├── webhook.py
│   │   │   │   ├── integration_calls.py
│   │   │   │   └── system.py
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── transcribe_ws.py
│   │   │       ├── transcribe_sync.py
│   │   │       └── jobs.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── vllm_client.py
│   │   │   ├── queue.py
│   │   │   ├── auth.py
│   │   │   ├── webhook.py
│   │   │   ├── audio_splitter.py
│   │   │   ├── job_runner.py
│   │   │   ├── training_runner.py
│   │   │   ├── dataset_importer.py
│   │   │   ├── deployment.py
│   │   │   ├── docker_ctrl.py
│   │   │   └── file_store.py
│   │   ├── utils/
│   │   │   ├── __init__.py
│   │   │   ├── audio.py            ffprobe, duration, MIME
│   │   │   ├── parser.py           §6.3 vLLM 輸出解析
│   │   │   ├── format_converters.py 6 種格式匯入/匯出
│   │   │   ├── time_utils.py       時間格式互轉
│   │   │   └── hmac_signer.py      Webhook 簽章
│   │   └── middleware/
│   │       ├── __init__.py
│   │       ├── api_key_auth.py
│   │       ├── integration_log.py
│   │       └── metrics.py
│   └── tests/
│       ├── conftest.py
│       ├── test_parser.py
│       ├── test_dataset_importer.py
│       ├── test_audio_splitter.py
│       ├── test_auth.py
│       ├── test_webhook_signer.py
│       ├── test_vllm_client.py
│       └── test_e2e.py
│
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/
│       │   ├── client.ts
│       │   ├── projects.ts
│       │   ├── jobs.ts
│       │   ├── datasets.ts
│       │   ├── training.ts
│       │   ├── api_keys.ts
│       │   └── system.ts
│       ├── pages/
│       │   ├── Projects.tsx
│       │   ├── Hotwords.tsx
│       │   ├── Offline.tsx
│       │   ├── Datasets.tsx
│       │   ├── Editor.tsx
│       │   ├── Training.tsx
│       │   ├── TrainingDetail.tsx
│       │   ├── Models.tsx
│       │   ├── ApiKeys.tsx
│       │   ├── Webhook.tsx
│       │   ├── IntegrationCalls.tsx
│       │   └── System.tsx
│       ├── components/
│       │   ├── TranscriptViewer.tsx
│       │   ├── TranscriptEditor.tsx
│       │   ├── WaveformPlayer.tsx
│       │   ├── HotwordsChips.tsx
│       │   ├── JobList.tsx
│       │   ├── ApiKeyDisplay.tsx
│       │   ├── WebhookTestResult.tsx
│       │   └── Sidebar.tsx
│       ├── stores/
│       │   ├── projectStore.ts
│       │   └── systemStore.ts
│       └── lib/
│           ├── time.ts
│           └── format.ts
│
├── scripts/
│   ├── bootstrap.sh                Day 0 環境設定
│   ├── verify_deployment.sh        部署驗證
│   ├── qc_simulator.py             QC 整合模擬器（M6 用）
│   └── seed_demo_project.py        建測試專案
│
└── data/                           gitignored
    ├── app.db
    ├── hf_cache/
    ├── jobs/                       ⛔ deprecated, use uploads/
    ├── uploads/
    │   └── {job_id}/
    │       └── audio.{ext}
    ├── datasets/
    │   └── {project_id}/
    │       └── {item_id}.{ext}
    ├── staging/
    │   └── {run_id}/
    ├── loras/
    │   └── {project_id}/{run_id}/
    ├── merged/
    │   └── {project_id}/{run_id}/
    ├── logs/
    └── redis/
```

---

## 14. 實施計劃

### 14.1 Milestones 總覽

| ID | 標題 | 預估 | 累計 | 主要產出 |
|---|---|---|---|---|
| M1 | vLLM 部署驗證 | 0.5 d | 0.5 | 跑通 demo 音檔 |
| M1.5 | vLLM 動態 LoRA 驗證 | 0.5 d | 1.0 | yes/no |
| M2 | Backend 骨架 + Arq+Redis + Admin 基本 API | 2.0 d | 3.0 | curl 上傳離線轉錄 |
| M3 | Frontend Admin 離線 + 校正工作台 | 2.0 d | 5.0 | 完整離線流程 + wavesurfer |
| M3.5 | Dataset CRUD + 多格式匯入 | 1.5 d | 6.5 | 6 種格式皆能匯入 |
| M4 | Training Runner + Model Versions | 2.0 d | 8.5 | 一鍵訓練、合併、切換 |
| M5 | 長音檔切段 + 錯誤恢復 | 1.0 d | 9.5 | >55 min 自動切段 |
| **M6** | **外部 v1 API：WS + API Key + Webhook + Idempotency + OpenAPI** | **2.0 d** | 11.5 | QC 整合 ready |
| M7 | Compose + Profile + 文件 + qc_simulator | 1.0 d | **12.5** | docker compose up 一鍵 |

### 14.2 各 Milestone 驗收條件（可執行測試）

#### M1：vLLM 部署驗證

```bash
# 1. 啟動
docker compose --profile manual up -d vllm
docker logs -f vibevoice-vllm  # 等到 "Application startup complete"

# 2. 列出 model
curl http://localhost:8000/v1/models | jq '.data[0].id'
# 預期：vibevoice

# 3. 跑 demo 音檔
docker exec vibevoice-vllm python3 /app/vllm_plugin/tests/test_api.py \
  /app/demo/asr_demo/demo3-hotwords.wav --hotwords "Microsoft,VibeVoice"
# 預期：輸出 JSON segments，含 Start time / End time / Speaker ID / Content

# 4. 測中文音檔（自備）
# ...
```

驗收：步驟 2-3 都成功，步驟 4 主觀判斷可接受。

#### M2：Backend + Admin API

```bash
# 1. 啟動
make up

# 2. 健康檢查
curl http://localhost:8080/api/admin/system/health | jq '.ok'  # true

# 3. 建專案
curl -X POST http://localhost:8080/api/admin/projects \
  -H "Content-Type: application/json" \
  -d '{"name":"M2測試","hotwords":["微軟"]}' | jq '.id'
# 預期：1 (或下一個可用 ID)

# 4. 上傳轉錄
curl -F "file=@vendor/VibeVoice/demo/asr_demo/demo3-hotwords.wav" \
  -F "project_id=1" \
  http://localhost:8080/api/admin/transcribe | jq -r '.job_id'
# 拿到 job_id

# 5. 等結果
JOB_ID=...
while [ "$(curl -s http://localhost:8080/api/admin/jobs/$JOB_ID | jq -r .status)" != "done" ]; do
  sleep 5
done

# 6. 看結果
curl http://localhost:8080/api/admin/jobs/$JOB_ID | jq '.segments | length'
# 預期：> 0

# 7. 確認 Redis 有 queue 紀錄
docker exec vibevoice-redis redis-cli KEYS '*'
```

#### M3：Frontend 離線 + 校正

```
測試流程（瀏覽器手動）：
1. 訪問 http://localhost:5173
2. 建立專案「M3測試」
3. 進入 Hotwords 頁，加 3 個 hotwords
4. 進入「離線轉錄」，上傳音檔
5. 等 status=done
6. 點「檢視」進 TranscriptViewer
7. 點 timestamp，確認音檔跳到對應時間
8. 點「編輯」進入 TranscriptEditor
9. 拖拉段落邊界，看到時間更新
10. 修改文字，確認 3 秒後自動儲存
11. 鍵盤快捷鍵測試（Space, ←/→, Tab, M, /）
```

#### M4：Training + Models

```bash
# 1. 用 toy_dataset 建立 datasets
for i in 0 1; do
  curl -F "audio=@vendor/VibeVoice/finetuning-asr/toy_dataset/${i}.mp3" \
       -F "label=@vendor/VibeVoice/finetuning-asr/toy_dataset/${i}.json" \
       -F "project_id=1" \
       -F "format=json" \
       http://localhost:8080/api/admin/datasets/import
done

# 2. 啟動訓練
curl -X POST http://localhost:8080/api/admin/training \
  -H "Content-Type: application/json" \
  -d '{"project_id":1,"dataset_item_ids":[1,2],"hyperparams":{"lora_r":16,"lora_alpha":32,"lr":1e-4,"epochs":1,"batch_size":1,"grad_accum":2}}' | jq -r '.id'

# 3. 看 log
RUN_ID=...
curl -N http://localhost:8080/api/admin/training/$RUN_ID/log

# 4. 等完成（約 5-10 分鐘 toy dataset）
while [ "$(curl -s http://localhost:8080/api/admin/training/$RUN_ID | jq -r .status)" != "done" ]; do
  sleep 30
done

# 5. 確認有新 ModelVersion
curl http://localhost:8080/api/admin/projects/1/models | jq '. | length'  # > 1

# 6. 切換 active model
MODEL_ID=...
curl -X POST http://localhost:8080/api/admin/projects/1/active_model \
  -d "{\"model_version_id\":$MODEL_ID}"

# 7. 等 vLLM 重啟完成
# 8. 用同樣音檔再轉錄一次，比對結果
```

#### M5：長音檔切段

```bash
# 用 ffmpeg 拼一個 60+ 分鐘音檔
ffmpeg -stream_loop 5 -i vendor/VibeVoice/demo/asr_demo/demo1-chat.mp3 -c copy long.mp3

# 確認時長
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 long.mp3
# 應該 > 3300 秒

# 上傳
curl -F "file=@long.mp3" -F "project_id=1" \
  http://localhost:8080/api/admin/transcribe | jq -r '.job_id'

# 確認自動切段（job 應該 chunks_total > 1）
JOB_ID=...
curl http://localhost:8080/api/admin/jobs/$JOB_ID | jq '.chunks_total'  # > 1
```

#### M6：v1 API

```bash
# 1. 建 API key
curl -X POST http://localhost:8080/api/admin/projects/1/api_keys \
  -d '{"name":"qc_test"}' | jq -r '.key'
# 拿到 plain key，僅此一次回傳

# 2. 用 qc_simulator 跑完整流程
python scripts/qc_simulator.py \
  --url ws://localhost:8080/api/v1/transcribe \
  --api-key vva_xxxxxxxxxxxxxx \
  --audio sample.mp3 \
  --callback-url https://webhook.site/xxx

# 3. 用 sync endpoint 跑短音檔
curl -X POST http://localhost:8080/api/v1/transcribe/sync \
  -H "Authorization: Bearer vva_xxxxxxxxxxxxxx" \
  -F "file=@short.wav" | jq '.segments | length'

# 4. 拿 OpenAPI
curl http://localhost:8080/api/v1/openapi.json | jq '.info.title'
# 預期：VibeVoice ASR API

# 5. 測 idempotency
IDEM=$(uuidgen)
curl -X POST http://localhost:8080/api/v1/transcribe/sync \
  -H "Authorization: Bearer vva_xxx" \
  -H "Idempotency-Key: $IDEM" -F "file=@short.wav" | jq -r '.job_id'
# 重送同 key
curl -X POST http://localhost:8080/api/v1/transcribe/sync \
  -H "Authorization: Bearer vva_xxx" \
  -H "Idempotency-Key: $IDEM" -F "file=@short.wav" | jq -r '.job_id'
# 應為同一 job_id
```

#### M7：Compose 一鍵

```bash
# Clean 環境驗證
git clean -fdx data/ 2>/dev/null || true
rm -rf data/app.db
make setup
make up

# 等所有 service 起來
sleep 30

# 跑 verify_deployment.sh
./scripts/verify_deployment.sh
# 預期：所有檢查 PASS
```

---

## 15. 風險登記

| ID | 風險 | 機率 | 衝擊 | 緩解 | 偵測點 |
|---|---|---|---|---|---|
| R1 | vLLM container 啟動失敗 | 中 | 高 | M1 早驗證；備援 transformers | M1 |
| R2 | 中文 hotwords 效果差 | 中 | 中 | M1 用中文測 | M1 |
| R3 | LoRA 合併後 vLLM 載入失敗 | 中 | 高 | M4 smoke test | M4 |
| R4 | OOM during training | 中 | 中 | grad_ckpt + batch=1 | M4 |
| R5 | Backend docker socket 安全 | 中 | 中 | 白名單；正式環境改 systemd | 全程 |
| R6 | 多格式匯入 edge cases | 高 | 低 | unit test 覆蓋 | M3.5 |
| R7 | 重複迴圈無法恢復 | 低 | 中 | 上限 3 次；標記 partial | M2 |
| R8 | 長音檔切段 speaker 連續性差 | 高 | 低 | 文件揭露；best-effort | M5 |
| R9 | **上萬通/天單卡不夠** | 高 | 中 | 客戶硬體建議升級至 dual-tp / multi | 客戶實測 |
| R10 | Redis 單點故障 | 中 | 高 | 預留 Redis Cluster 設定 | 生產 |
| R11 | Webhook 投遞累積失敗淹沒 queue | 中 | 中 | DLQ + alert | M6 |
| R12 | API key 洩漏 | 低 | 高 | hash 儲存、rotate 機制、僅一次 plain 顯示 | M6 |
| R13 | WS 上傳大檔記憶體爆 | 中 | 中 | stream-to-disk during upload | M6 |
| R14 | Idempotency Redis miss → 重複 job | 低 | 低 | DB unique constraint 兜底 | M6 |
| R15 | QC 端整合卡 schema 不穩 | 中 | 中 | v1 凍結，未來改 → /api/v2 | M6 |

---

## 16. 安全性

### 16.1 內部 Demo 假設
- 部署在內網
- Admin UI 走內網訪問（IP 白名單可選）
- v1 API 用 API Key 認證（必須）

### 16.2 強制措施

| 項目 | 措施 |
|---|---|
| API Key 儲存 | SHA-256 hash，不儲存 plain |
| API Key 顯示 | 建立時唯一一次顯示 plain；之後只顯示 prefix |
| Webhook secret | 同上策略 |
| Webhook 簽章 | HMAC-SHA256，header `X-Webhook-Signature: sha256=...` |
| Webhook timestamp | header `X-Webhook-Timestamp`，QC 端應驗證 ≤5 分鐘內 |
| Docker socket | Backend 內限制 image / container name 白名單 |
| 上傳檔案 | 大小限制（500MB 預設）、MIME 驗證、檔名 sanitize |
| Path traversal | `Path.resolve()` + 確認在 data/ 之下 |
| SQL injection | SQLAlchemy ORM |
| XSS | React 預設 escape；不用 dangerouslySetInnerHTML |
| Idempotency Key | 限同一 API Key 範圍內，避免跨租戶碰撞 |

### 16.3 升級至正式環境補

- HTTPS（reverse proxy with TLS）
- Audit log（誰在何時 transcribe / train / 切 model）
- IP 白名單 / mTLS（v1 API）
- Rate limiting（per API Key）
- 訓練資料加密 at rest
- API key 過期強制（目前可永久）

---

## 17. 外部整合 API（v1）⭐

> **本章獨立給 QC 端工程師閱讀**。從 §17.1 到 §17.10 即為對外整合手冊，可直接抽出。

### 17.1 概覽

VibeVoice ASR 服務對外提供以下整合方式（依優先順序）：

| Endpoint | 用途 | 適用 |
|---|---|---|
| `WSS /api/v1/transcribe` | **主要**：WS 上傳音檔，取結果 | 大多數情況 |
| `POST /api/v1/transcribe/sync` | 短音檔同步轉錄（≤2 分鐘） | 短音檔簡單情境 |
| `GET /api/v1/jobs/{id}` | 查詢 Job 狀態 | 連線斷線後查狀態 |
| `GET /api/v1/jobs/{id}/result` | 取得 Job 結果 | 同上 |
| `GET /api/v1/openapi.json` | OpenAPI spec | client SDK 生成 |
| Webhook（我們 → QC） | 結果完成主動推送 | 可選，搭配 WS 或 sync |

### 17.2 認證

#### API Key 格式
- Prefix：`vva_`（VibeVoice ASR）
- 隨機部分：32 字元 URL-safe base64
- 範例：`vva_a1B2c3D4e5F6g7H8i9J0kLmN1oP2qR3s`
- 全長：36 字元

#### 取得 API Key
- 由 Admin UI 建立（§8.3.x）
- 建立時系統回傳 plain key（僅此一次）
- 其後只能看 prefix（前 8 碼）做識別

#### Authorization 方式

**HTTP（REST）**：
```
Authorization: Bearer vva_a1B2c3D4e5F6g7H8i9J0kLmN1oP2qR3s
```

**WebSocket**：
透過 WebSocket Subprotocol 帶（HTTP header 不支援自訂）：
```
Sec-WebSocket-Protocol: bearer.vva_a1B2c3D4e5F6g7H8i9J0kLmN1oP2qR3s
```

> 為什麼 WS 不放 query string？query 會被 access log 寫入，洩漏 key。Subprotocol 不會。

#### 認證失敗回應

REST：
```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "code": "invalid_api_key",
  "detail": "API key is invalid, revoked, or expired"
}
```

WebSocket：握手時直接回 `401`，不建立連線。

### 17.3 WebSocket 上傳協定（主路徑）

#### 連線

```
GET wss://your-host/api/v1/transcribe HTTP/1.1
Sec-WebSocket-Protocol: bearer.vva_xxxxxxxxxxxxxxxxxxxxx
```

#### 訊息流

```
[Client]                          [Server]
   │ ─── connect (subprotocol) ───>│
   │ <── 101 Switching Protocols ──│
   │                               │
   │                               │ 認證成功，回 ready
   │ <─── ready ───────────────────│  text frame: {"type":"ready", ...}
   │                               │
   │ ─── start metadata ──────────>│  text frame: {"type":"start", ...}
   │ <── ack ──────────────────────│  text frame: {"type":"ack", ...}
   │                               │
   │ ─── audio chunk 1 (binary) ──>│
   │ ─── audio chunk 2 (binary) ──>│
   │ ─── ... ─────────────────────>│
   │ ─── audio chunk N (binary) ──>│
   │ ─── eof ─────────────────────>│  text frame: {"type":"eof"}
   │                               │
   │ <── queued ───────────────────│  text frame: {"type":"queued", ...}
   │ <── running ──────────────────│  text frame: {"type":"running", ...}
   │ <── progress (optional) ──────│  text frame: {"type":"progress", ...}
   │ <── done ─────────────────────│  text frame: {"type":"done", ...}
   │                               │
   │ ─── close ───────────────────>│
```

#### Client → Server 訊息

##### Text frame: `start`
```json
{
  "type": "start",
  "filename": "call_001.mp3",
  "mime": "audio/mpeg",
  "expected_size_bytes": 4567890,
  "callback_url": "https://qc.example.com/asr-callback",
  "idempotency_key": "qc-call-2026-05-09-001",
  "metadata": {
    "call_id": "abc-123",
    "agent_id": "agt-456",
    "any_other_field": "..."
  }
}
```

| 欄位 | 必需 | 說明 |
|---|---|---|
| `type` | ✅ | 固定 `"start"` |
| `filename` | ✅ | 給 server 推測 MIME 用，不會儲存原檔名 |
| `mime` | ⬜ | 若不給，依 filename 副檔名推測 |
| `expected_size_bytes` | ⬜ | Server 用於進度回報（不檢查） |
| `callback_url` | ⬜ | 若提供，完成時 server POST 到此 URL |
| `idempotency_key` | ⬜ | 24 小時內同 key 同 API Key 視為同一 Job |
| `metadata` | ⬜ | QC 自訂欄位，會原封不動寫入 Job 並 callback 帶回 |

##### Binary frames: 音檔內容

- 任意大小，server 會 streaming 寫入 disk
- 累積上限：`MAX_UPLOAD_MB`（預設 500MB）
- 任一 binary frame 大小：建議 256KB-1MB

##### Text frame: `eof`
```json
{"type": "eof"}
```

##### Text frame: `cancel`
```json
{"type": "cancel"}
```
取消上傳/處理。

#### Server → Client 訊息

##### `ready`
```json
{
  "type": "ready",
  "session_id": "ses-uuid",
  "server_version": "1.0.0",
  "limits": {
    "max_upload_bytes": 524288000,
    "max_audio_duration_sec": 14400,
    "ws_idle_timeout_sec": 60
  }
}
```

##### `ack`（接收 metadata 後）
```json
{
  "type": "ack",
  "session_id": "ses-uuid",
  "ready_to_receive": true
}
```

##### `progress`（上傳期間或推論期間）
```json
{"type": "progress", "phase": "upload", "received_bytes": 1024000, "total_bytes": 4567890}
{"type": "progress", "phase": "inference", "value": 0.45}
```

##### `queued`（eof 後）
```json
{
  "type": "queued",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "queue_position": 3
}
```

##### `running`
```json
{"type": "running", "job_id": "550e..."}
```

##### `done`（成功）
```json
{
  "type": "done",
  "job_id": "550e...",
  "duration_sec": 354.78,
  "elapsed_sec": 142.3,
  "model": "v2-2026-05-09",
  "hotwords_used": ["糖尿病", "胰島素"],
  "segments": [
    {"start_time": 0.0, "end_time": 3.45, "speaker_id": 1, "text": "..."},
    {"start_time": 3.45, "end_time": 7.20, "speaker_id": 2, "text": "..."}
  ],
  "warnings": [],
  "metadata": { ... }   // QC 帶來的原樣回傳
}
```

##### `error`
```json
{
  "type": "error",
  "code": "audio_too_long",
  "detail": "Audio duration 5500.0s exceeds limit 4800.0s",
  "job_id": "550e..."   // 可能無
}
```

#### 錯誤碼目錄（WS / REST 共用）

| Code | HTTP | 說明 |
|---|---|---|
| `invalid_api_key` | 401 | API key 不存在、撤銷、過期 |
| `quota_exceeded` | 429 | Queue 滿 / rate limit |
| `idempotency_replay` | 409 | 同 idempotency_key 已有不同的 request body |
| `invalid_metadata` | 400 | start frame 欄位錯 |
| `audio_too_long` | 400 | 超過 MAX_AUDIO_DURATION_SEC |
| `audio_too_short` | 400 | 短於 0.5 秒 |
| `audio_unreadable` | 400 | ffmpeg 解碼失敗 |
| `unsupported_format` | 400 | MIME 不支援 |
| `upload_too_large` | 413 | 超過 MAX_UPLOAD_MB |
| `upload_timeout` | 408 | WS idle 超過 timeout |
| `vllm_unavailable` | 503 | vLLM container 沒就緒 |
| `internal_error` | 500 | 未預期錯誤 |

#### WS Idle Timeout

連續 60 秒沒有任何 frame（client → server）→ server 主動 close。
回應 close code `4001`，reason `"upload_timeout"`。

### 17.4 同步轉錄（短音檔）

`POST /api/v1/transcribe/sync`

**用途**：≤120 秒短音檔，QC 想直接拿結果不用 polling/webhook。

**Request**:
```http
POST /api/v1/transcribe/sync HTTP/1.1
Authorization: Bearer vva_xxx
Content-Type: multipart/form-data
Idempotency-Key: qc-call-2026-05-09-002 (optional)

file: <binary>
metadata: {"call_id": "abc"}  (optional, JSON string)
```

**Response (200)**:
```json
{
  "job_id": "550e...",
  "duration_sec": 88.5,
  "elapsed_sec": 35.2,
  "model": "base",
  "hotwords_used": [],
  "segments": [...],
  "metadata": {"call_id": "abc"}
}
```

**Response (400 audio_too_long)**:
```json
{"code": "audio_too_long", "detail": "Audio is 145s, sync limit is 120s. Use WS endpoint instead."}
```

### 17.5 Job 狀態查詢

`GET /api/v1/jobs/{job_id}`

```json
{
  "job_id": "550e...",
  "status": "running",
  "progress": 0.6,
  "duration_sec": 354.78,
  "created_at": "2026-05-09T14:30:00Z",
  "started_at": "2026-05-09T14:30:02Z",
  "metadata": {...}
}
```

`GET /api/v1/jobs/{job_id}/result`（status=done 才有 segments）

```json
{
  "job_id": "550e...",
  "status": "done",
  "segments": [...],
  "model": "...",
  "hotwords_used": [...],
  "metadata": {...},
  "warnings": []
}
```

> 同一個 API Key 只能存取自己 project 的 job_id。其他 project 的 job 回 404（不洩漏存在性）。

### 17.6 Webhook Callback

如果 `start` 訊息或 sync request 帶了 `callback_url`，OR 該 project 有設定預設 webhook，**完成時** server 主動 POST。

#### 投遞 request

```http
POST <callback_url> HTTP/1.1
Content-Type: application/json
X-Webhook-Event: transcription.completed
X-Webhook-Signature: sha256=<HMAC_HEX>
X-Webhook-Timestamp: 1715243400
X-Webhook-Delivery: <uuid>
User-Agent: VibeVoice-ASR/1.0

{
  "event": "transcription.completed",
  "job_id": "550e...",
  "project": "客服質檢",
  "duration_sec": 354.78,
  "elapsed_sec": 142.3,
  "model": "v2-2026-05-09",
  "hotwords_used": [...],
  "segments": [...],
  "metadata": {...},
  "warnings": []
}
```

#### 失敗事件

```json
{
  "event": "transcription.failed",
  "job_id": "550e...",
  "error_code": "audio_unreadable",
  "error_detail": "...",
  "metadata": {...}
}
```

#### 簽章驗證（QC 端必須做）

```python
import hmac, hashlib, json, time

def verify_webhook(headers, body_bytes, secret):
    sig_header = headers.get("X-Webhook-Signature", "")
    timestamp = headers.get("X-Webhook-Timestamp", "")
    
    # 1. 時間戳檢查（防 replay）
    if abs(time.time() - int(timestamp)) > 300:
        return False
    
    # 2. 計算期望簽章
    msg = f"{timestamp}.{body_bytes.decode()}".encode()
    expected = "sha256=" + hmac.new(
        secret.encode(), msg, hashlib.sha256
    ).hexdigest()
    
    # 3. constant-time 比對
    return hmac.compare_digest(sig_header, expected)
```

#### Webhook 重試政策

server 端 retry：1 次後 30s → 5min → 30min → 2h → 6h → 12h → give_up（共 7 次）。
2xx response 視為成功，其他都重試。

QC 端建議：
- 收到後先回 200，再非同步處理
- 處理失敗自己 queue，不要靠 server retry
- 處理時間 > 30s 也應立即回 200，避免 server 誤判失敗

### 17.7 Idempotency

防止 QC 端重試造成重複 Job：

- 機制：`Idempotency-Key` header（REST）或 `idempotency_key` 欄位（WS start）
- 範圍：同一個 API Key 內
- TTL：24 小時
- 實作：Redis `SETNX` + DB unique constraint 兜底

行為：
| 狀況 | Server 行為 |
|---|---|
| 新 key | 建 Job，記錄 key→job_id 24h |
| 重複 key + 同 body hash | 回原 job（200，不再 process） |
| 重複 key + 不同 body hash | 拒絕（409 `idempotency_replay`） |

### 17.8 Rate Limiting

預設**不主動 rate limit**（內部使用），但 vLLM queue 有上限：

- queue 中超過 `WORKER_MAX_JOBS × replicas × 4` 時 → 回 `429 quota_exceeded`
- response header 帶 `Retry-After: <seconds>`

QC 端建議：看到 429 應 backoff（建議 exponential 1s → 2s → 4s → ...）。

### 17.9 OpenAPI

`GET /api/v1/openapi.json` 回傳 OpenAPI 3.1 spec。

QC 端可用：
- Swagger Codegen / openapi-generator 生 client SDK
- VS Code REST Client / Postman 匯入測試

### 17.10 完整呼叫範例（Python）

```python
import asyncio
import json
import websockets
import aiofiles

API_KEY = "vva_xxxxxxxxxxxxxxxxxxxxxxx"
WS_URL = "wss://vibevoice.internal/api/v1/transcribe"

async def transcribe(audio_path: str, callback_url: str = None) -> dict:
    subprotocol = f"bearer.{API_KEY}"
    
    async with websockets.connect(
        WS_URL, subprotocols=[subprotocol]
    ) as ws:
        # 等 ready
        ready = json.loads(await ws.recv())
        assert ready["type"] == "ready"
        
        # 送 metadata
        await ws.send(json.dumps({
            "type": "start",
            "filename": audio_path.split("/")[-1],
            "mime": "audio/mpeg",
            "callback_url": callback_url,
            "idempotency_key": f"call-{audio_path}",
            "metadata": {"call_id": "abc-123"},
        }))
        
        # 等 ack
        ack = json.loads(await ws.recv())
        assert ack["type"] == "ack"
        
        # 串流上傳
        async with aiofiles.open(audio_path, "rb") as f:
            while chunk := await f.read(256 * 1024):
                await ws.send(chunk)
        
        # 送 eof
        await ws.send(json.dumps({"type": "eof"}))
        
        # 等結果
        while True:
            msg = json.loads(await ws.recv())
            if msg["type"] == "done":
                return msg
            if msg["type"] == "error":
                raise RuntimeError(f"{msg['code']}: {msg['detail']}")
            print(f"State: {msg['type']}", msg)


result = asyncio.run(transcribe("call_001.mp3"))
for seg in result["segments"]:
    print(f"[{seg['start_time']}-{seg['end_time']}] Sp{seg['speaker_id']}: {seg['text']}")
```

更多範例見 `scripts/qc_simulator.py`。

---

## 18. 待驗證項目（給接手者）

### 18.1 高優先（M1-M2 階段）

| ID | 項目 | 驗證方式 |
|---|---|---|
| V1 | vLLM 在 RTX 6000 Ada 48GB 啟動成功 | M1 |
| V2 | ASR-7B 中文 hotwords 效果 | M1，準備中文音檔 |
| V3 | 60 分鐘長音檔不會 OOM | M1 |
| V4 | vLLM `--enable-lora` 是否相容 VibeVoice plugin | M1.5 |
| V5 | Backend container 透過 docker socket 操控其他 container | M2 |
| V6 | Arq + Redis 在容器內正常運作 | M2 |

### 18.2 中優先

| ID | 項目 |
|---|---|
| V7 | 雙卡 dual-split 時 GPU0 vLLM 不會被 GPU1 訓練影響 |
| V8 | merge_and_unload 後 model 大小、載入時間 |
| V9 | 訓練資料量門檻（多少分鐘 ≈ 多少 epochs 才有效） |
| V10 | 多格式匯入對 BOM / 編碼 / 全形空白容忍度 |
| V11 | WS 上傳大檔（>100MB）記憶體佔用 |
| V12 | Webhook 重試在 Redis 重啟後是否會丟資料 |

### 18.3 文件中標記

搜尋 `⚠️` 和 `🔬` 找所有待驗證項目。

---

## 19. 詞彙表

| 詞 | 解釋 |
|---|---|
| ASR | Automatic Speech Recognition |
| QC | Quality Control（語音質檢） |
| Rich Transcription | 含講者、時間軸、文字的結構化逐字稿 |
| Hotwords / Customized Context | 領域詞彙提示 |
| Diarization | 講者分離 |
| LoRA | Low-Rank Adaptation |
| PEFT | Parameter-Efficient Fine-Tuning |
| RTF | Real-Time Factor（處理時長 ÷ 音檔時長） |
| TP / DP | Tensor Parallel / Data Parallel |
| KV Cache | Transformer 推論快取 |
| Profile | 部署模式抽象 |
| Idempotency | 同 key 多次請求視為同一筆 |
| HMAC | Hash-based Message Authentication Code |
| DLQ | Dead Letter Queue |
| Arq | Async Redis Queue（Python） |

---

## 附錄 A：上游檔案速查

| 想知道什麼 | 看哪裡 |
|---|---|
| API request/response | 📁 `vendor/VibeVoice/vllm_plugin/tests/test_api.py` |
| Auto-recovery 邏輯 | 📁 `.../tests/test_api_auto_recover.py` |
| vLLM 啟動參數 | 📁 `.../vllm_plugin/scripts/start_server.py` |
| Output 解析 / key mapping | 📁 `.../vibevoice/processor/vibevoice_asr_processor.py:490` |
| Prompt 組裝 | 📁 `.../vibevoice_asr_processor.py:340-370` |
| 訓練資料格式 | 📁 `.../finetuning-asr/toy_dataset/0.json` |
| LoRA 訓練參數 | 📁 `.../finetuning-asr/lora_finetune.py:44-85` |
| Inference with LoRA | 📁 `.../finetuning-asr/inference_lora.py` |
| 官方部署文件 | 📁 `.../docs/vibevoice-vllm-asr.md` |
| 微調文件 | 📁 `.../finetuning-asr/README.md` |

## 附錄 B：常見錯誤排除

| 錯誤訊息 | 可能原因 | 排除 |
|---|---|---|
| `CUDA out of memory` (vLLM) | KV cache 太大 | 降 `VLLM_MAX_MODEL_LEN` 或 `VLLM_MAX_NUM_SEQS` |
| `CUDA out of memory` (Training) | batch / activation 太大 | 確認 `gradient_checkpointing=True`、batch=1 |
| `ffmpeg failed to decode` | 音檔損毀 | ffprobe 檢查；轉成 wav 16k |
| `Plugin not loaded` | vLLM entry point 錯 | 確認 vendor/VibeVoice mount 為 /app |
| `Repetition loop detected` | 模型卡重複 | 自動重試 with higher temperature |
| `Model not found` | active_model 路徑錯 | 檢查 data/merged 是否存在 |
| `Failed to parse JSON from transcription` | 模型輸出不規範 | 看 raw_text；可能 max_tokens 不夠 |
| `Docker socket permission denied` | 沒掛 socket | docker-compose 加 socket volume |
| `Redis connection refused` | redis service 未起 | `docker compose ps`，重啟 redis |
| `arq.worker.WorkerSettingsType not found` | worker import path 錯 | 確認 `app.worker.WorkerSettings` 存在 |

## 附錄 C：開發者快速指令

```bash
# 環境設定（一次性）
make setup

# 啟動全部
make up

# 停止全部
make down

# 看 logs
make logs                      # 所有
make logs-backend              # 只 backend
make logs-worker

# 重啟 backend / worker
make restart-backend
make restart-worker

# 進 backend container
make shell-backend

# 跑 backend tests
make test

# 跑 frontend dev server（另一 terminal）
make frontend-dev

# 部署驗證
./scripts/verify_deployment.sh

# QC 整合模擬
python scripts/qc_simulator.py --help
```

---

**文件結束**

接手者請從 §0.2「開發環境快速理解清單」開始。實作中如發現本文件描述與上游不一致或有更新，請更新本文件並標記版本（在文件最上方）。
