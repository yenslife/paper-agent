from paper_agent.schemas import Citation
from paper_agent.services.chat import AgentCitation, ChatService


def test_merge_citations_keeps_local_and_web_sources_distinct() -> None:
    service = ChatService.__new__(ChatService)
    local = {
        "1": Citation(
            title="Local Paper",
            url=None,
            source_page_url="https://example.com/local-list",
            venue="ICLR",
            year=2025,
            source_type="local_paper_db",
        )
    }
    remote = [
        AgentCitation(
            title="External Source",
            url="https://example.com/external",
            source_page_url=None,
            venue=None,
            year=None,
            source_type="web_search",
        )
    ]

    citations = service._merge_citations(remote, local)

    assert {citation.source_type for citation in citations} == {"local_paper_db", "web_search"}


def test_build_sources_summarizes_available_source_types() -> None:
    service = ChatService.__new__(ChatService)
    citations = [
        Citation(
            title="Local Paper",
            url=None,
            source_page_url="https://example.com/local-list",
            source_type="local_paper_db",
        ),
        Citation(
            title="External Source",
            url="https://example.com/external",
            source_page_url=None,
            source_type="web_search",
        ),
    ]

    sources = service._build_sources(citations)

    assert len(sources) == 2
    assert {source.source_type for source in sources} == {"local_paper_db", "web_search"}
