import asyncio
from collections import OrderedDict
from dataclasses import asdict, dataclass
from io import BytesIO
from urllib.parse import urlparse

import httpx
from markitdown import MarkItDown

from paper_agent.config import get_settings
from paper_agent.services.paper_lookup import PaperLookupService


@dataclass(slots=True)
class PdfMarkdownChunk:
    source_url: str
    resolved_pdf_url: str
    markdown: str
    start_char: int
    end_char: int
    total_chars: int
    has_more: bool
    provider: str = "markitdown"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class PdfMarkdownService:
    def __init__(
        self,
        paper_lookup_service: PaperLookupService,
        markitdown_client: MarkItDown | None = None,
    ) -> None:
        self.settings = get_settings()
        self.paper_lookup_service = paper_lookup_service
        self.markitdown = markitdown_client or MarkItDown(enable_plugins=False)
        self._cache: OrderedDict[str, str] = OrderedDict()

    async def convert_pdf_url_to_markdown(
        self,
        pdf_url: str,
        *,
        start_char: int = 0,
        max_chars: int = 12000,
    ) -> PdfMarkdownChunk:
        markdown = await self._get_or_convert_markdown(pdf_url)
        return self._slice_markdown(
            source_url=pdf_url,
            resolved_pdf_url=pdf_url,
            markdown=markdown,
            start_char=start_char,
            max_chars=max_chars,
        )

    async def convert_paper_url_to_markdown(
        self,
        *,
        title: str,
        paper_url: str | None = None,
        source_page_url: str | None = None,
        venue: str | None = None,
        year: int | None = None,
        start_char: int = 0,
        max_chars: int = 12000,
    ) -> PdfMarkdownChunk | None:
        if paper_url and self._looks_like_pdf_url(paper_url):
            markdown = await self._get_or_convert_markdown(paper_url)
            return self._slice_markdown(
                source_url=paper_url,
                resolved_pdf_url=paper_url,
                markdown=markdown,
                start_char=start_char,
                max_chars=max_chars,
            )

        lookup = await self.paper_lookup_service.lookup_paper(
            title=title,
            paper_url=paper_url,
            source_page_url=source_page_url,
            venue=venue,
            year=year,
        )
        if not lookup or not lookup.pdf_url:
            return None

        markdown = await self._get_or_convert_markdown(lookup.pdf_url)
        return self._slice_markdown(
            source_url=paper_url or source_page_url or lookup.url or lookup.pdf_url,
            resolved_pdf_url=lookup.pdf_url,
            markdown=markdown,
            start_char=start_char,
            max_chars=max_chars,
        )

    async def _get_or_convert_markdown(self, pdf_url: str) -> str:
        cached = self._cache.get(pdf_url)
        if cached is not None:
            self._cache.move_to_end(pdf_url)
            return cached

        headers = {"User-Agent": self.settings.paper_fetch_user_agent}
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.settings.http_timeout_seconds,
            headers=headers,
        ) as client:
            response = await client.get(pdf_url)
            response.raise_for_status()
            pdf_bytes = response.content

        markdown = await asyncio.to_thread(self._convert_bytes_to_markdown, pdf_bytes, pdf_url)
        self._remember(pdf_url, markdown)
        return markdown

    def _convert_bytes_to_markdown(self, pdf_bytes: bytes, pdf_url: str) -> str:
        extension = self._infer_extension(pdf_url)
        result = self.markitdown.convert_stream(
            BytesIO(pdf_bytes),
            file_extension=extension,
            url=pdf_url,
        )
        markdown = getattr(result, "text_content", None) or ""
        return markdown.strip()

    def _slice_markdown(
        self,
        *,
        source_url: str,
        resolved_pdf_url: str,
        markdown: str,
        start_char: int,
        max_chars: int,
    ) -> PdfMarkdownChunk:
        normalized_start = max(0, start_char)
        normalized_max = max(1000, max_chars)
        excerpt = markdown[normalized_start : normalized_start + normalized_max]
        end_char = normalized_start + len(excerpt)
        return PdfMarkdownChunk(
            source_url=source_url,
            resolved_pdf_url=resolved_pdf_url,
            markdown=excerpt,
            start_char=normalized_start,
            end_char=end_char,
            total_chars=len(markdown),
            has_more=end_char < len(markdown),
        )

    def _remember(self, pdf_url: str, markdown: str) -> None:
        self._cache[pdf_url] = markdown
        self._cache.move_to_end(pdf_url)
        while len(self._cache) > self.settings.pdf_markdown_cache_entries:
            self._cache.popitem(last=False)

    def _infer_extension(self, pdf_url: str) -> str:
        path = urlparse(pdf_url).path.lower()
        if path.endswith(".pdf"):
            return ".pdf"
        return ".pdf"

    def _looks_like_pdf_url(self, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.lower()
        return path.endswith(".pdf") or "/doi/pdf/" in path or "stamp.jsp" in path
