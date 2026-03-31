import pytest

from paper_agent.services.markdown_parser import (
    ImportJobCancelledError,
    KnownConferenceLabel,
    MarkdownParser,
    ParsedPaper,
    extract_document_source_url,
    normalize_parsed_papers,
    normalize_title_for_dedupe,
    parse_markdown_papers_rule_based,
    split_markdown_into_chunks,
)


def test_parse_markdown_papers_with_heading_context() -> None:
    content = """
## ICLR 2025

- [Paper A](https://openreview.net/forum?id=abc)
- [Paper B](https://arxiv.org/abs/2501.00001)
"""
    parsed = parse_markdown_papers_rule_based(content)

    assert len(parsed) == 2
    assert parsed[0].title == "Paper A"
    assert parsed[0].venue == "ICLR"
    assert parsed[0].year == 2025
    assert parsed[1].url == "https://arxiv.org/abs/2501.00001"


def test_parse_markdown_papers_supports_text_links_and_deduplicates() -> None:
    content = """
- Paper A - https://example.com/a
- [Paper A duplicate](https://example.com/a)
"""
    parsed = parse_markdown_papers_rule_based(content)

    assert len(parsed) == 1
    assert parsed[0].title == "Paper A"


def test_normalize_parsed_papers_strips_values_and_deduplicates_urls() -> None:
    parsed = normalize_parsed_papers(
        [
            ParsedPaper(
                title="  Paper A  ",
                url=" https://example.com/a ",
                source_page_url=" https://example.com/list ",
                venue=" ICLR ",
                year=2025,
            ),
            ParsedPaper(title="Paper A duplicate", url="https://example.com/a", venue=None, year=None),
            ParsedPaper(title=" ", url="https://example.com/b", venue=None, year=None),
        ]
    )

    assert parsed == [
        ParsedPaper(
            title="Paper A",
            url="https://example.com/a",
            source_page_url="https://example.com/list",
            venue="ICLR",
            year=2025,
        )
    ]


def test_extract_document_source_url() -> None:
    content = "Title: Foo\nURL Source: https://example.com/list\n"
    assert extract_document_source_url(content) == "https://example.com/list"


def test_normalize_title_for_dedupe_ignores_punctuation_and_spacing() -> None:
    assert normalize_title_for_dedupe("PoisonedRAG: Knowledge Corruption Attacks") == normalize_title_for_dedupe(
        " PoisonedRAG  Knowledge Corruption Attacks "
    )


def test_normalize_parsed_papers_drops_overly_long_titles() -> None:
    parsed = normalize_parsed_papers(
        [
            ParsedPaper(title="A" * 600, url=None, source_page_url="https://example.com/list", venue="USENIX Security", year=2025),
            ParsedPaper(title="Valid Paper Title", url=None, source_page_url="https://example.com/list", venue="USENIX Security", year=2025),
        ]
    )

    assert [item.title for item in parsed] == ["Valid Paper Title"]


def test_split_markdown_into_chunks_adds_overlap_and_keeps_prefix() -> None:
    content = "\n".join(
        [
            "Title: Demo",
            "URL Source: https://example.com/list",
            "",
            "Markdown Content:",
            "Paper 1",
            "Author line 1",
            "Paper 2",
            "Author line 2",
            "Paper 3",
            "Author line 3",
        ]
    )

    chunks = split_markdown_into_chunks(content, max_chars=50, overlap_chars=12)

    assert len(chunks) >= 2
    assert all("URL Source: https://example.com/list" in chunk for chunk in chunks)
    assert all("Markdown Content:" in chunk for chunk in chunks)
    assert all("Title: Demo" in chunk for chunk in chunks)
    assert "Author line 1" in chunks[0]
    first_chunk_lines = set(chunks[0].splitlines())
    second_chunk_lines = set(chunks[1].splitlines())
    assert len(first_chunk_lines & second_chunk_lines) >= 1


def test_split_markdown_into_chunks_keeps_only_header_before_markdown_content() -> None:
    content = "\n".join(
        [
            "Title: USENIX Security '24 Fall Accepted Papers",
            "URL Source: https://www.usenix.org/conference/usenixsecurity24/fall-accepted-papers",
            "",
            "Published Time: 2024-04-30T13:22:34-07:00",
            "",
            "Markdown Content:",
            "[Hide details ▾](https://www.usenix.org/conference/usenixsecurity24/fall-accepted-papers#accordion)",
            "",
            "USENIX Security '24 has three submission deadlines.",
            "",
            "## [Towards Generic Database Management System Fuzzing](https://www.usenix.org/conference/usenixsecurity24/presentation/yang-yupeng)",
        ]
    )

    chunks = split_markdown_into_chunks(content, max_chars=80, overlap_chars=10)

    assert len(chunks) >= 2
    assert all("Title: USENIX Security '24 Fall Accepted Papers" in chunk for chunk in chunks)
    assert all("Published Time: 2024-04-30T13:22:34-07:00" in chunk for chunk in chunks)
    assert all("Markdown Content:" in chunk for chunk in chunks)
    assert all(chunk.count("Markdown Content:") == 1 for chunk in chunks)


