import asyncio
from dataclasses import asdict, dataclass

import httpx
from ddgs import DDGS

from paper_agent.config import get_settings


@dataclass(slots=True)
class WebSearchResultItem:
    title: str
    url: str
    snippet: str | None = None
    provider: str = "unknown"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class WebSearchService:
    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        ddgs_factory: type[DDGS] | None = None,
    ) -> None:
        self.settings = get_settings()
        self.http_client = http_client
        self.ddgs_factory = ddgs_factory or DDGS

    async def search(self, query: str, max_results: int | None = None) -> list[WebSearchResultItem]:
        limit = max_results or self.settings.web_search_max_results

        searxng_results = await self._search_via_searxng(query, limit)
        if searxng_results:
            return searxng_results

        return await self._search_via_ddgs(query, limit)

    async def _search_via_searxng(self, query: str, max_results: int) -> list[WebSearchResultItem]:
        if not self.settings.searxng_base_url:
            return []

        params = {
            "q": query,
            "format": "json",
            "language": "all",
        }
        headers = {
            "User-Agent": self.settings.paper_fetch_user_agent,
            "X-Real-IP": "127.0.0.1",
        }
        base_url = self.settings.searxng_base_url.rstrip("/")

        try:
            if self.http_client is not None:
                response = await self.http_client.get(f"{base_url}/search", params=params, headers=headers)
            else:
                async with httpx.AsyncClient(
                    follow_redirects=True,
                    timeout=self.settings.http_timeout_seconds,
                    headers=headers,
                ) as client:
                    response = await client.get(f"{base_url}/search", params=params)
            response.raise_for_status()
        except Exception:
            return []

        payload = response.json()
        results = payload.get("results", [])
        normalized: list[WebSearchResultItem] = []
        for item in results[:max_results]:
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            if not title or not url:
                continue
            normalized.append(
                WebSearchResultItem(
                    title=title,
                    url=url,
                    snippet=str(item.get("content") or "").strip() or None,
                    provider=f"searxng:{item.get('engine') or 'unknown'}",
                )
            )
        return normalized

    async def _search_via_ddgs(self, query: str, max_results: int) -> list[WebSearchResultItem]:
        def run_search() -> list[dict[str, object]]:
            ddgs = self.ddgs_factory()
            return ddgs.text(
                query,
                max_results=max_results,
                region="wt-wt",
                safesearch="moderate",
            )

        try:
            results = await asyncio.to_thread(run_search)
        except Exception:
            return []

        normalized: list[WebSearchResultItem] = []
        for item in results[:max_results]:
            title = str(item.get("title") or "").strip()
            url = str(item.get("href") or item.get("url") or "").strip()
            if not title or not url:
                continue
            normalized.append(
                WebSearchResultItem(
                    title=title,
                    url=url,
                    snippet=str(item.get("body") or item.get("snippet") or "").strip() or None,
                    provider="ddgs",
                )
            )
        return normalized
