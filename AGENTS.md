# AGENTS.md

本文件整理這個專案在實際協作過程中已經確認過的開發慣例、架構偏好與 UI 方向，目的是讓新的 agent session 能更快進入狀況。

## 開發工具

### Python

- 使用 `uv` 進行 Python 開發。
- 新增或移除依賴請使用 `uv add`、`uv remove`，不要直接編輯 `pyproject.toml`。
- 執行 Python 程式、模組、測試與工具時，請優先使用：
  - `uv run pytest`
  - `uv run python -m py_compile ...`
- 若要改善終端輸出，優先考慮 `rich`。

### Frontend

- 使用 `pnpm`，不要使用 `npm`。
- frontend 變更後，至少驗證：
  - `pnpm build`

### 路徑

- 一般開發與文件內容優先使用相對路徑。
- 若是回覆使用者、需要可點擊檔案連結時，再使用絕對路徑。

### 安全性

- 不要直接讀取 `.env` 等可能含敏感資訊的檔案。
- 不要直接用 `docker compose config` 因為環境變數可能有敏感內容
- 若需要敏感操作或破壞性操作，必須先獲得人類同意。

## 文件與語言

- 文件以台灣常用的繁體中文撰寫。
- 若專有名詞不適合翻譯，可保留英文。

## Git Commit Message

- 格式如下：

```text
TYPE: SUBJECT

BODY

FOOTER
```

- `TYPE` 與 `SUBJECT` 使用英文，小寫
- `BODY` / `FOOTER` 可使用繁體中文。
- 若要提供 git commit 指令，請用多個 `-m`，不要在單一 `-m` 內用 `\n`。

## 專案理解原則

- 本專案屬於多服務協作型系統，但具體目錄與模組切分可能會隨重構演進。
- 不要把 `AGENTS.md` 視為「當前檔案樹的唯一真相」；若需要了解目前真實架構，應優先使用檢索工具查看最新程式碼與目錄結構。
- `AGENTS.md` 應描述：
  - 穩定的協作規則
  - 已反覆確認的設計偏好
  - 較高層次的架構原則
- `AGENTS.md` 不應過度依賴容易變動的實作細節，例如精確檔名、暫時性的 shim、或短期過渡結構。

### 穩定架構偏好

- chat 相關邏輯若持續膨脹，應優先以 package 或模組分層處理，不要把 orchestration、tools、events、prompt 全塞回單一檔案。
- `browser-use` 相關能力應優先維持為獨立服務，而不是直接塞進 backend 主 runtime。
- 一般 web search 應優先走免 API key 的方案；若有多層 fallback，應保持策略清楚且可觀察。

### 維護規則

- 若某次修改會讓 `AGENTS.md` 內描述的穩定慣例失真，修改者應主動評估是否需要同步更新 `AGENTS.md`。
- 若只是暫時性的重構過渡狀態，不要急著把短期細節寫進 `AGENTS.md`。
- 若未來結構改動很大，優先把 `AGENTS.md` 改寫為更抽象的原則，而不是持續堆疊過時的具體路徑。

## Agent 行為與工具策略

- `search_papers` 是語意搜尋，不是 keyword-only search。
- 結構化 metadata 問題才使用資料庫 schema / SQL 工具。
- SQL 不應取代 paper semantic retrieval。
- `web_search` 與 `browser_browse_task` 應視為可串接工具：
  1. 先用 `web_search` 找候選頁面
  2. 再用 `browser_browse_task` 深入頁面

## 前端 UI 協作偏好

### 整體風格

- 偏好黑白、極簡、偏 shadcn 的語言。
- 避免多餘外層容器與過度包裝。
- 頁面內容傾向直接落在主內容區，而不是再套一張大卡片。

### Chat 頁

- 聊天頁應接近現代 chatbot / ChatGPT 風格。
- 目前確認過的偏好：
  - 不需要重複 header
  - 底部使用懸浮膠囊輸入框
  - 輸入框是獨立浮動元素，不要再有整條背景容器
  - 頁面本身不要雙重滾動
  - 只有聊天歷史區可以滾動
  - 送出訊息後自動定位到最新 user message

### Chat 輸入框

- placeholder 與 caret 要視覺對齊。
- textarea 要能自動長高，但有最大高度；超過後再內部滾動。
- `⌘ + Enter` / `Ctrl + Enter` 可送出訊息。

### Chat 工具泡泡

- 前端應顯示 agent 的工具使用過程。
- 每次工具呼叫都是一個獨立泡泡。
- 工具泡泡的進階資訊採「預設收合、按箭頭展開」模式。
- 展開後保留通用 JSON 格式即可，不要為每個工具做客製化 UI。
- 進階資訊可包含：
  - `arguments`
  - `result`
  - `started_at`
  - `ended_at`
  - `duration_ms`

### Markdown Renderer

- chat assistant 回覆使用正式 Markdown renderer。
- 若未來調整，優先維持通用 markdown 支援，而不是手寫簡化 parser。

### 深色模式

- 支援 `system / light / dark` 三態切換。
- dark mode 應避免殘留大量寫死的白底樣式。
- chat 深色模式背景偏好純色，不要使用明顯漸層。
- 懸浮按鈕與說明浮窗避免透明背景，以免被底圖干擾。

## 重構偏好

- 若檔案開始過胖，優先做結構重整。
- 重構時先保行為不變，再做第二輪清理。
- 對於值得抽離的邏輯：
  - 先拆 responsibility
  - 再整理 import path
  - 最後移除過渡檔

## 開發驗證習慣

- backend 變更後，至少跑：
  - `cd backend && uv run pytest`
  - `cd backend && uv run python -m py_compile ...`
- frontend 變更後，至少跑：
  - `cd frontend && pnpm build`

## Docker / Compose 開發習慣

- 這個專案的開發通常涉及多個相依服務，但實際需要啟動哪些服務，應以當前 README 與 compose 設定為準。
- 若修改 backend，通常要注意資料庫、browser service、web search service 等相依元件是否可用。
- 若修改 frontend，至少要確認有可用的 backend。
- 若修改瀏覽器自動化相關功能，應特別檢查 compose 內的 browser runtime 是否正常。

## 補充

- 如果新的需求會影響既有互動手感，先以目前已確認過的 UX 為基準，不要一次大改風格。
- 若要新增 trace / observability 類功能，優先整合到現有的 tool trace 流，而不是直接把前端綁到外部 trace 後台。
