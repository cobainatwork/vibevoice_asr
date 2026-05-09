# M3 Frontend Admin 設計規格

**狀態**：approved（brainstorming 階段）
**對應里程碑**：SPEC.md §14 M3
**最後更新**：2026-05-09
**範圍依據**：scope B（M3 acceptance + System 監控頁）

---

## 一、 範圍

### 1.1 In Scope（M3 範圍）

實作以下 6 頁與相關共用元件：

| 路由 | 頁面 | 主要元件 |
|---|---|---|
| `/` | Projects | 卡片網格 + Create / Edit modal |
| `/projects/:id/hotwords` | Hotwords | Chip input + 匯入 / 匯出 |
| `/projects/:id/offline` | Offline | Upload dropzone + JobList |
| `/projects/:id/edit/:itemId?mode=view` | TranscriptViewer | WaveformPlayer + segments list（read-only） |
| `/projects/:id/edit/:itemId?mode=edit` | TranscriptEditor | WaveformPlayer + Regions + Focus editor |
| `/system` | System | Health / vLLM / Profile / Queue 4 panel |

共用元件：`Sidebar`、`WaveformPlayer`、`SegmentListItem`、`SegmentFocusEditor`、`JobList`、`JobStatusBadge`、`HotwordsChips`、`UploadDropzone`、`Toast`。

### 1.2 Out of Scope

以下頁面在 M3.5 / M4 / M6 處理；M3 階段路由仍存在但只 redirect 到 Projects 並提示「尚未開放」：

- Datasets（M3.5）
- Training / TrainingDetail（M4）
- Models（M4）
- ApiKeys / Webhook / IntegrationCalls（M6）

Frontend 自動化測試（vitest / playwright）列為 backlog；M3 採人工 e2e（依 SPEC.md §14.2 步驟）。

---

## 二、 Layout 與導覽

### 2.1 兩層 Sidebar（240 px 固定寬）

```
┌────────────────────────┐
│ VibeVoice ASR          │  brand
├────────────────────────┤
│ ▾ 客服質檢            │  project switcher（dropdown）
├────────────────────────┤
│ 本專案                 │  section label
│   Hotwords             │
│   離線轉錄            │  
│   校正工作台          │
├────────────────────────┤
│ 系統                   │  底部固定區
│   服務狀態            │
└────────────────────────┘
```

- Project switcher：點擊展開 dropdown 列出所有 projects + 「+ 新增專案」入口
- 切換 project 時 navigate 至 `/projects/:newId/<同子頁>`，若該子頁不存在則 fallback 到 hotwords
- Active 子頁底色 `bg-blue-50`、左 border `border-l-2 border-blue-500`

### 2.2 Main 區結構

```
┌──────────────────────────────────────────────────┐
│ Page Header（h2 標題 + 右上 action buttons）    │
├──────────────────────────────────────────────────┤
│ Page Content                                     │
│ max-w-7xl mx-auto px-6 py-4                      │
└──────────────────────────────────────────────────┘
```

Toast 容器固定 `bottom-4 right-4`，z-index 50。

---

## 三、 Routing

維持既有 `App.tsx`：

```tsx
<Route path="/" element={<Projects />} />
<Route path="/projects/:id/hotwords" element={<Hotwords />} />
<Route path="/projects/:id/offline" element={<Offline />} />
<Route path="/projects/:id/edit/:itemId" element={<Editor />} />
<Route path="/system" element={<System />} />
{/* 其餘 stub routes 保留並 redirect 到 / 並 toast 提示 */}
<Route path="*" element={<Navigate to="/" replace />} />
```

`Editor` 頁讀 `?mode=view|edit` query param（預設 view），切換不需重新載入資料。

---

## 四、 State 管理

### 4.1 Zustand Stores

