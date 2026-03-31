from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from paper_agent.api.serializers import to_paper_read
from paper_agent.config import get_settings
from paper_agent.db import get_db_session
from paper_agent.dependencies import ingestion_service
from paper_agent.models import Conference, Paper
from paper_agent.schemas import (
    FetchMarkdownResponse,
    ImportJobRead,
    ImportMarkdownRequest,
    PaperConferenceResolution,
    PaperListResponse,
    PaperRead,
    PaperUpdateRequest,
    ConferenceRead,
)

router = APIRouter()
settings = get_settings()


def build_jina_reader_url(source_url: str) -> str:
    normalized = source_url.strip()
    if normalized.startswith("https://r.jina.ai/http://") or normalized.startswith("https://r.jina.ai/https://"):
        return normalized
    if normalized.startswith("http://r.jina.ai/http://") or normalized.startswith("http://r.jina.ai/https://"):
        return normalized.replace("http://", "https://", 1)
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid source URL.")
    return f"https://r.jina.ai/{normalized}"


@router.get("/papers/fetch-markdown", response_model=FetchMarkdownResponse)
async def fetch_markdown_from_url(url: str) -> FetchMarkdownResponse:
    fetched_url = build_jina_reader_url(url)
    headers = {"User-Agent": settings.paper_fetch_user_agent}
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=settings.http_timeout_seconds * 3,
        headers=headers,
    ) as client:
        response = await client.get(fetched_url)
        response.raise_for_status()
    return FetchMarkdownResponse(
        source_url=url.strip(),
        fetched_url=fetched_url,
        markdown=response.text,
    )


@router.post("/papers/import-markdown", response_model=ImportJobRead, status_code=202)
async def import_markdown(
    payload: ImportMarkdownRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
) -> ImportJobRead:
    job = await ingestion_service.create_import_job(
        session,
        source_name=payload.source_name,
    )
    background_tasks.add_task(
        ingestion_service.run_import_job,
        job.id,
        payload.content,
        payload.source_name,
    )
    return ImportJobRead.model_validate(job, from_attributes=True)


@router.get("/papers/import-jobs/{job_id}", response_model=ImportJobRead)
async def get_import_job(
    job_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> ImportJobRead:
    job = await ingestion_service.get_import_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found.")
    return ImportJobRead.model_validate(job, from_attributes=True)


@router.get("/papers", response_model=PaperListResponse)
async def list_papers(
    q: str | None = None,
    conference_id: str | None = None,
    venue: str | None = None,
    year: int | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 10,
    session: AsyncSession = Depends(get_db_session),
) -> PaperListResponse:
    if page < 1:
        raise HTTPException(status_code=400, detail="Page must be >= 1.")
    if page_size < 1 or page_size > 100:
        raise HTTPException(status_code=400, detail="Page size must be between 1 and 100.")

    stmt = select(Paper).options(selectinload(Paper.conference))
    if q:
        keyword = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Paper.title.ilike(keyword),
                Paper.venue.ilike(keyword),
                Paper.abstract.ilike(keyword),
                Paper.source_page_url.ilike(keyword),
            )
        )
    if conference_id:
        stmt = stmt.where(Paper.conference_id == conference_id)
    if venue:
        stmt = stmt.where(Paper.venue == venue)
    if year:
        stmt = stmt.where(Paper.year == year)
    if year_from is not None:
        stmt = stmt.where(Paper.year.is_not(None), Paper.year >= year_from)
    if year_to is not None:
        stmt = stmt.where(Paper.year.is_not(None), Paper.year <= year_to)
    if status:
        stmt = stmt.where(Paper.ingest_status == status)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_items = int((await session.scalar(count_stmt)) or 0)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    if total_items == 0:
        page = 1
    else:
        page = min(page, total_pages)

    paged_stmt = stmt.order_by(Paper.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    papers = list((await session.scalars(paged_stmt)).all())
    return PaperListResponse(
        items=[to_paper_read(paper) for paper in papers],
        page=page,
        page_size=page_size,
        total_items=total_items,
        total_pages=total_pages,
    )


@router.patch("/papers/{paper_id}", response_model=PaperRead)
async def update_paper(
    paper_id: str,
    payload: PaperUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> PaperRead:
    paper = await session.get(Paper, paper_id, options=[selectinload(Paper.conference)])
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found.")

    conference = paper.conference
    if "conference_id" in payload.model_fields_set:
        if payload.conference_id:
            conference = await session.get(Conference, payload.conference_id)
            if not conference:
                raise HTTPException(status_code=404, detail="Conference not found.")
        else:
            conference = None

    paper.title = payload.title.strip()
    paper.conference_id = conference.id if conference else None
    paper.url = payload.url.strip() if payload.url else None
    paper.source_page_url = (
        conference.source_page_url
        if conference and conference.source_page_url
        else payload.source_page_url.strip() if payload.source_page_url else None
    )
    paper.venue = conference.name if conference else payload.venue.strip() if payload.venue else None
    paper.year = conference.year if conference and conference.year else payload.year
    paper.abstract = payload.abstract.strip() if payload.abstract else None
    await session.commit()
    refreshed_paper = await session.get(Paper, paper_id, options=[selectinload(Paper.conference)])
    if not refreshed_paper:
        raise HTTPException(status_code=404, detail="Paper not found.")
    return to_paper_read(refreshed_paper)


@router.delete("/papers/{paper_id}", status_code=204)
async def delete_paper(
    paper_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    paper = await session.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found.")

    await session.delete(paper)
    await session.commit()
    return Response(status_code=204)


@router.post("/papers/{paper_id}/resolve-conference", response_model=PaperConferenceResolution)
async def resolve_paper_conference(
    paper_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> PaperConferenceResolution:
    paper = await session.get(Paper, paper_id, options=[selectinload(Paper.conference)])
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found.")

    conference, status = await ingestion_service.resolve_conference_for_paper(session, paper)
    refreshed_paper = await session.get(Paper, paper_id, options=[selectinload(Paper.conference)])
    if not refreshed_paper:
        raise HTTPException(status_code=404, detail="Paper not found.")

    if status == "already_attached":
        message = f"這篇 paper 已經綁定到 conference 實體：{conference.name if conference else refreshed_paper.venue or '未命名會議'}。"
    elif status == "reused_existing":
        message = f"已偵測到重複的 conference，重用了既有實體：{conference.name if conference else refreshed_paper.venue or '未命名會議'}。"
    elif status == "created_new":
        message = f"已建立新的 conference 實體：{conference.name if conference else refreshed_paper.venue or '未命名會議'}。"
    else:
        message = "這篇 paper 目前缺少可辨識的 conference 名稱，無法建立或綁定 conference 實體。"

    conference_read = None
    if conference:
        conference_read = ConferenceRead(
            id=conference.id,
            name=conference.name,
            normalized_name=conference.normalized_name,
            source_page_url=conference.source_page_url,
            year=conference.year,
            paper_count=int(
                (
                    await session.scalar(select(func.count()).select_from(Paper).where(Paper.conference_id == conference.id))
                )
                or 0
            ),
        )

    return PaperConferenceResolution(
        paper=to_paper_read(refreshed_paper),
        conference=conference_read,
        status=status,
        duplicate_detected=status == "reused_existing",
        message=message,
    )
