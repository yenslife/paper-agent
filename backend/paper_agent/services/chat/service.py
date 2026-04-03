import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator

from agents import Agent, ModelSettings, Runner, trace
from agents.extensions.memory import SQLAlchemySession
from sqlalchemy.ext.asyncio import AsyncSession

from paper_agent.config import get_settings
from paper_agent.db import engine
from paper_agent.schemas import ChatMessage, ChatResponse
from paper_agent.services.browser_use_service import BrowserUseService
from paper_agent.services.database_query import DatabaseQueryService
from paper_agent.services.ingestion import IngestionService
from paper_agent.services.paper_lookup import PaperLookupService
from paper_agent.services.pdf_markdown import PdfMarkdownService
from paper_agent.services.retrieval import RetrievalService
from paper_agent.services.web_search import WebSearchService

from .output import build_sources, coerce_output, merge_citations
from .prompts import CHAT_INSTRUCTIONS
from .tools import build_chat_tools
from .types import AgentCitation, AgentContext, AgentOutput


class ChatService:
    def __init__(
        self,
        retrieval_service: RetrievalService,
        ingestion_service: IngestionService,
        paper_lookup_service: PaperLookupService,
        pdf_markdown_service: PdfMarkdownService,
        browser_use_service: BrowserUseService,
        database_query_service: DatabaseQueryService,
        web_search_service: WebSearchService,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.ingestion_service = ingestion_service
        self.paper_lookup_service = paper_lookup_service
        self.pdf_markdown_service = pdf_markdown_service
        self.browser_use_service = browser_use_service
        self.database_query_service = database_query_service
        self.web_search_service = web_search_service
        self.settings = get_settings()

    async def run_chat(
        self,
        session: AsyncSession,
        message: str,
        history: list[ChatMessage],
        session_id: str | None = None,
    ) -> ChatResponse:
        resolved_session_id = session_id or str(uuid.uuid4())
        context = self._build_context(session=session)
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
        final_output = coerce_output(result.final_output)
        citations = merge_citations(final_output.citations, context.local_citations)
        sources = build_sources(citations)

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

        context = self._build_context(session=session, event_emitter=emit)
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
                final_output = coerce_output(result.final_output)
                citations = merge_citations(final_output.citations, context.local_citations)
                sources = build_sources(citations)
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

    def _build_context(
        self,
        session: AsyncSession,
        event_emitter=None,
    ) -> AgentContext:
        return AgentContext(
            session=session,
            retrieval_service=self.retrieval_service,
            ingestion_service=self.ingestion_service,
            paper_lookup_service=self.paper_lookup_service,
            pdf_markdown_service=self.pdf_markdown_service,
            browser_use_service=self.browser_use_service,
            database_query_service=self.database_query_service,
            web_search_service=self.web_search_service,
            event_emitter=event_emitter,
        )

    def _build_agent(self) -> Agent[AgentContext]:
        return Agent(
            name="Paper Agent",
            instructions=CHAT_INSTRUCTIONS,
            model=self.settings.openai_model,
            model_settings=ModelSettings(temperature=0.2),
            tools=build_chat_tools(self),
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
        return coerce_output(final_output)

    def _merge_citations(self, citations, local_citations):
        return merge_citations(citations, local_citations)

    def _build_sources(self, citations):
        return build_sources(citations)