| Store | State | 範圍 |
|---|---|---|
| `projectStore` | `projects[]`、`currentProjectId`、`refetch()` | 全域 |
| `editorStore` | `segments[]`、`originalSegments[]`（mount 時 snapshot，用於 dirty 判定）、`activeIdx`、`saving`、`lastSavedAt` | Editor 頁 mount 時建立、unmount 時清理 |
| `toastStore` | `toasts[]` queue（含 id / level / message / timeoutMs） | 全域 |

### 4.2 不進 store 的部分

`jobs`、`system info`、`hotwords`、`vllm status` 等以 hooks + local state 管理，避免不必要的全域耦合。

### 4.3 Polling 策略

| 場景 | 間隔 |
|---|---|
| Offline 頁的 active job 列表（status ≠ done/failed/cancelled 任一者） | 2 秒 |
| Offline 頁無 active job | 停止 poll，僅手動 refresh |
| System 頁 health / queue / vllm_status | 10 秒 |
| System 頁 profile（不變） | 一次性 fetch |

---

## 五、 各頁規格

### 5.1 Projects（`/`）

#### Layout

- 卡片網格（`grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4`）
- 每卡顯示：name、description（行數限 2 行 ellipsis）、`hotwords.length` 個 hotwords、`active_model` name、updated_at
- 右上「+ 新增專案」按鈕

#### Modal：Create / Edit

欄位：name（required，1-100）、description（optional）、webhook_url（optional URL）、hotwords（多列 textarea，逗號分隔；M3 階段以 textarea 即可，detailed chip UI 留 Hotwords 頁）。

驗證用 react-hook-form + zod，submit 後 toast 成功 / 失敗。

#### 互動

- 點卡片任意處 → 進該 project 的 Hotwords 頁（預設子頁）
- 卡片右上「⋯」menu：編輯、刪除（含 confirm dialog）
- 刪除若 backend 回 IntegrityError（有 jobs 關聯）→ toast「請先刪除該 project 的 jobs」

### 5.2 Hotwords（`/projects/:id/hotwords`）

#### Layout

```
[Page Header: Hotwords]    [匯入] [匯出] [儲存（變更時亮）]
─────────────────────────────────────────────────────────
[ tag1 × ] [ tag2 × ] [ tag3 × ] ... [ + 輸入新詞... ]
─────────────────────────────────────────────────────────
共 12 個詞 · 上次更新 5 分鐘前
```

#### Chip Input 行為

- Enter 或逗號送出（trim 空白、去重）
- 每 chip 右側 `×` 刪除
- 拖拉重新排序（M3 不支援；列為 backlog）

#### 匯入 / 匯出

| 動作 | UX |
|---|---|
| 匯出 | 點「匯出」按鈕 → 直接下載 `hotwords-{project_name}-{YYYYMMDD}.txt`（一詞一行 UTF-8 BOM-less） |
| 匯入 | 點「匯入」→ 跳檔案選擇器（accept `.txt`） + radio「append」/「replace」 → 上傳前 preview「將新增 N 個、覆蓋 M 個」→ confirm 後送 server → 成功後 chip 區即時更新 |

匯入 dedupe 規則：完全字串比對（case-sensitive）。append 模式下重複詞略過。

CSV / JSON 列為 backlog。

#### Save 行為

- 改動後右上「儲存」按鈕 enable
- Save 成功 toast「✓ 已儲存」+ 「上次更新」時間更新
- Discard 用瀏覽器原生 `beforeunload` 攔截

### 5.3 Offline（`/projects/:id/offline`）

#### Layout

```
[Page Header: 離線轉錄]
─────────────────────────────────────────────────────────
┌── Upload Dropzone（高 160 px）─────────────────┐
│  拖入音檔，或點擊選擇  ·  支援 wav/mp3/m4a/mp4    │
│  上限 500 MB / 4 小時                           │
└──────────────────────────────────────────────────┘

[篩選: 全部 status ▾]                  [手動 refresh ↻]
─────────────────────────────────────────────────────────
JobList（最新在上）：
┌──────────────────────────────────────────────────┐
│ ● done    14:30  call-001.mp3   17 s   [檢視] │
│ ● running 14:32  long-meeting.mp3  進度 45%   │
│ ● failed  14:25  bad-audio.wav         [檢視] │
│   audio_unreadable                            │
└──────────────────────────────────────────────────┘
```

