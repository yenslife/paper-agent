# Paper Agent

一個以 `FastAPI`、`openai-agents`、`Postgres + pgvector` 為核心的研究助理系統。它會讀取你手動整理的 accepted paper Markdown 清單，自動抓取摘要並建立向量索引，讓聊天 Agent 可以優先從本地 paper 資料庫找資料，必要時再透過 paper-specific lookup 與 PDF 轉 Markdown 工具補充內容。

## 功能

- 匯入 accepted paper Markdown 清單
- 自動抓取論文摘要並建立 embedding
- 用 `pgvector` 做 paper retrieval
- 用 `openai-agents` 建立可呼叫本地 paper tools 的聊天 Agent
- 支援 `Semantic Scholar -> OpenAlex` 的 paper-specific web lookup fallback
- 支援從 `NDSS`、`USENIX`、`IEEE`、`ACM`、`arXiv` 頁面或 URL 推導 paper metadata / PDF
- 支援將 PDF 轉成 Markdown，讓 Agent 分段閱讀論文內容
- 極簡 React + shadcn/ui 風格前端

## 專案結構

- `backend/`: FastAPI backend、測試與 Python 專案設定
- `browser-service/`: 獨立的 browser automation service，專門跑 `browser-use`
- `frontend/`: React frontend 與 Vite/Tailwind 設定
- `docs/`: 系統設計與功能整理

## 文件

- `docs/conference-binding.md`: conference entity 與綁定邏輯
- `docs/system-changes.md`: 近期主要修改整理

## 環境需求

- Python 3.12+
- Node.js 20+
- `pnpm`
- Docker + Docker Compose
- OpenAI API key

## 必要環境變數

請自行建立 `.env`。可以直接從 `.env.example` 複製：

```bash
cp .env.example .env
```

至少需要確認：

```bash
OPENAI_API_KEY=...
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/paper_agent
BROWSER_SERVICE_URL=http://localhost:8001
```

可選設定：

```bash
OPENAI_MODEL=gpt-4.1-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
SEMANTIC_SCHOLAR_API_KEY=
BROWSER_USE_MODEL=gpt-4.1-mini
BROWSER_USE_HEADLESS=true
BROWSER_USE_MAX_STEPS=12
BROWSER_USE_EXECUTABLE_PATH=
FRONTEND_ORIGIN=http://localhost:5173
VITE_API_BASE_URL=/api
```

## Docker Compose

專案提供四個容器：

- `postgres`: 使用 `pgvector/pgvector:pg16`，提供 paper agent 的向量資料庫
- `adminer`: 提供資料庫瀏覽介面
- `backend`: FastAPI API server
- `browser-service`: 獨立的 browser automation API，供 backend 轉呼叫
- `frontend`: 以 `nginx` 提供建置後的 React 前端
- PostgreSQL 會在第一次建立 volume 時，自動套用 `docker/postgres/init/*.sql`，建立 extension、enum、tables 與 indexes
- compose 模式下前端會透過 `nginx` 將 `/api/*` 代理到 backend，不需要瀏覽器直接跨來源打 `localhost:8000`
- backend image 會在建置時安裝 `browser-use` 所需的 Chromium，讓 `browser_browse_task` 可在 Docker 內執行

完整啟動前後端與資料庫：

```bash
docker compose up -d
```

服務位置：

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- Browser Service API: `http://localhost:8001`
- Adminer: `http://localhost:8080`

停止：

```bash
docker compose down
```

若也要連同資料庫 volume 一起清掉：

```bash
docker compose down -v
```

若你剛更新了 backend image 中的 browser 相關依賴，請記得重建：

```bash
docker compose up -d --build backend
```

Adminer 連線資訊：

- System: `PostgreSQL`
- Server: `postgres`（若你是從 Adminer 容器內連）
- Username: `postgres`
- Password: `postgres`
- Database: `paper_agent`

