from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from paper_agent.db import get_db_session
from paper_agent.dependencies import chat_service
from paper_agent.schemas import ChatRequest, ChatResponse

router = APIRouter()


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