#### UploadDropzone 行為

- Drag-over：邊框轉 `border-blue-500 border-dashed`
- 檔案 drop：先檢查 size & extension（client-side 提早 fail），通過後 POST `/api/admin/transcribe`（multipart，`file` + `project_id`）
- Upload 期間 dropzone 內顯示 progress bar（如 backend 不支援 progress event 則用 indeterminate spinner）
- 成功 → toast「✓ Job 已建立」、JobList 新增該 row
- 失敗 → toast 顯示 backend `detail.detail`

#### JobList 行為

- 每 row：`JobStatusBadge` + 建立時間 + filename + duration + 動作按鈕
- Status `done`：「檢視」按鈕跳 Editor 頁 view mode
- Status `running` / `queued`：顯示 progress bar 與 chunks 進度（chunks_done/total）
- Status `failed`：紅字 error code、滑鼠 hover 顯示完整 error
- Polling 規則見 §4.3

### 5.4 TranscriptViewer（`/projects/:id/edit/:itemId?mode=view`）

#### Layout

與 Editor 同主結構，但右側 Focus Editor 換成 read-only segment 詳情；左列表行為一致。

```
[Header] 檔名 · 時長 · 模型 · hotwords 用詞 │ [編輯模式]
─────────────────────────────────────────────────────────
[ WaveformPlayer（高 80 px，含 regions）            ]
─────────────────────────────────────────────────────────
[左列表 38%][ 右側顯示當前段落 read-only（plain text）]
```

#### 互動

- 點 region 或左 row → 跳音檔到該段、focus 該段
- Space：play / pause
- 右側顯示 segment 全文 + speaker + 時間範圍（不能編輯）
- 右上「編輯模式」按鈕切換到 Editor

### 5.5 TranscriptEditor（`/projects/:id/edit/:itemId?mode=edit`）

#### Layout（Focus Editor / Descript 風）

```
[Header] 檔名 · ✓ 已儲存 N 秒前 │ [檢視模式]
─────────────────────────────────────────────────────────
[ WaveformPlayer + Regions（含 active region 高亮）  ]
─────────────────────────────────────────────────────────
┌─ 左 38% ─────────┬─ 右 62% Active Segment Editor ────┐
│ 00:00 Sp1 微軟… │ SEGMENT 2 / 4                     │
│ ►00:03 Sp2 是的…│ ⏱ 00:03.45 → 00:08.20             │
│ 00:08 Sp1 那 hot…│ 🎙 Speaker [▾ 2]                 │
│ 00:12 Sp2 透過…  │ ┌─ text editor ──────────────┐   │
│                  │ │ 是的，VibeVoice 支援 50 種…│   │
│                  │ └────────────────────────────┘   │
│                  │ [↰ 拆段] [⇲ 合併下] [⌫ 刪除]    │
└──────────────────┴───────────────────────────────────┘
```

#### Segment 操作（M3 範圍）

| 操作 | 規則 |
|---|---|
| 改文字 | textarea，autosize，3 秒 idle 觸發 save |
| 改 speaker | dropdown，立即 dirty |
| 改時間（拖 region 邊界 / 直接輸入） | 吸附 0.05 秒網格 |

> Split / Merge / Delete segment 等結構性操作移至 backlog（M3.5）。M3 僅支援既有 segments 的 inline 編輯與邊界調整。理由：split 點對應 audio time 缺乏自然 UX（文字游標 vs 波形時間軸映射不對齊），M3.5 dataset 化階段再設計。

#### 鍵盤快捷鍵（集中於 `lib/keyboard.ts`）

