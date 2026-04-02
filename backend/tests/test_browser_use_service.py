import asyncio

import httpx

from paper_agent.services.browser_use_service import BrowserUseService


class DummyResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.payload


class DummyClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.last_url: str | None = None
        self.last_json: dict[str, object] | None = None

    async def post(self, url: str, json: dict[str, object]) -> DummyResponse:
        self.last_url = url
        self.last_json = json
        return DummyResponse(self.payload)


def test_browser_use_service_calls_remote_browser_worker() -> None:
    client = DummyClient(
        {
            "status": "success",
            "task": "Find the PDF link.",
            "final_result": "Found the PDF link.",
            "urls": ["https://example.com/paper", "https://example.com/paper.pdf"],
            "extracted_content": ["Paper page loaded", "PDF link found"],
            "errors": [],
            "steps": 3,
        }
    )
    service = BrowserUseService(base_url="http://browser-service:8001", http_client=client)  # type: ignore[arg-type]

    result = asyncio.run(
        service.browse_task(
            task="Find the PDF link.",
            start_url="https://example.com/paper",
            max_steps=7,
        )
    )

    assert client.last_url == "http://browser-service:8001/browse"
    assert client.last_json == {
        "task": "Find the PDF link.",
        "start_url": "https://example.com/paper",
        "max_steps": 7,
    }
    assert result.status == "success"
    assert result.final_result == "Found the PDF link."
    assert result.urls[-1] == "https://example.com/paper.pdf"
    assert result.steps == 3


def test_browser_use_service_returns_structured_error_on_remote_http_failure() -> None:
    class FailingClient:
        async def post(self, url: str, json: dict[str, object]) -> DummyResponse:
            raise httpx.HTTPStatusError(
                "upstream error",
                request=httpx.Request("POST", url),
                response=httpx.Response(502, request=httpx.Request("POST", url)),
            )

    service = BrowserUseService(base_url="http://browser-service:8001", http_client=FailingClient())  # type: ignore[arg-type]

    result = asyncio.run(service.browse_task(task="Open the page and summarize it."))

    assert result.status == "error"
    assert result.errors
