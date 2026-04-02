from paper_agent.services.paper_lookup import PaperLookupResult
from paper_agent.services.pdf_markdown import PdfMarkdownService


class DummyPaperLookupService:
    async def lookup_paper(self, **_: object) -> PaperLookupResult | None:
        return PaperLookupResult(
            provider="dummy",
            confidence=1.0,
            title="Dummy Paper",
            pdf_url="https://example.com/paper.pdf",
            url="https://example.com/paper",
        )


def test_slice_markdown_returns_chunk_metadata() -> None:
    service = PdfMarkdownService(DummyPaperLookupService())  # type: ignore[arg-type]

    chunk = service._slice_markdown(  # pyright: ignore[reportPrivateUsage]
        source_url="https://example.com/paper",
        resolved_pdf_url="https://example.com/paper.pdf",
        markdown="abcdefghij",
        start_char=2,
        max_chars=4,
    )

    assert chunk.markdown == "cdefghij"
    assert chunk.start_char == 2
    assert chunk.end_char == 10
    assert chunk.has_more is False


def test_convert_paper_url_to_markdown_uses_lookup_result(monkeypatch) -> None:
    service = PdfMarkdownService(DummyPaperLookupService())  # type: ignore[arg-type]

    async def fake_get_or_convert_markdown(pdf_url: str) -> str:
        assert pdf_url == "https://example.com/paper.pdf"
        return "0123456789abcdef"

    monkeypatch.setattr(service, "_get_or_convert_markdown", fake_get_or_convert_markdown)

    import asyncio

    chunk = asyncio.run(
        service.convert_paper_url_to_markdown(
            title="Dummy Paper",
            paper_url="https://example.com/paper",
            start_char=4,
            max_chars=6,
        )
    )

    assert chunk is not None
    assert chunk.resolved_pdf_url == "https://example.com/paper.pdf"
    assert chunk.start_char == 4
    assert chunk.end_char == 16


def test_convert_paper_url_to_markdown_accepts_direct_pdf_url(monkeypatch) -> None:
    service = PdfMarkdownService(DummyPaperLookupService())  # type: ignore[arg-type]

    async def fake_get_or_convert_markdown(pdf_url: str) -> str:
        assert pdf_url == "https://dl.acm.org/doi/pdf/10.1145/3719027.3744836"
        return "abcdefghijklmnopqrstuvwxyz"

    monkeypatch.setattr(service, "_get_or_convert_markdown", fake_get_or_convert_markdown)

    import asyncio

    chunk = asyncio.run(
        service.convert_paper_url_to_markdown(
            title="SecAlign: Defending Against Prompt Injection with Preference Optimization",
            paper_url="https://dl.acm.org/doi/pdf/10.1145/3719027.3744836",
            source_page_url="https://www.sigsac.org/ccs/CCS2025/accepted-papers/",
            venue="ACM CCS",
            year=2025,
            start_char=0,
            max_chars=12000,
        )
    )

    assert chunk is not None
    assert chunk.resolved_pdf_url == "https://dl.acm.org/doi/pdf/10.1145/3719027.3744836"
    assert chunk.markdown == "abcdefghijklmnopqrstuvwxyz"
