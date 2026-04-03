from paper_agent.schemas import Citation, SourceSummary

from .types import AgentCitation, AgentOutput


def coerce_output(final_output: object) -> AgentOutput:
    if isinstance(final_output, AgentOutput):
        return final_output
    if isinstance(final_output, str):
        return AgentOutput.model_validate_json(final_output)
    return AgentOutput.model_validate(final_output)


def merge_citations(
    citations: list[AgentCitation],
    local_citations: dict[str, Citation],
) -> list[Citation]:
    merged: dict[tuple[str, str], Citation] = {}

    for citation in local_citations.values():
        merged[(citation.source_type, citation.url or citation.source_page_url or citation.title)] = citation

    for citation in citations:
        normalized = Citation(
            title=citation.title,
            url=citation.url,
            source_page_url=citation.source_page_url,
            venue=citation.venue,
            year=citation.year,
            source_type="web_search" if citation.source_type == "web_search" else "local_paper_db",
        )
        merged[(normalized.source_type, normalized.url or normalized.source_page_url or normalized.title)] = normalized

    return list(merged.values())


def build_sources(citations: list[Citation]) -> list[SourceSummary]:
    source_types = {citation.source_type for citation in citations}
    descriptions: list[SourceSummary] = []
    if "local_paper_db" in source_types:
        descriptions.append(
            SourceSummary(
                source_type="local_paper_db",
                description="Results retrieved from the curated local paper database.",
            )
        )
    if "web_search" in source_types:
        descriptions.append(
            SourceSummary(
                source_type="web_search",
                description="External web sources used as supplemental context.",
            )
        )
    return descriptions
