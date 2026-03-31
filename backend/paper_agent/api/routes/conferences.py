from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from paper_agent.db import get_db_session
from paper_agent.dependencies import ingestion_service
from paper_agent.models import Conference, Paper
from paper_agent.schemas import BatchConferenceBindingResult, ConferenceListResponse, ConferenceRead

router = APIRouter()


@router.get("/conferences", response_model=ConferenceListResponse)
async def list_conferences(
    session: AsyncSession = Depends(get_db_session),
) -> ConferenceListResponse:
    stmt = (
        select(Conference, func.count(Paper.id))
        .outerjoin(Paper, Paper.conference_id == Conference.id)
        .group_by(Conference.id)
        .order_by(Conference.year.desc().nullslast(), Conference.name.asc())
    )
    rows = (await session.execute(stmt)).all()
    return ConferenceListResponse(
        items=[
            ConferenceRead(
                id=conference.id,
                name=conference.name,
                normalized_name=conference.normalized_name,
                source_page_url=conference.source_page_url,
                year=conference.year,
                paper_count=int(paper_count),
            )
            for conference, paper_count in rows
        ]
    )


@router.post("/conferences/bind-unlinked-papers", response_model=BatchConferenceBindingResult)
async def bind_unlinked_papers_to_conferences(
    session: AsyncSession = Depends(get_db_session),
) -> BatchConferenceBindingResult:
    result = await ingestion_service.bind_all_unlinked_papers_to_conferences(session)
    return BatchConferenceBindingResult(
        total_candidates=result["total_candidates"],
        bound_count=result["bound_count"],
        reused_existing_count=result["reused_existing_count"],
        created_new_count=result["created_new_count"],
        unresolved_count=result["unresolved_count"],
        message=(
            f"已處理 {result['total_candidates']} 篇未綁定 paper；"
            f"成功綁定 {result['bound_count']} 篇，"
            f"其中重用既有 conference {result['reused_existing_count']} 次、"
            f"建立新 conference {result['created_new_count']} 次，"
            f"仍有 {result['unresolved_count']} 篇無法判定。"
        ),
    )