| 鍵 | 行為 |
|---|---|
| `Space` | 播放 / 暫停（focus 不在 input/textarea 才生效） |
| `←` / `→` | 跳前 / 後 5 秒 |
| `Tab` / `Shift+Tab` | 下一 / 上一段 + 自動播該段 |
| `M` | Mute / Unmute |
| `/` | Focus 上方搜尋輸入框 |
| `Esc` | 離開當前 text 編輯 |
| `Ctrl/Cmd + S` | 手動 save + toast |

#### Auto-save 流程（`useAutoSave` hook）

```
編輯 → debounce 3s
切換 segment → flush（立即 save）
beforeunload → 若 dirty 跳 confirm
Ctrl+S → flush + toast
Save 期間 toolbar 顯示「儲存中…」
```

實作：用 `useEffect` 監聽 `editorStore.dirtyIndices`，debounce 後 PATCH `/api/admin/jobs/:id/segments`。失敗時保留 dirty 狀態並 toast「儲存失敗，請重試」。

### 5.6 System（`/system`）

#### Layout

四個 panel 並排（`grid grid-cols-1 md:grid-cols-2 gap-4`）：

| Panel | 內容 |
|---|---|
| Health | DB / Redis / vLLM 三個狀態（綠 / 黃 / 紅 dot + 文字），最後檢查時間 |
| vLLM Status | status / model / uptime；mock 模式特殊樣式提示 |
| Profile | profile 名稱、GPU 配置、TP/DP、最大並發數、是否可同時訓練 |
| Queue | pending / running / oldest_age_sec；queue 滿時紅色警示 |

Polling 見 §4.3。Page Header 右上「重新載入」手動 refresh。

---

## 六、 共用元件規格

### 6.1 Sidebar

- Props：無（從 `projectStore` 與 `useLocation` 自帶 state）
- 切 project 時保留「同子頁」邏輯：若當前 path 為 `/projects/old/X`，切到 new 後跳 `/projects/new/X`

### 6.2 WaveformPlayer

- Props：`audioUrl`、`segments`（用於 regions）、`activeIdx`、`onSeek(time)`、`onRegionClick(idx)`、`onRegionResize(idx, newStart, newEnd)`、`editable`
- 使用 wavesurfer.js v7 + Regions plugin
- Regions 顏色：active 段 `rgba(249, 115, 22, 0.25)` 含 orange 邊框，其他 `rgba(59, 130, 246, 0.18)` blue 邊框
- 控制列：Play / Pause / 當前時間 / 總時長 / Mute / 速度（0.5x / 1x / 1.5x / 2x）

### 6.3 SegmentListItem

- Props：`segment`、`active`、`dirty`、`onClick`
- 結構：`[時間戳 mono] Sp{id} {text 截斷 60 字}`
- Active：`border-l-2 border-blue-500 bg-blue-50`
- Dirty：右側顯示橙色 dot

### 6.4 SegmentFocusEditor

- Props：`segment`、`onChange`、`onSplit`、`onMergeNext`、`onDelete`、`saving`
- 結構：見 §5.5 layout
- textarea 用 autosize（基於 `scrollHeight` 動態調整）

### 6.5 JobList、JobStatusBadge、HotwordsChips、UploadDropzone

依 §5 各頁規格描述。每個元件 props 介面在 implementation plan 階段細化。

### 6.6 Toast

- 結構：`{ id, level: 'info'|'success'|'warning'|'error', message, timeoutMs }`
- 預設 timeout：success 3 秒、info / warning 5 秒、error 8 秒（且需手動關）
- 同時最多 3 條，超出 dequeue 最舊
- 視覺：右下浮動，圖示 + 訊息 + 關閉 ×

---

## 七、 API Layer

### 7.1 `client.ts`

```ts
type ApiError = { code: string; detail: string };

async function request<T>(
  method, path, opts?: { body?, params?, signal? }
): Promise<T>
```

統一處理：
- Base URL 從 `import.meta.env.VITE_API_BASE`（預設 `http://localhost:8080`）
- 401 → toast「請重新登入」（M3 admin 內網無認證，但保留分支）
- 4xx → 抽出 `detail.detail` 顯示為 toast
- 5xx → toast「服務異常，請稍後再試」
- Network error → toast「網路連線失敗」

