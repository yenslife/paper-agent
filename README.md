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

專案提供六個容器：

- `postgres`: 使用 `pgvector/pgvector:pg16`，提供 paper agent 的向量資料庫
- `adminer`: 提供資料庫瀏覽介面
- `valkey`: 提供 `SearXNG` 所需的快取後端
- `searxng`: 免 API key 的開源 metasearch service，供 backend 的 `web_search` 工具使用
- `backend`: FastAPI API server
- `browser-service`: 獨立的 browser automation API，供 backend 轉呼叫
- `frontend`: 以 `nginx` 提供建置後的 React 前端
- PostgreSQL 會在第一次建立 volume 時，自動套用 `docker/postgres/init/*.sql`，建立 extension、enum、tables 與 indexes
- compose 模式下前端會透過 `nginx` 將 `/api/*` 代理到 backend，不需要瀏覽器直接跨來源打 `localhost:8000`
- backend image 會在建置時安裝 `browser-use` 所需的 Chromium，讓 `browser_browse_task` 可在 Docker 內執行
- compose 模式下 backend 會預設連到內部的 `searxng` 容器，所以 `web_search` 開箱即可使用，不需要額外 API key
- `searxng` 現在改成接近官方 `searxng-docker` 的 compose 啟動方式：使用官方 image、將整個設定目錄以 `rw` 掛到 `/etc/searxng`，並額外掛載 `/var/cache/searxng`
- 內建 `SearXNG` 目前採用本機 compose 用途的精簡設定，會停用 limiter，避免因未經反向代理而持續出現 `X-Forwarded-For` / `X-Real-IP` 的 botdetection 警告
- 專案會使用 `docker/searxng/config/` 當設定目錄，其中包含最小的 `settings.yml` 與 `limiter.toml`
- `SearXNG` 仍然保留 `server.secret_key` 這個安全機制；請務必在 `.env` 中設定 `SEARXNG_SECRET`，不要直接使用預設值
- 另外會將 `ahmia`、`torch` 預設停用，並移除目前最容易噴出 `CAPTCHA` / `403` / `timeout` 的 `duckduckgo`、`karmasearch`、`wikidata`，降低本機開發時的噪音與不穩定性
- `searxng` 的 healthcheck 只檢查首頁是否可用，不再用實際搜尋結果判斷健康，避免因外部搜尋引擎暫時失敗而被 compose 誤判成 unhealthy

建議先自行產生一組 `SearXNG` secret：

```bash
openssl rand -hex 32
```

然後把結果填到 `.env`：

```bash
SEARXNG_SECRET=your_generated_hex_secret
```

如果沒有設定，SearXNG 啟動時可能會出現類似 `server.secret_key is not changed` 的安全警告。

完整啟動前後端與資料庫：

```bash
docker compose up -d
```

服務位置：

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- Browser Service API: `http://localhost:8001`
- SearXNG: `http://localhost:8081`
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

### 開發者常用啟動方式

若你主要在改 backend：

```bash
docker compose up -d postgres adminer browser-service searxng
cd backend && uv run uvicorn paper_agent.main:app --reload
```

這種模式下：

- `postgres`: 提供資料庫
- `browser-service`: 提供 `browser_browse_task`
- `searxng`: 提供 `web_search`
- `adminer`: 方便檢查資料庫內容

若你主要在改 frontend：

```bash
docker compose up -d backend browser-service searxng postgres
cd frontend && pnpm dev
```

如果 backend 也想一起本機 hot reload，建議改成：

```bash
docker compose up -d postgres adminer browser-service searxng
cd backend && uv run uvicorn paper_agent.main:app --reload
cd frontend && pnpm dev
```

若你主要在改 `browser-service`：

```bash
docker compose up -d postgres searxng
cd browser-service && uv run uvicorn browser_service.main:app --reload --host 0.0.0.0 --port 8001
cd backend && uv run uvicorn paper_agent.main:app --reload
```

若你只想用完整容器模式測整體整合：

```bash
docker compose up -d --build
```

### 提交前請先自行跑測試

在推上 GitHub 或開 PR 前，建議至少先把 CI 對應的檢查在本機跑過一次：

```bash
cd backend
uv sync --frozen --dev
uv run pytest
uv run python -m py_compile $(find paper_agent -name '*.py' -print)

cd ../browser-service
uv sync --frozen
uv run python -m py_compile $(find src -name '*.py' -print)
uv run playwright install --with-deps chromium
uv run python scripts/playwright_smoke.py

cd ../frontend
pnpm install --frozen-lockfile
pnpm build
```

若你想連 `browser-use` 的真實 task 也一起測，可以額外提供 `OPENAI_API_KEY`：

```bash
cd browser-service
OPENAI_API_KEY=... uv run python scripts/browser_task_smoke.py
```

## 用 act 本地跑 GitHub Actions

若你想在 push 前直接本地模擬 GitHub Actions，可以用 [`act`](https://github.com/nektos/act)。

先安裝：

```bash
brew install act
```

列出目前 workflow / jobs：

```bash
act -l
```

跑整個 `pull_request` 事件：

```bash
act pull_request
```

只跑單一 job：

```bash
act pull_request -j backend
act pull_request -j browser-service
act pull_request -j frontend
```

第一次使用 `act` 時，它會要求你選 runner image。若你想手動指定，可用：

```bash
act pull_request -P ubuntu-latest=ghcr.io/catthehacker/ubuntu:act-latest
```

若你是 Apple Silicon（M 系列晶片）機器，建議直接加上：

```bash
act pull_request --container-architecture linux/amd64
```

只跑單一 job 也一樣：

```bash
act pull_request -j backend --container-architecture linux/amd64
act pull_request -j browser-service --container-architecture linux/amd64
act pull_request -j frontend --container-architecture linux/amd64
```

如果要把 secrets 帶進 `act`，建議建立一個本機用的 secret 檔案，例如 `.secrets.act`：

```bash
OPENAI_API_KEY=your_key_here
```

然後執行：

```bash
act pull_request --secret-file .secrets.act
```

`browser-service` 的真實 browser task smoke test 只有在 `OPENAI_API_KEY` 存在時才會執行；若沒有提供 secret，CI 仍會執行 Playwright 啟動測試與其他基本檢查。

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
  - 以語意向量檢索查本地資料庫中的相關 papers
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
- `inspect_database_schema`
  - 動態檢查目前資料庫 schema，讓 Agent 在執行 SQL 前先知道有哪些表與欄位
- `query_database_sql`
  - 執行受限的唯讀 SQL，用於查詢 conferences、papers、import jobs 等結構化 metadata
- `web_search`
  - 進行免 API key 的外部 web search，優先走 `SearXNG`，失敗時 fallback 到 `DDGS`

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

`web_search` 的設定方式：

- `docker compose` 模式下會自動啟動內建 `SearXNG` 容器，backend 預設連到 `http://searxng:8080`
- 若你想改成外部自建或可信任的 `SearXNG` instance，可在 `.env` 覆寫：
  - `SEARXNG_BASE_URL=https://your-searxng.example`
- 若 `SearXNG` 不可用，系統會自動 fallback 到 `DDGS`

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
