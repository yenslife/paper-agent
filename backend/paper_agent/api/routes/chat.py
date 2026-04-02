import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from paper_agent.db import get_db_session
from paper_agent.dependencies import chat_service
from paper_agent.schemas import ChatRequest, ChatResponse

router = APIRouter()


def _encode_sse(event: dict[str, object]) -> str:
    event_type = str(event.get("type", "message"))
    return f"event: {event_type}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ChatResponse:
    return await chat_service.run_chat(
        session=session,
        message=payload.message,
        history=payload.history,
        session_id=payload.session_id,
    )


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    async def event_generator():
        async for event in chat_service.stream_chat(
            session=session,
            message=payload.message,
            history=payload.history,
            session_id=payload.session_id,
        ):
            yield _encode_sse(event)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