class _FakeCompletions:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.index = 0
        self.calls: list[dict[str, object]] = []

    async def create(self, **_: object):
        self.calls.append(_)
        content = self.outputs[self.index]
        self.index += 1
        return type(
            "Response",
            (),
            {
                "choices": [
                    type(
                        "Choice",
                        (),
                        {
                            "message": type("Message", (), {"content": content})(),
                        },
                    )()
                ]
            },
        )()


class _FakeChat:
    def __init__(self, outputs: list[str]) -> None:
        self.completions = _FakeCompletions(outputs)


class _FakeClient:
    def __init__(self, outputs: list[str]) -> None:
        self.chat = _FakeChat(outputs)


@pytest.mark.asyncio
async def test_markdown_parser_merges_chunk_results_and_deduplicates() -> None:
    fake_client = _FakeClient([
        '{"papers":[{"title":"Paper A","url":null,"source_page_url":"https://example.com/list","venue":"USENIX Security","year":2025}]}',
        '{"papers":[{"title":"Paper A","url":null,"source_page_url":"https://example.com/list","venue":"USENIX Security","year":2025},{"title":"Paper B","url":null,"source_page_url":"https://example.com/list","venue":"USENIX Security","year":2025}]}',
    ])
    parser = MarkdownParser(client=fake_client)
    parser.settings.parser_chunk_size_chars = 50
    parser.settings.parser_chunk_overlap_chars = 12

    content = "\n".join(
        [
            "Title: Demo",
            "URL Source: https://example.com/list",
            "",
            "Markdown Content:",
            "Paper A",
            "Author line A",
            "Paper B",
            "Author line B",
            "Paper C",
            "Author line C",
        ]
    )

    parsed = await parser.parse_markdown_papers(content)

    assert [item.title for item in parsed] == ["Paper A", "Paper B"]


@pytest.mark.asyncio
async def test_markdown_parser_reuses_existing_conference_labels_in_prompt() -> None:
    fake_client = _FakeClient([
        '{"papers":[{"title":"Paper A","url":null,"source_page_url":"https://example.com/list","venue":"USENIX Security","year":2024}]}'
    ])
    parser = MarkdownParser(client=fake_client)

    await parser.parse_markdown_papers(
        "Title: Demo\nURL Source: https://example.com/list\n\nMarkdown Content:\nPaper A",
        existing_conferences=[
            KnownConferenceLabel(
                name="USENIX Security",
                year=2024,
                source_page_url="https://example.com/list",
            )
        ],
    )

    system_message = fake_client.chat.completions.calls[0]["messages"][0]["content"]  # type: ignore[index]
    assert "Existing conference labels:" in system_message
    assert "USENIX Security | source=https://example.com/list | year=2024" in system_message


@pytest.mark.asyncio
async def test_markdown_parser_propagates_cancellation() -> None:
    fake_client = _FakeClient([
        '{"papers":[{"title":"Paper A","url":null,"source_page_url":"https://example.com/list","venue":"USENIX Security","year":2025}]}',
        '{"papers":[{"title":"Paper B","url":null,"source_page_url":"https://example.com/list","venue":"USENIX Security","year":2025}]}',
    ])
    parser = MarkdownParser(client=fake_client)
    parser.settings.parser_chunk_size_chars = 50
    parser.settings.parser_chunk_overlap_chars = 12
    parser.settings.parser_max_concurrency = 1

    content = "\n".join(
        [
            "Title: Demo",
            "URL Source: https://example.com/list",
            "",
            "Markdown Content:",
            "Paper A",
            "Author line A",
            "Paper B",
            "Author line B",
            "Paper C",
            "Author line C",
        ]
    )

    checks = {"count": 0}

    async def cancel_check() -> bool:
        checks["count"] += 1
        return checks["count"] >= 2

    with pytest.raises(ImportJobCancelledError):
        await parser.parse_markdown_papers(content, cancel_check=cancel_check)
