import json
from typing import TYPE_CHECKING

from agents import RunContextWrapper, function_tool
from sqlalchemy import select

from paper_agent.models import IngestStatus, PaperEmbedding
from paper_agent.schemas import Citation
from paper_agent.services.database_query import (
    DatabaseQueryValidationError,
    DatabaseSchemaInspectionError,
)

if TYPE_CHECKING:
    from .service import ChatService

from .events import emit_tool_started, record_tool_trace
from .types import AgentContext, paper_to_citation


def build_chat_tools(service: "ChatService") -> list[object]:
    @function_tool
    async def inspect_database_schema(
        ctx: RunContextWrapper[AgentContext],
    ) -> str:
        """Inspect the read-only database schema. Use this before writing SQL queries about conferences, papers, or import jobs."""

        await emit_tool_started(
            ctx,
            "inspect_database_schema",
            "查看資料庫 schema 與可查詢的表。",
        )
        try:
            schema = await ctx.context.database_query_service.describe_schema(ctx.context.session)
        except DatabaseSchemaInspectionError as error:
            await record_tool_trace(
                ctx,
                "inspect_database_schema",
                "error",
                f"資料庫 schema 檢查失敗：{error}",
            )
            return json.dumps(
                {
                    "status": "error",
                    "message": str(error),
                },
                ensure_ascii=False,
            )
        await record_tool_trace(
            ctx,
            "inspect_database_schema",
            "ok",
            f"查看資料庫 schema，共 {len(schema.get('tables', []))} 個資料表。",
        )
        return json.dumps(
            {
                "status": "ok",
                "schema": schema,
            },
            ensure_ascii=False,
        )

    @function_tool
    async def query_database_sql(
        ctx: RunContextWrapper[AgentContext],
        sql: str,
    ) -> str:
        """Execute a read-only SQL query against the local database. Only SELECT queries are allowed. Use this only for structured metadata questions such as listing conferences, counts, or import jobs. Do not use SQL as a replacement for semantic paper retrieval."""

        await emit_tool_started(
            ctx,
            "query_database_sql",
            f"執行唯讀 SQL：{sql}",
        )
        try:
            result = await ctx.context.database_query_service.execute_readonly_sql(ctx.context.session, sql)
        except DatabaseQueryValidationError as error:
            await record_tool_trace(
                ctx,
                "query_database_sql",
                "error",
                f"SQL 驗證失敗：{error}",
            )
            return json.dumps(
                {
                    "status": "invalid_sql",
                    "message": str(error),
                },
                ensure_ascii=False,
            )

        await record_tool_trace(
            ctx,
            "query_database_sql",
            "ok",
            f"執行唯讀 SQL，取得 {result.row_count} 筆資料。",
        )
        return json.dumps(
            {
                "status": "ok",
                "result": result.to_dict(),
            },
            ensure_ascii=False,
        )

    @function_tool
    async def search_papers(
        ctx: RunContextWrapper[AgentContext],
        query: str,
        venue: str | None = None,
        year: int | None = None,
        top_k: int | None = None,
    ) -> str:
        """Search the local paper database by semantic similarity. Use this first for paper-related questions, topic discovery, or when the user may describe a concept without exact title keywords."""

        await emit_tool_started(
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
        await record_tool_trace(
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

        await emit_tool_started(
            ctx,
            "get_paper_details",
            f"讀取 {len(paper_ids)} 篇論文的詳細資料。",
        )
        papers = await ctx.context.retrieval_service.get_papers_by_ids(ctx.context.session, paper_ids)
        for paper in papers:
            ctx.context.local_citations[paper.id] = paper_to_citation(paper)
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
        await record_tool_trace(
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

        await emit_tool_started(
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
            ctx.context.local_citations[best_local.id] = paper_to_citation(best_local)
            if best_local.abstract:
                await record_tool_trace(
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
                ctx.context.local_citations[best_local.id] = paper_to_citation(best_local)
                status = "enriched_local" if best_local.abstract else "metadata_only_local"
                await record_tool_trace(
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
                await record_tool_trace(
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
            await record_tool_trace(
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

        await record_tool_trace(
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

        await emit_tool_started(
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
            await record_tool_trace(
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

        await record_tool_trace(
            ctx,
            "lookup_paper_on_web",
            "ok",
            f"透過 {lookup.provider} 找到「{lookup.title or title}」的外部 metadata。"
            + (" 已解析 PDF。" if lookup.pdf_url else ""),
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

        await emit_tool_started(
            ctx,
            "convert_pdf_url_to_markdown",
            f"將 PDF 轉成 Markdown：{pdf_url}",
        )
        chunk = await ctx.context.pdf_markdown_service.convert_pdf_url_to_markdown(
            pdf_url,
            start_char=start_char,
            max_chars=max_chars or service.settings.pdf_markdown_chunk_chars,
        )
        await record_tool_trace(
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

        await emit_tool_started(
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
            max_chars=max_chars or service.settings.pdf_markdown_chunk_chars,
        )
        if not chunk:
            await record_tool_trace(
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
        await record_tool_trace(
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

        await emit_tool_started(
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
        await record_tool_trace(
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

        await emit_tool_started(
            ctx,
            "import_markdown_papers",
            "建立新的 markdown 匯入工作。",
        )
        result = await ctx.context.ingestion_service.import_markdown(
            ctx.context.session,
            content=markdown_content,
            source_name=source_name,
        )
        await record_tool_trace(
            ctx,
            "import_markdown_papers",
            "ok",
            f"建立匯入工作，解析 {result.summary.parsed_count} 篇，已匯入 {result.summary.imported_count} 篇。",
        )
        return result.summary.model_dump_json()

    @function_tool
    async def web_search(
        ctx: RunContextWrapper[AgentContext],
        query: str,
        max_results: int = 10,
    ) -> str:
        """Search the public web without API keys. Use this for general web context, recent background, or when paper-specific lookup is insufficient. Set max_results to control the number of results (default 10)."""

        await emit_tool_started(
            ctx,
            "web_search",
            f"搜尋外部網頁：「{query}」，最多 {max_results} 筆結果。",
        )
        results = await ctx.context.web_search_service.search(query, max_results)
        if not results:
            await record_tool_trace(
                ctx,
                "web_search",
                "not_found",
                f"外部 web search 沒有為「{query}」找到結果。",
            )
            return json.dumps(
                {
                    "status": "not_found",
                    "query": query,
                    "results": [],
                },
                ensure_ascii=False,
            )

        for result in results:
            citation_key = f"web:{result.url}"
            ctx.context.local_citations[citation_key] = Citation(
                title=result.title,
                url=result.url,
                source_page_url=None,
                venue=None,
                year=None,
                source_type="web_search",
            )

        await record_tool_trace(
            ctx,
            "web_search",
            "ok",
            f"外部 web search 為「{query}」找到 {len(results)} 筆結果。",
        )
        return json.dumps(
            {
                "status": "ok",
                "query": query,
                "results": [result.to_dict() for result in results],
            },
            ensure_ascii=False,
        )

    return [
        inspect_database_schema,
        query_database_sql,
        search_papers,
        get_paper_details,
        find_paper_abstract,
        lookup_paper_on_web,
        convert_pdf_url_to_markdown,
        convert_paper_pdf_to_markdown,
        browser_browse_task,
        import_markdown_papers,
        web_search,
    ]
