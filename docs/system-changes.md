# 系統修改整理

這份文件整理目前 `Paper Agent` 已經完成的主要修改，方便後續開發與驗收。

## 1. 匯入流程改為 job-based

- `POST /papers/import-markdown` 不再同步等待整批匯入完成
- backend 先建立 `import_jobs`
- 前端輪詢 `GET /papers/import-jobs/{job_id}`
- UI 可顯示：
  - status
  - stage
  - stage_message
  - parsed / processed / imported / skipped / failed

## 2. Markdown parser 改為 LLM parse

- parser 使用 OpenAI `chat.completions.create(...)`
- schema-based JSON output
- 不使用 `responses.parse(...)`
- LLM 失敗時才 fallback 到 rule-based parser

## 3. 長文本切塊與 overlap

- 很長的 Markdown 會先切 chunks
- chunks 之間保留 overlap
- 每個 chunk 都會保留 Jina 產生的前置 header
  - `Title`
  - `URL Source`
  - `Published Time`
- 每個 chunk 都會重建成：
  - `header + Markdown Content: + chunk body`

## 4. parser chunk 平行化

- 不再逐 chunk 串行解析
- 改成有限度平行呼叫 API
- 用 semaphore 控制最大併發
- 預設 concurrency 目前是 `4`

## 5. paper 去重

目前有兩層去重：

- parser 聚合結果去重
- 寫入資料庫前再次和 DB 內容比對

策略：

- 有 `url` 時優先用 `url`
- 沒 `url` 時，用 normalize 過的 `title`
- 再配合 `source_page_url / venue / year`

## 6. metadata-only papers

現在 paper 不一定需要單篇 paper URL 才能入庫。

如果只有：

- `title`
- `conference source page`
- `venue`
- `year`

也可以入庫，狀態會是：

- `metadata_only`

並仍然建立 metadata embedding。

## 7. 前端 Paper records

已支援：

- 分頁
- 直接輸入頁碼跳轉
- keyword search
- 編輯單筆 paper
- 刪除單筆 paper
- 匯入進行時即時刷新總筆數與列表

## 8. Chat Agent

已支援：

- `openai-agents`
- trace
- `openai-agents[sqlalchemy]` session persistence
- 本地 paper retrieval
- 找特定 paper abstract
- dummy web search tool
- 前端中斷回覆按鈕

## 9. conference entity

新增 `conferences` table 與 `paper.conference_id`：

- parser 前先讀既有 conference labels
- parser 盡量重用既有會議名
- ingestion 寫入前做 conference resolve/create
- 前端可手動把單筆 paper 綁定到 conference entity

## 10. Docker schema initialization

現在 Docker 初始化時就會建立：

- enum
- papers
- import_jobs
- paper_embeddings
- conferences

新 volume 啟動後不需要再手動補 schema 才能運作。
