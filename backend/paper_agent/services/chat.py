import asyncio
import contextlib
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field

from agents import Agent, ModelSettings, RunContextWrapper, Runner, function_tool, trace
from agents.extensions.memory import SQLAlchemySession
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from paper_agent.config import get_settings
from paper_agent.db import engine
from paper_agent.models import IngestStatus, Paper, PaperEmbedding
from paper_agent.schemas import ChatMessage, ChatResponse, Citation, SourceSummary, ToolTrace
from paper_agent.services.ingestion import IngestionService
from paper_agent.services.browser_use_service import BrowserUseService
from paper_agent.services.paper_lookup import PaperLookupService
from paper_agent.services.pdf_markdown import PdfMarkdownService
from paper_agent.services.retrieval import RetrievalService


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
    local_citations: dict[str, Citation] = field(default_factory=dict)
    tool_traces: list[ToolTrace] = field(default_factory=list)
    event_emitter: Callable[[dict[str, object]], Awaitable[None]] | None = None


def _paper_to_citation(paper: Paper) -> Citation:
    return Citation(
        title=paper.title,
        url=paper.url or paper.source_page_url,
        source_page_url=paper.source_page_url,
        venue=paper.venue,
        year=paper.year,
        source_type="local_paper_db",
    )


class ChatService:
    def __init__(
        self,
        retrieval_service: RetrievalService,
        ingestion_service: IngestionService,
        paper_lookup_service: PaperLookupService,
        pdf_markdown_service: PdfMarkdownService,
        browser_use_service: BrowserUseService,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.ingestion_service = ingestion_service
        self.paper_lookup_service = paper_lookup_service
        self.pdf_markdown_service = pdf_markdown_service
        self.browser_use_service = browser_use_service
        self.settings = get_settings()

    async def run_chat(
        self,
        session: AsyncSession,
        message: str,
        history: list[ChatMessage],
        session_id: str | None = None,
    ) -> ChatResponse:
        resolved_session_id = session_id or str(uuid.uuid4())
        context = AgentContext(
            session=session,
            retrieval_service=self.retrieval_service,
            ingestion_service=self.ingestion_service,
            paper_lookup_service=self.paper_lookup_service,
            pdf_markdown_service=self.pdf_markdown_service,
            browser_use_service=self.browser_use_service,
        )
        agent = self._build_agent()
        input_text = self._format_conversation_input(message, history, has_persistent_session=session_id is not None)
        agent_session = SQLAlchemySession(
            resolved_session_id,
            engine=engine,
            create_tables=True,
        )

        with trace(
            "paper-agent-chat",
            group_id=resolved_session_id,
            metadata={
                "session_id": resolved_session_id,
                "history_count": str(len(history)),
            },
        ):
            result = await Runner.run(
                agent,
                input_text,
                context=context,
                session=agent_session,
            )
        final_output = self._coerce_output(result.final_output)
        citations = self._merge_citations(final_output.citations, context.local_citations)
        sources = self._build_sources(citations)

        return ChatResponse(
            session_id=resolved_session_id,
            answer=final_output.answer,
            citations=citations,
            sources=sources,
            tool_traces=context.tool_traces,
        )

    async def stream_chat(
        self,
        session: AsyncSession,
        message: str,
        history: list[ChatMessage],
        session_id: str | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        resolved_session_id = session_id or str(uuid.uuid4())
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

        async def emit(event: dict[str, object]) -> None:
            await queue.put(event)

        context = AgentContext(
            session=session,
            retrieval_service=self.retrieval_service,
            ingestion_service=self.ingestion_service,
            paper_lookup_service=self.paper_lookup_service,
            pdf_markdown_service=self.pdf_markdown_service,
            browser_use_service=self.browser_use_service,
            event_emitter=emit,
        )
        agent = self._build_agent()
        input_text = self._format_conversation_input(message, history, has_persistent_session=session_id is not None)
        agent_session = SQLAlchemySession(
            resolved_session_id,
            engine=engine,
            create_tables=True,
        )

        async def run_agent() -> None:
            try:
                await emit({"type": "session_started", "session_id": resolved_session_id})
                with trace(
                    "paper-agent-chat",
                    group_id=resolved_session_id,
                    metadata={
                        "session_id": resolved_session_id,
                        "history_count": str(len(history)),
                    },
                ):
                    result = await Runner.run(
                        agent,
                        input_text,
                        context=context,
                        session=agent_session,
                    )
                final_output = self._coerce_output(result.final_output)
                citations = self._merge_citations(final_output.citations, context.local_citations)
                sources = self._build_sources(citations)
                await emit(
                    {
                        "type": "final_answer",
                        "session_id": resolved_session_id,
                        "answer": final_output.answer,
                        "citations": [citation.model_dump() for citation in citations],
                        "sources": [source.model_dump() for source in sources],
                        "tool_traces": [trace_item.model_dump() for trace_item in context.tool_traces],
                    }
                )
            except Exception as error:
                await emit(
                    {
                        "type": "error",
                        "message": str(error),
                    }
                )
            finally:
                await emit({"type": "completed"})

        task = asyncio.create_task(run_agent())

        try:
            while True:
                event = await queue.get()
                yield event
                if event.get("type") == "completed":
                    break
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    @staticmethod
    def _append_tool_trace(
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

    @staticmethod
    async def _emit_event(
        ctx: RunContextWrapper[AgentContext],
        event: dict[str, object],
    ) -> None:
        if ctx.context.event_emitter:
            await ctx.context.event_emitter(event)

    async def _emit_tool_started(
        self,
        ctx: RunContextWrapper[AgentContext],
        tool_name: str,
        summary: str,
    ) -> None:
        await self._emit_event(
            ctx,
            {
                "type": "tool_started",
                "tool_name": tool_name,
                "summary": summary,
            },
        )

    async def _record_tool_trace(
        self,
        ctx: RunContextWrapper[AgentContext],
        tool_name: str,
        status: str,
        summary: str,
    ) -> None:
        self._append_tool_trace(ctx, tool_name, status, summary)
        await self._emit_event(
            ctx,
            {
                "type": "tool_finished" if status == "ok" else "tool_failed",
                "tool_name": tool_name,
                "status": status,
                "summary": summary,
            },
        )

    def _build_agent(self) -> Agent[AgentContext]:
        @function_tool
        async def search_papers(
            ctx: RunContextWrapper[AgentContext],
            query: str,
            venue: str | None = None,
            year: int | None = None,
            top_k: int | None = None,
        ) -> str:
            """Search the local paper database by semantic similarity. Use this first for paper-related questions."""

            await self._emit_tool_started(
                ctx,
                "search_papers",
                f"在本地資料庫搜尋「{query}」{f'，venue={venue}' if venue else ''}{f'，year={year}' if year else ''}。",
            )
            papers = await ctx.context.retrieval_service.search_papers(
                ctx.context.session,
                query=query,
                venue=venue,
                year=year,
                top_k=top_k,
            )
            for paper in papers:
                ctx.context.local_citations[paper.id] = Citation(
                    title=paper.title,
                    url=paper.url or paper.source_page_url,
                    source_page_url=paper.source_page_url,
                    venue=paper.venue,
                    year=paper.year,
                    source_type="local_paper_db",
                )
            await self._record_tool_trace(
                ctx,
                "search_papers",
                "ok",
                f"在本地資料庫搜尋「{query}」{f'，venue={venue}' if venue else ''}{f'，year={year}' if year else ''}，找到 {len(papers)} 篇結果。",
            )
            return json.dumps([paper.model_dump() for paper in papers], ensure_ascii=False)

        @function_tool
        async def get_paper_details(
            ctx: RunContextWrapper[AgentContext],
            paper_ids: list[str],
        ) -> str:
            """Fetch detailed records for papers that were previously retrieved."""

            await self._emit_tool_started(
                ctx,
                "get_paper_details",
                f"讀取 {len(paper_ids)} 篇論文的詳細資料。",
            )
            papers = await ctx.context.retrieval_service.get_papers_by_ids(ctx.context.session, paper_ids)
            for paper in papers:
                ctx.context.local_citations[paper.id] = _paper_to_citation(paper)
            payload = [
                {
                    "id": paper.id,
                    "title": paper.title,
                    "url": paper.url,
                    "source_page_url": paper.source_page_url,
                    "venue": paper.venue,
                    "year": paper.year,
                    "abstract": paper.abstract,
                    "source_type": "local_paper_db",
                }
                for paper in papers
            ]
            await self._record_tool_trace(
                ctx,
                "get_paper_details",
                "ok",
                f"讀取 {len(papers)} 篇已檢索論文的詳細資料。",
            )
            return json.dumps(payload, ensure_ascii=False)

        @function_tool
        async def find_paper_abstract(
            ctx: RunContextWrapper[AgentContext],
            title: str,
            paper_url: str | None = None,
            source_page_url: str | None = None,
            venue: str | None = None,
            year: int | None = None,
        ) -> str:
            """Find the abstract for a specific paper title. Check the local database first, then do an external metadata lookup if needed."""

            await self._emit_tool_started(
                ctx,
                "find_paper_abstract",
                f"為「{title}」查找摘要。",
            )
            local_matches = await ctx.context.retrieval_service.find_papers_by_title(
                ctx.context.session,
                title=title,
                limit=5,
            )
            if local_matches:
                best_local = local_matches[0]
                ctx.context.local_citations[best_local.id] = _paper_to_citation(best_local)
                if best_local.abstract:
                    await self._record_tool_trace(
                        ctx,
                        "find_paper_abstract",
                        "ok",
                        f"在本地資料庫找到「{best_local.title}」的摘要。",
                    )
                    return json.dumps(
                        {
                            "status": "found_local",
                            "paper": {
                                "id": best_local.id,
                                "title": best_local.title,
                                "abstract": best_local.abstract,
                                "url": best_local.url,
                                "source_page_url": best_local.source_page_url,
                                "venue": best_local.venue,
                                "year": best_local.year,
                                "source_type": "local_paper_db",
                            },
                        },
                        ensure_ascii=False,
                    )

                lookup = await ctx.context.paper_lookup_service.lookup_paper(
                    title=best_local.title,
                    paper_url=best_local.url or paper_url,
                    source_page_url=best_local.source_page_url or source_page_url,
                    venue=best_local.venue or venue,
                    year=best_local.year or year,
                )
                if lookup:
                    if lookup.abstract:
                        best_local.abstract = lookup.abstract
                    if not best_local.url and lookup.url:
                        best_local.url = lookup.url
                    if not best_local.venue and lookup.venue:
                        best_local.venue = lookup.venue
                    if not best_local.year and lookup.year:
                        best_local.year = lookup.year
                    if best_local.abstract:
                        best_local.ingest_status = IngestStatus.READY

                    parts = [best_local.title]
                    if best_local.abstract:
                        parts.append(best_local.abstract)
                    if best_local.venue:
                        parts.append(best_local.venue)
                    if best_local.year:
                        parts.append(str(best_local.year))
                    if best_local.source_page_url:
                        parts.append(best_local.source_page_url)
                    embedding_input = "\n\n".join(parts)
                    embedding_vector = await ctx.context.retrieval_service.embedding_service.embed_text(embedding_input)
                    existing_embedding = await ctx.context.session.scalar(
                        select(PaperEmbedding).where(PaperEmbedding.paper_id == best_local.id)
                    )
                    if existing_embedding:
                        existing_embedding.embedding = embedding_vector
                    else:
                        ctx.context.session.add(PaperEmbedding(paper_id=best_local.id, embedding=embedding_vector))
                    await ctx.context.session.commit()
                    await ctx.context.session.refresh(best_local)
                    ctx.context.local_citations[best_local.id] = _paper_to_citation(best_local)
                    status = "enriched_local" if best_local.abstract else "metadata_only_local"
                    await self._record_tool_trace(
                        ctx,
                        "find_paper_abstract",
                        "ok" if best_local.abstract else "not_found",
                        (
                            f"本地找到「{best_local.title}」，並用外部來源補齊摘要。"
                            if best_local.abstract
                            else f"本地找到「{best_local.title}」，但外部來源只補到 metadata，沒有摘要。"
                        ),
                    )
                    return json.dumps(
                        {
                            "status": status,
                            "paper": {
                                "id": best_local.id,
                                "title": best_local.title,
                                "abstract": best_local.abstract,
                                "url": best_local.url,
                                "source_page_url": best_local.source_page_url,
                                "venue": best_local.venue,
                                "year": best_local.year,
                                "source_type": "local_paper_db",
                                "pdf_url": lookup.pdf_url,
                                "slide_url": lookup.slide_url,
                                "video_url": lookup.video_url,
                                "provider": lookup.provider,
                            },
                        },
                        ensure_ascii=False,
                    )

            lookup = await ctx.context.paper_lookup_service.lookup_paper(
                title=title,
                paper_url=paper_url,
                source_page_url=source_page_url,
                venue=venue,
                year=year,
            )
            if lookup:
                if not lookup.abstract:
                    await self._record_tool_trace(
                        ctx,
                        "find_paper_abstract",
                        "not_found",
                        f"外部來源找到「{lookup.title or title}」的 metadata，但沒有可用摘要。",
                    )
                    return json.dumps(
                        {
                            "status": "metadata_only",
                            "paper": {
                                "title": lookup.title,
                                "url": lookup.url,
                                "source_page_url": lookup.source_page_url,
                                "pdf_url": lookup.pdf_url,
                                "slide_url": lookup.slide_url,
                                "video_url": lookup.video_url,
                                "venue": lookup.venue,
                                "year": lookup.year,
                                "provider": lookup.provider,
                                "confidence": lookup.confidence,
                                "source_type": "web_search",
                            },
                            "message": "Found paper metadata on the web, but no abstract was available.",
                        },
                        ensure_ascii=False,
                    )
                await self._record_tool_trace(
                    ctx,
                    "find_paper_abstract",
                    "ok",
                    f"透過 {lookup.provider} 找到「{lookup.title or title}」的摘要。",
                )
                return json.dumps(
                    {
                        "status": "found_external",
                        "paper": {
                            "title": lookup.title,
                            "abstract": lookup.abstract,
                            "url": lookup.url,
                            "source_page_url": lookup.source_page_url,
                            "pdf_url": lookup.pdf_url,
                            "slide_url": lookup.slide_url,
                            "video_url": lookup.video_url,
                            "venue": lookup.venue,
                            "year": lookup.year,
                            "provider": lookup.provider,
                            "confidence": lookup.confidence,
                            "source_type": "web_search",
                        },
                    },
                    ensure_ascii=False,
                )

            await self._record_tool_trace(
                ctx,
                "find_paper_abstract",
                "not_found",
                f"沒有為「{title}」找到摘要。",
            )
            return json.dumps(
                {
                    "status": "not_found",
                    "message": "Abstract not found in the local database or via external metadata lookup.",
                },
                ensure_ascii=False,
            )

        @function_tool
        async def lookup_paper_on_web(
            ctx: RunContextWrapper[AgentContext],
            title: str,
            paper_url: str | None = None,
            source_page_url: str | None = None,
            venue: str | None = None,
            year: int | None = None,
        ) -> str:
            """Look up paper metadata on the web. Use this when you need a paper page, PDF, slides, video, DOI, or abstract for a specific paper."""

            await self._emit_tool_started(
                ctx,
                "lookup_paper_on_web",
                f"在外部來源查找「{title}」的 paper metadata。",
            )
            lookup = await ctx.context.paper_lookup_service.lookup_paper(
                title=title,
                paper_url=paper_url,
                source_page_url=source_page_url,
                venue=venue,
                year=year,
            )
            if not lookup:
                await self._record_tool_trace(
                    ctx,
                    "lookup_paper_on_web",
                    "not_found",
                    f"沒有為「{title}」找到可信的外部 paper metadata。",
                )
                return json.dumps(
                    {
                        "status": "not_found",
                        "message": "No trusted external paper metadata was found for the requested title.",
                    },
                    ensure_ascii=False,
                )

            citation_url = lookup.url or lookup.source_page_url
            if citation_url:
                citation_key = f"web:{citation_url}"
                ctx.context.local_citations[citation_key] = Citation(
                    title=lookup.title or title,
                    url=citation_url,
                    source_page_url=lookup.source_page_url,
                    venue=lookup.venue,
                    year=lookup.year,
                    source_type="web_search",
                )

            await self._record_tool_trace(
                ctx,
                "lookup_paper_on_web",
                "ok",
                f"透過 {lookup.provider} 找到「{lookup.title or title}」的外部 metadata。"
                + (f" 已解析 PDF。" if lookup.pdf_url else ""),
            )
            return json.dumps(
                {
                    "status": "found",
                    "paper": lookup.to_dict(),
                },
                ensure_ascii=False,
            )

        @function_tool
        async def convert_pdf_url_to_markdown(
            ctx: RunContextWrapper[AgentContext],
            pdf_url: str,
            start_char: int = 0,
            max_chars: int | None = None,
        ) -> str:
            """Convert a PDF URL to markdown and return a chunk. Use this when you need to read PDF content directly."""

            await self._emit_tool_started(
                ctx,
                "convert_pdf_url_to_markdown",
                f"將 PDF 轉成 Markdown：{pdf_url}",
            )
            chunk = await ctx.context.pdf_markdown_service.convert_pdf_url_to_markdown(
                pdf_url,
                start_char=start_char,
                max_chars=max_chars or self.settings.pdf_markdown_chunk_chars,
            )
            await self._record_tool_trace(
                ctx,
                "convert_pdf_url_to_markdown",
                "ok",
                f"將 PDF 轉成 Markdown，讀取字元區間 {chunk.start_char}-{chunk.end_char} / {chunk.total_chars}。",
            )
            return json.dumps(
                {
                    "status": "ok",
                    "chunk": chunk.to_dict(),
                },
                ensure_ascii=False,
            )

        @function_tool
        async def convert_paper_pdf_to_markdown(
            ctx: RunContextWrapper[AgentContext],
            title: str,
            paper_url: str | None = None,
            source_page_url: str | None = None,
            venue: str | None = None,
            year: int | None = None,
            start_char: int = 0,
            max_chars: int | None = None,
        ) -> str:
            """Resolve a paper PDF from a paper URL or source page and convert it to markdown. Use this when the user asks to read the PDF content of a specific paper."""

            await self._emit_tool_started(
                ctx,
                "convert_paper_pdf_to_markdown",
                f"為「{title}」解析 PDF 並轉成 Markdown。",
            )
            chunk = await ctx.context.pdf_markdown_service.convert_paper_url_to_markdown(
                title=title,
                paper_url=paper_url,
                source_page_url=source_page_url,
                venue=venue,
                year=year,
                start_char=start_char,
                max_chars=max_chars or self.settings.pdf_markdown_chunk_chars,
            )
            if not chunk:
                await self._record_tool_trace(
                    ctx,
                    "convert_paper_pdf_to_markdown",
                    "not_found",
                    f"無法為「{title}」解析出 PDF URL。",
                )
                return json.dumps(
                    {
                        "status": "not_found",
                        "message": "Could not resolve a PDF URL for the requested paper.",
                    },
                    ensure_ascii=False,
                )

            citation_key = f"web:{chunk.source_url}"
            ctx.context.local_citations[citation_key] = Citation(
                title=title,
                url=chunk.resolved_pdf_url,
                source_page_url=paper_url or source_page_url,
                venue=venue,
                year=year,
                source_type="web_search",
            )
            await self._record_tool_trace(
                ctx,
                "convert_paper_pdf_to_markdown",
                "ok",
                f"為「{title}」解析 PDF 並轉成 Markdown，讀取字元區間 {chunk.start_char}-{chunk.end_char} / {chunk.total_chars}。",
            )
            return json.dumps(
                {
                    "status": "ok",
                    "chunk": chunk.to_dict(),
                },
                ensure_ascii=False,
            )

        @function_tool
        async def browser_browse_task(
            ctx: RunContextWrapper[AgentContext],
            task: str,
            start_url: str | None = None,
            max_steps: int | None = None,
        ) -> str:
            """Use a real browser to complete a browsing task. Use this only when page-specific extractors and paper lookup are insufficient, or when the website requires real browser interaction."""

            await self._emit_tool_started(
                ctx,
                "browser_browse_task",
                f"使用瀏覽器執行任務：{task}",
            )
            result = await ctx.context.browser_use_service.browse_task(
                task=task,
                start_url=start_url,
                max_steps=max_steps,
            )
            normalized_status = result.status.lower()
            status = "ok"
            if normalized_status in {"error", "failed"}:
                status = "error"
            elif normalized_status in {"not_found", "unavailable"}:
                status = "not_found"
            await self._record_tool_trace(
                ctx,
                "browser_browse_task",
                status,
                (
                    f"用瀏覽器工具執行任務，共 {result.steps} 步，造訪 {len(result.urls)} 個 URL。"
                    if status == "ok"
                    else f"瀏覽器工具執行失敗：{'; '.join(result.errors) if result.errors else '未知錯誤'}"
                ),
            )
            return json.dumps(result.to_dict(), ensure_ascii=False)

        @function_tool
        async def import_markdown_papers(
            ctx: RunContextWrapper[AgentContext],
            markdown_content: str,
            source_name: str | None = None,
        ) -> str:
            """Import a markdown list of papers into the local paper database."""

            await self._emit_tool_started(
                ctx,
                "import_markdown_papers",
                "建立新的 markdown 匯入工作。",
            )
            result = await ctx.context.ingestion_service.import_markdown(
                ctx.context.session,
                content=markdown_content,
                source_name=source_name,
            )
            await self._record_tool_trace(
                ctx,
                "import_markdown_papers",
                "ok",
                f"建立匯入工作，解析 {result.summary.parsed_count} 篇，已匯入 {result.summary.imported_count} 篇。",
            )
            return result.summary.model_dump_json()

        @function_tool
        async def web_search(ctx: RunContextWrapper[AgentContext], query: str) -> str:
            """Placeholder web search tool. It is currently unavailable and should not be treated as a real web result."""

            await self._record_tool_trace(
                ctx,  # type: ignore[name-defined]
                "web_search",
                "unavailable",
                f"外部 web search 尚未配置，無法直接搜尋「{query}」。",
            )
            return json.dumps(
                {
                    "status": "unavailable",
                    "query": query,
                    "message": (
                        "Web search is not configured yet. "
                        "Use the local paper database only and clearly tell the user that external web search is unavailable."
                    ),
                },
                ensure_ascii=False,
            )

        instructions = """
You are a research paper assistant.

Rules:
1. For any request that depends on papers, first use `search_papers`.
1a. If the user asks for the abstract of a specific paper, use `find_paper_abstract`.
1b. If the user needs a specific paper's PDF, slide, video, DOI, or paper page, use `lookup_paper_on_web`.
1c. If the user needs to read the PDF content itself, use `convert_paper_pdf_to_markdown` or `convert_pdf_url_to_markdown`. Read it in chunks if needed.
1d. If the site is dynamic, blocked, or the paper-specific lookup tools are insufficient, use `browser_browse_task` as a fallback browser automation tool.
2. The `web_search` tool is currently a dummy placeholder. If you call it, explain that external web search is not configured yet.
3. Never claim you read a paper unless it came from `get_paper_details`, `convert_paper_pdf_to_markdown`, `convert_pdf_url_to_markdown`, or `browser_browse_task`.
4. Citations must only include URLs that came from trusted tools.
5. Distinguish local paper citations from web search citations with the `source_type` field.
6. If the database is missing enough evidence, say so directly.
7. Reply in Traditional Chinese (繁體中文).
"""

        return Agent(
            name="Paper Agent",
            instructions=instructions,
            model=self.settings.openai_model,
            model_settings=ModelSettings(temperature=0.2),
            tools=[
                search_papers,
                get_paper_details,
                find_paper_abstract,
                lookup_paper_on_web,
                convert_pdf_url_to_markdown,
                convert_paper_pdf_to_markdown,
                browser_browse_task,
                import_markdown_papers,
                web_search,
            ],
            output_type=AgentOutput,
        )

    def _format_conversation_input(
        self,
        message: str,
        history: list[ChatMessage],
        has_persistent_session: bool,
    ) -> str:
        if has_persistent_session:
            return message

        relevant_history = history[-self.settings.max_history_messages :]
        lines = ["You are helping with academic paper discovery and analysis."]
        if relevant_history:
            lines.append("Conversation history:")
            for item in relevant_history:
                role = "User" if item.role == "user" else "Assistant"
                lines.append(f"{role}: {item.content}")
        lines.append(f"Current user message: {message}")
        return "\n".join(lines)

    def _coerce_output(self, final_output: object) -> AgentOutput:
        if isinstance(final_output, AgentOutput):
            return final_output
        if isinstance(final_output, str):
            return AgentOutput.model_validate_json(final_output)
        return AgentOutput.model_validate(final_output)

    def _merge_citations(
        self,
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

    def _build_sources(self, citations: list[Citation]) -> list[SourceSummary]:
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