若你改成在本機直接跑 backend，`.env` 中的 `DATABASE_URL` 應維持：

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/paper_agent
```

因為這種模式下 backend 是在你主機上跑，不是在 compose network 裡跑，所以 host 要用 `localhost`，不是 `postgres`。

## 本機開發模式

若你想保留 hot reload，可以只用 compose 跑資料庫與 browser-service，再本機分別跑 backend/frontend：

```bash
docker compose up -d postgres adminer browser-service
cd backend && uv run uvicorn paper_agent.main:app --reload
cd frontend && pnpm dev
```

本機前端預設會在 `http://localhost:5173`，並透過 `VITE_API_BASE_URL` 連線到 backend。若未設定，預設連 `http://localhost:8000`。

## Markdown 匯入格式

系統現在會優先使用 LLM 解析 Markdown，再退回規則 parser 當 fallback，所以格式可以比以前自由。不過為了提升解析穩定度，仍然建議每篇 paper 至少清楚出現 `title + url`，而且 `venue/year` 盡量放在 heading 或附近文字中。

穩定度最高的格式仍然是：

```md
## ICLR 2025

- [Paper Title A](https://openreview.net/forum?id=xxx)
- [Paper Title B](https://arxiv.org/abs/2501.00001)
```

也接受：

```md
- Paper Title C - https://example.com/paper
```

heading 中若包含 venue 與年份，系統會自動保留。

## 主要 API

- `POST /papers/import-markdown`
- `GET /papers/import-jobs/{job_id}`
- `GET /papers`
- `POST /chat`

`POST /papers/import-markdown` 現在會先建立匯入 job 並立即回傳，前端再輪詢 job 狀態，不再同步等待整批 paper 完成。

## Agent 工具能力

目前聊天 Agent 除了本地 paper retrieval 外，還有以下 paper-specific 工具：

- `search_papers`
  - 以向量檢索查本地資料庫中的相關 papers
- `get_paper_details`
  - 取得已檢索 papers 的詳細資料
- `find_paper_abstract`
  - 先查本地資料庫，必要時再用外部 paper lookup 補 abstract
- `lookup_paper_on_web`
  - 針對特定 paper 查找 paper page、PDF、slides、video、DOI 等 metadata
- `convert_pdf_url_to_markdown`
  - 直接將 PDF URL 轉成 Markdown
- `convert_paper_pdf_to_markdown`
  - 先解析特定 paper 的 PDF URL，再把 PDF 轉成 Markdown

其中 `lookup_paper_on_web` 的目前支援來源如下：

- domain / venue extractor
  - `NDSS`
  - `USENIX`
  - `IEEE`
  - `ACM`
  - `arXiv`
- metadata fallback
  - `Semantic Scholar`
  - `OpenAlex`

`convert_pdf_url_to_markdown` 與 `convert_paper_pdf_to_markdown` 會回傳 chunked Markdown，Agent 可用 `start_char` / `max_chars` 逐段閱讀 PDF，避免一次把整份論文塞進 context。

另外也提供獨立的瀏覽器工具：

- `browser_browse_task`
  - 讓 Agent 在 page-specific extractor 與 paper lookup 都不足時，轉呼叫 `browser-service`
  - 真正的 `browser-use` 與 Chromium runtime 被隔離在 `browser-service`，避免主 backend 的 OpenAI 依賴衝突

## 測試

```bash
cd backend && uv run pytest
cd backend && uv run python -m py_compile $(find paper_agent -name '*.py' -print)
cd frontend && pnpm build
```

## TODO

- `browser-use` 獨立工具
  - 已拆成獨立 `browser-service`
  - 後續可再補更細的任務模板與權限控制
- 擴充更多 paper page extractor
  - 優先考慮 `OpenReview`
  - 視需要補強更多 conference proceedings / publisher 網站
- 將外部 paper lookup 結果回寫到本地資料庫
  - 例如 DOI、PDF URL、abstract、slides、video 等欄位
  - 避免重複查詢外部來源

## 初始化資料庫

若你不是用 compose 第一次初始化資料庫，或想手動補建既有資料庫結構，可執行：

```bash
cd backend
uv run python -m paper_agent.scripts.init_db
```

這個腳本會：

- 若資料庫不存在則建立它
- 在目標資料庫中補齊 backend 需要的 extension 與 tables