### 7.2 各模組

`projects.ts` / `jobs.ts` / `system.ts`：對應 backend admin endpoints，函式名與 endpoint 對齊（如 `listProjects()`、`createProject(data)`、`patchJobSegments(id, segments)`）。

### 7.3 Types

`types.ts` 從 backend `schemas.py` 手動翻譯，保留同欄位名稱（snake_case），後續可考慮接 OpenAPI 生成。

---

## 八、 後端微調（M3 範圍內 backend 加項）

### 8.1 `PATCH /api/admin/jobs/{id}/segments`

```
Request body: {"segments": [Segment, ...]}
Response: 200 JobOut
```

校驗：
- segments 升冪 by start_time
- 每段 start < end
- speaker_id ≥ 1
- text 非空
驗證失敗 → 400 + `code: "invalid_segments"`、`detail: <具體原因>`。

### 8.2 `GET /api/admin/projects/{id}/hotwords/export?format=txt`

```
Response: 200 text/plain; charset=utf-8
Content-Disposition: attachment; filename="hotwords-<safe_project_name>-<YYYYMMDD>.txt"
Body: 一詞一行
```

### 8.3 `POST /api/admin/projects/{id}/hotwords/import`

```
Request: multipart
  file: text/plain
  mode: "append" | "replace"
Response: 200 {hotwords: string[], added: number, replaced: number, skipped_duplicates: number}
```

實作要點：
- 解析 file：UTF-8 decode、splitlines、trim、過濾空行
- mode=append：與現有 list union（保留順序，新詞接尾、重複跳過）
- mode=replace：直接覆蓋
- 上限：單檔 ≤ 1 MB；超過 → 413

### 8.4 ErrorCode 增補

新增 `INVALID_SEGMENTS`（HTTP 400）。

---

## 九、 設計風格與 UX 細節

### 9.1 顏色

| 角色 | 值 |
|---|---|
| Primary | blue-500 `#3B82F6` |
| Hover / Active | blue-600 `#2563EB` |
| CTA accent | orange-500 `#F97316` |
| Background | slate-50 `#F8FAFC` |
| Surface | white |
| Border | slate-200 `#E2E8F0` |
| Text body | slate-900 `#0F172A` |
| Text muted | slate-600 `#475569` |
| Status done | green-500 |
| Status running / queued | blue-500（pulse） |
| Status failed | red-500 |
| Status cancelled | slate-400 |

### 9.2 Typography

- Body：Inter（Google Fonts，loaded via `<link>` in `index.html`）
- Mono：JetBrains Mono（時間戳、job_id、API key prefix）
- Headings：Inter，weight 600
- Body line-height 1.6、heading 1.3

### 9.3 互動細節

- 所有可點選元件 `cursor-pointer`
- Transitions 統一 `transition-colors duration-200`
- Focus ring：`focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2`
- Disabled：`opacity-50 cursor-not-allowed`
- Hover：背景色微調（不用 transform / scale 避免 layout shift）

### 9.4 響應式

- 桌面為主（≥1024 必滿足）
- Tablet（768-1023）：sidebar 縮為 icon-only（48 px 寬），main 全寬
- Mobile（<768）：M3 不支援，顯示「請使用桌面瀏覽器」提示頁

### 9.5 Accessibility

- 4.5:1 對比（已用 slate-900 / slate-600 確保）
- 所有圖示 button 帶 `aria-label`
- 鍵盤 navigation：Tab order 與視覺一致
- Modal 用 `role="dialog"` + focus trap
- `prefers-reduced-motion` 啟用時關閉所有 transition

---

## 十、 Error Handling 全景

