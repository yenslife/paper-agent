from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

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
    active_tool_spans: dict[str, "ToolSpanState"] = field(default_factory=dict)


@dataclass(slots=True)
class ToolSpanState:
    trace_id: str
    started_at: str
    started_perf: float


def start_tool_span(ctx: RunContextWrapper[AgentContext], tool_name: str) -> ToolSpanState:
    trace_id = f"{tool_name}-{uuid4()}"
    span = ToolSpanState(
        trace_id=trace_id,
        started_at=datetime.now(UTC).isoformat(),
        started_perf=perf_counter(),
    )
    ctx.context.active_tool_spans[tool_name] = span
    return span


def finish_tool_span(
    ctx: RunContextWrapper[AgentContext],
    tool_name: str,
) -> tuple[str, str, str, int]:
    finished_at = datetime.now(UTC).isoformat()
    span = ctx.context.active_tool_spans.pop(tool_name, None)
    if not span:
        span = ToolSpanState(
            trace_id=f"{tool_name}-{uuid4()}",
            started_at=finished_at,
            started_perf=perf_counter(),
        )
    duration_ms = max(0, int((perf_counter() - span.started_perf) * 1000))
    return span.trace_id, span.started_at, finished_at, duration_ms


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
    trace_id: str,
    tool_name: str,
    status: str,
    summary: str,
    started_at: str,
    ended_at: str | None = None,
    duration_ms: int | None = None,
    details: dict[str, object] | None = None,
) -> None:
    ctx.context.tool_traces.append(
        ToolTrace(
            trace_id=trace_id,
            tool_name=tool_name,
            status=status,
            summary=summary,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=duration_ms,
            details=details,
        )
    )
