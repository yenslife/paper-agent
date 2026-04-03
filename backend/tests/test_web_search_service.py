import asyncio

from paper_agent.services.web_search import WebSearchService


class DummyResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.payload


class DummyHttpClient:
    def __init__(self, payload: dict[str, object] | None = None, should_fail: bool = False) -> None:
        self.payload = payload or {}
        self.should_fail = should_fail
        self.last_url: str | None = None
        self.last_params: dict[str, object] | None = None

    async def get(self, url: str, params: dict[str, object], headers: dict[str, str]) -> DummyResponse:
        self.last_url = url
        self.last_params = params
        if self.should_fail:
            raise RuntimeError("boom")
        return DummyResponse(self.payload)


class DummyDDGS:
    def text(self, query: str, **kwargs):
        return [
            {
                "title": "Prompt Injection Guide",
                "href": "https://example.com/prompt-injection",
                "body": "A practical overview.",
            }
        ]


def test_web_search_service_prefers_searxng_results() -> None:
    service = WebSearchService(
        http_client=DummyHttpClient(
            {
                "results": [
                    {
                        "title": "USENIX Security 2025",
                        "url": "https://example.com/usenix-2025",
                        "content": "Accepted papers list.",
                        "engine": "duckduckgo",
                    }
                ]
            }
        ),
        ddgs_factory=DummyDDGS,
    )
    service.settings.searxng_base_url = "https://searx.example"

    results = asyncio.run(service.search("USENIX Security 2025", max_results=3))

    assert len(results) == 1
    assert results[0].provider == "searxng:duckduckgo"
    assert results[0].url == "https://example.com/usenix-2025"


def test_web_search_service_falls_back_to_ddgs_when_searxng_fails() -> None:
    service = WebSearchService(
        http_client=DummyHttpClient(should_fail=True),
        ddgs_factory=DummyDDGS,
    )
    service.settings.searxng_base_url = "https://searx.example"

    results = asyncio.run(service.search("prompt injection"))

    assert len(results) == 1
    assert results[0].provider == "ddgs"
    assert results[0].title == "Prompt Injection Guide"