| 來源 | 處理 |
|---|---|
| Network error | `client.ts` 統一 toast + retry 按鈕（如有 idempotent 操作） |
| 4xx with `code/detail` | toast 顯示 detail；特定 code 可有自訂 fallback（如 401 redirect） |
| 5xx | toast「服務異常」 |
| Validation error（client-side） | 表單欄位下方紅字 inline，不發 toast |
| Auto-save 失敗 | toolbar 紅字「儲存失敗，重試中…」+ 自動 retry 1 次後 toast「請手動 Ctrl+S 重試」 |
| Polling 失敗 | 連續 3 次失敗才 toast「無法取得最新狀態」，避免噪音 |

---

## 十一、 Testing 策略

### 11.1 後端（這次新增）

| 對象 | 測試 |
|---|---|
| `PATCH /jobs/{id}/segments` | 合法 / 非法（時間 overlap、speaker_id < 1、空 text）→ 200 / 400 |
| Hotwords export | 空 list、含中文、Content-Disposition header |
| Hotwords import append | 有重複 / 無重複 / 多空行 / UTF-8 BOM |
| Hotwords import replace | 整批換掉 |
| Hotwords import 超 1 MB | 413 |

加入既有 `tests/` 結構，使用 docker compose exec backend pytest 跑。

### 11.2 Frontend

M3 不做自動化測試。e2e 流程依 SPEC.md §14.2 步驟人工驗收：

1. 訪問 http://localhost:5173
2. 建 project「M3 測試」
3. 進 Hotwords 加 3 個詞 → 匯出 → 匯入（mode=replace）
4. 進 Offline 上傳 demo3-hotwords.wav
5. 等 status=done
6. 點檢視進 Viewer，點 timestamp 跳音檔
7. 切編輯模式，拖 region 邊界、改文字
8. 等 3 秒看 toolbar「✓ 已儲存」
9. 鍵盤快捷鍵測試（Space / ←→ / Tab / M / /）
10. 進 System 看 4 個 panel 全綠

---

## 十二、 Acceptance Criteria

對齊 SPEC.md §14.2 M3 + 補本 spec 範圍：

- [ ] 6 頁路由皆可進入
- [ ] Sidebar 切 project 維持當前子頁
- [ ] 可建立 / 編輯 / 刪除 project
- [ ] 可在 Hotwords 頁加減詞、匯入、匯出
- [ ] 可上傳音檔並看到 JobList 即時更新
- [ ] Job done 後可進 Viewer 看 segments、點 timestamp 跳音檔
- [ ] Viewer 可切 Editor 編輯 segments
- [ ] Editor 拖 region / 改文字 3 秒後自動儲存
- [ ] 鍵盤快捷鍵集合運作
- [ ] System 頁顯示 4 panel 並 polling
- [ ] 後端新增 3 個 endpoints 通過 unit test
- [ ] Light mode 4.5:1 對比
- [ ] 可在 Windows + Docker Desktop + MOCK_VLLM=true 跑通完整流程

---

## 十三、 Open Questions / Backlog

不阻 M3 推進，列為待辦：

- B1 Frontend 自動化測試（vitest / playwright）
- B2 Dark mode
- B3 Mobile / tablet 完整支援（目前桌面為主）
- B4 Hotwords import / export CSV / JSON 格式
- B5 Hotwords chip 拖拉重排
- B6 Editor undo / redo（目前只有 auto-save，沒 history）
- B7 Editor 多 segment 同時選取批次操作
- B8 Toast 系統升級為 sonner / react-hot-toast 等成熟 lib
- B9 OpenAPI 自動生成 TS types
- B10 System 頁 GPU info（M7）

---

## 十四、 實作順序建議（給 writing-plans 階段參考）

依依賴順序，推薦：

1. 後端 endpoints（PATCH segments、hotwords import/export）+ 單測
2. Frontend `client.ts` + types + toast 基礎建設
3. Sidebar + Layout
4. Projects 頁
5. Hotwords 頁（含匯入 / 匯出）
6. Offline 頁 + JobList + UploadDropzone
7. WaveformPlayer 共用元件
8. TranscriptViewer
9. TranscriptEditor（含 useAutoSave、useKeyboardShortcuts）
10. System 頁
11. e2e 驗收（依 §11.2 步驟）

---

**End of design spec.**
