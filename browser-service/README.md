# Browser Service

獨立的 browser automation service，專門承接 `browser-use` 與 Chromium runtime。

## 用途

- 讓主 backend 不需要直接依賴 `browser-use`
- 避免 `browser-use` 與主 backend 的 `openai` / `openai-agents` 版本衝突
- 提供一個簡單的 HTTP API 給主 backend 呼叫

## API

- `GET /health`
- `POST /browse`

`POST /browse` 輸入：

```json
{
  "task": "Browse the page and summarize it.",
  "start_url": "https://example.com",
  "max_steps": 12
}
```

## 本機啟動

```bash
cd browser-service
uv run uvicorn browser_service.main:app --reload --host 0.0.0.0 --port 8001
```
