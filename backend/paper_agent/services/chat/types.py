from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from agents import RunContextWrapper
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from paper_agent.models import Paper
from paper_agent.schemas import Citation, ToolTrace
from paper_agent.services.browser_use_service import BrowserUseService
from paper_agent.services.database_query import DatabaseQueryService
from paper_agent.services.ingestion import IngestionService
from paper_agent.services.paper_lookup import PaperLookupService
from paper_agent.services.pdf_markdown import PdfMarkdownService
from paper_agent.services.retrieval import RetrievalService
from paper_agent.services.web_search import WebSearchService


class AgentCitation(BaseModel):
    title: str
    url: str | None = None
    source_page_url: str | None = None
    venue: str | None = None
    year: int | None = None
    source_type: str = Field(description="Either local_paper_db or web_search.")


class AgentOutput(BaseModel):
    answer: str
    citations: list[AgentCitation] = Field(default_factory=list)


@dataclass(slots=True)
class AgentContext:
    session: AsyncSession
    retrieval_service: RetrievalService
    ingestion_service: IngestionService
    paper_lookup_service: PaperLookupService
    pdf_markdown_service: PdfMarkdownService
    browser_use_service: BrowserUseService
    database_query_service: DatabaseQueryService
    web_search_service: WebSearchService
    local_citations: dict[str, Citation] = field(default_factory=dict)
    tool_traces: list[ToolTrace] = field(default_factory=list)
    event_emitter: Callable[[dict[str, object]], Awaitable[None]] | None = None


def paper_to_citation(paper: Paper) -> Citation:
    return Citation(
        title=paper.title,
        url=paper.url or paper.source_page_url,
        source_page_url=paper.source_page_url,
        venue=paper.venue,
        year=paper.year,
        source_type="local_paper_db",
    )


def append_tool_trace(
    ctx: RunContextWrapper[AgentContext],
    tool_name: str,
    status: str,
    summary: str,
) -> None:
    ctx.context.tool_traces.append(
        ToolTrace(
            tool_name=tool_name,
            status=status,
            summary=summary,
        )
    )
