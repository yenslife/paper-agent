# Paper Agent

一個以 `FastAPI`、`openai-agents`、`Postgres + pgvector` 為核心的研究助理系統。它會讀取你手動整理的 accepted paper Markdown 清單，自動抓取摘要並建立向量索引，讓聊天 Agent 可以優先從本地 paper 資料庫找資料，必要時再用網路搜尋補充背景。

## 功能

- 匯入 accepted paper Markdown 清單
- 自動抓取論文摘要並建立 embedding
- 用 `pgvector` 做 paper retrieval
- 用 `openai-agents` 建立可呼叫本地 paper tools 與 `WebSearchTool()` 的聊天 Agent
- 極簡 React + shadcn/ui 風格前端

## 專案結構

- `backend/`: FastAPI backend、測試與 Python 專案設定
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
```

可選設定：

```bash
OPENAI_MODEL=gpt-4.1-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
FRONTEND_ORIGIN=http://localhost:5173
```

## 啟動 backend

```bash
docker compose up -d
cd backend
uv run uvicorn paper_agent.main:app --reload
```

API 預設會在 `http://localhost:8000`。

## 啟動 frontend

```bash
cd frontend
pnpm dev
```

前端預設會在 `http://localhost:5173`，並透過 `VITE_API_BASE_URL` 連線到 backend。若未設定，預設連 `http://localhost:8000`。

## Docker Compose

專案提供兩個容器：

- `postgres`: 使用 `pgvector/pgvector:pg16`，提供 paper agent 的向量資料庫
- `adminer`: 提供資料庫瀏覽介面
- PostgreSQL 會在第一次建立 volume 時，自動套用 `docker/postgres/init/*.sql`，建立 extension、enum、tables 與 indexes

啟動：

```bash
docker compose up -d
```

停止：

```bash
docker compose down
```

若也要連同資料庫 volume 一起清掉：

```bash
docker compose down -v
```

資料庫介面：

- Adminer: `http://localhost:8080`

Adminer 連線資訊：

- System: `PostgreSQL`
- Server: `postgres`（若你是從 Adminer 容器內連）
- Username: `postgres`
- Password: `postgres`
- Database: `paper_agent`

本機 backend 連 compose 裡的資料庫時，`.env` 中的 `DATABASE_URL` 應維持：

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/paper_agent
```

因為 backend 是在你主機上跑，不是在 compose network 裡跑，所以 host 要用 `localhost`，不是 `postgres`。

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

## 測試

```bash
cd backend && uv run pytest
cd backend && uv run python -m py_compile $(find paper_agent -name '*.py' -print)
cd frontend && pnpm build
```

## TODO

- `paper-specific web lookup`
  - 先不要做通用 web search engine integration
  - 優先做一個專門針對 paper 的外部查找能力
  - 目標是讓 agent 在本地資料不足時，可以依 `title + venue + year` 去查 paper page、OpenAlex、Semantic Scholar、arXiv、OpenReview 等來源
  - 這會比先接一般搜尋引擎更符合目前 `Paper Agent` 的核心用途

## 初始化資料庫

若你不是用 compose 第一次初始化資料庫，或想手動補建既有資料庫結構，可執行：

```bash
cd backend
uv run python -m paper_agent.scripts.init_db
```

這個腳本會：

- 若資料庫不存在則建立它
- 在目標資料庫中補齊 backend 需要的 extension 與 tables
