from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from paper_agent.db import SessionLocal
from paper_agent.models import Conference, ImportJob, ImportJobStatus, IngestStatus, Paper, PaperEmbedding
from paper_agent.schemas import ImportJobRead, ImportSummary
from paper_agent.services.abstract_fetcher import AbstractFetcher
from paper_agent.services.embeddings import EmbeddingService
from paper_agent.services.markdown_parser import (
    KnownConferenceLabel,
    MarkdownParser,
    ParsedPaper,
    normalize_title_for_dedupe,
)


@dataclass(slots=True)
class ImportResult:
    summary: ImportSummary
    papers: list[Paper]


class IngestionService:
    def __init__(
        self,
        abstract_fetcher: AbstractFetcher,
        embedding_service: EmbeddingService,
        markdown_parser: MarkdownParser | None = None,
    ) -> None:
        self.abstract_fetcher = abstract_fetcher
        self.embedding_service = embedding_service
        self.markdown_parser = markdown_parser or MarkdownParser()

    async def list_conferences(self, session: AsyncSession) -> list[Conference]:
        stmt = select(Conference).order_by(Conference.year.desc().nullslast(), Conference.name.asc())
        return list((await session.scalars(stmt)).all())

    async def resolve_conference_for_paper(
        self,
        session: AsyncSession,
        paper: Paper,
    ) -> tuple[Conference | None, str]:
        if paper.conference_id and paper.conference:
            return paper.conference, "already_attached"
        if not paper.venue:
            return None, "unresolved"

        existing_before = await self._find_matching_conference(
            session,
            venue=paper.venue,
            year=paper.year,
            source_page_url=paper.source_page_url,
        )
        conference = existing_before
        if not conference:
            conference = Conference(
                name=paper.venue.strip(),
                normalized_name=self._normalize_conference_name(paper.venue),
                identity_key=self._build_conference_identity_key(
                    name=paper.venue,
                    year=paper.year,
                    source_page_url=paper.source_page_url,
                ),
                source_page_url=paper.source_page_url,
                year=paper.year,
            )
            session.add(conference)
            await session.flush()

        paper.conference_id = conference.id
        paper.venue = conference.name
        if conference.year:
            paper.year = conference.year
        if conference.source_page_url:
            paper.source_page_url = conference.source_page_url
        await session.commit()
        await session.refresh(paper)
        await session.refresh(conference)
        return conference, "reused_existing" if existing_before else "created_new"

    async def bind_all_unlinked_papers_to_conferences(
        self,
        session: AsyncSession,
    ) -> dict[str, int]:
        papers = list(
            (
                await session.scalars(
                    select(Paper)
                    .where(Paper.conference_id.is_(None))
                    .order_by(Paper.year.desc().nullslast(), Paper.created_at.asc())
                )
            ).all()
        )

        result = {
            "total_candidates": len(papers),
            "bound_count": 0,
            "reused_existing_count": 0,
            "created_new_count": 0,
            "unresolved_count": 0,
        }

        for paper in papers:
            conference, status = await self.resolve_conference_for_paper(session, paper)
            if status == "unresolved" or conference is None:
                result["unresolved_count"] += 1
                continue
            result["bound_count"] += 1
            if status == "reused_existing":
                result["reused_existing_count"] += 1
            elif status == "created_new":
                result["created_new_count"] += 1

        return result

    async def import_markdown(
        self,
        session: AsyncSession,
        content: str,
        source_name: str | None = None,
    ) -> ImportResult:
        result = await self._process_import(
            session=session,
            content=content,
            source_name=source_name,
        )
        await session.commit()
        return result

    async def create_import_job(self, session: AsyncSession, source_name: str | None = None) -> ImportJob:
        job = ImportJob(
            source_name=source_name,
            status=ImportJobStatus.PENDING,
            stage="queued",
            stage_message="等待開始匯入工作。",
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job

    async def get_import_job(self, session: AsyncSession, job_id: str) -> ImportJob | None:
        return await session.get(ImportJob, job_id)

    async def run_import_job(self, job_id: str, content: str, source_name: str | None = None) -> None:
        async with SessionLocal() as session:
            job = await session.get(ImportJob, job_id)
            if not job:
                return

            job.status = ImportJobStatus.RUNNING
            job.stage = "preparing"
            job.stage_message = "正在準備匯入環境。"
            job.error_message = None
            await session.commit()

            async def persist_progress() -> None:
                await session.commit()

            try:
                await self._process_import(
                    session=session,
                    content=content,
                    source_name=source_name,
                    job=job,
                    persist_progress=persist_progress,
                )
                job.status = ImportJobStatus.COMPLETED
                job.stage = "completed"
                job.stage_message = "匯入工作已完成。"
                await session.commit()
            except Exception as exc:
                await session.rollback()
                job = await session.get(ImportJob, job_id)
                if not job:
                    return
                job.status = ImportJobStatus.FAILED
                job.stage = "failed"
                job.stage_message = "匯入工作失敗。"
                job.error_message = str(exc)
                await session.commit()

    async def _process_import(
        self,
        session: AsyncSession,
        content: str,
        source_name: str | None = None,
        job: ImportJob | None = None,
        persist_progress: Callable[[], Awaitable[None]] | None = None,
    ) -> ImportResult:
        async def handle_parse_progress(current_chunk: int, total_chunks: int) -> None:
            if not job:
                return
            async with SessionLocal() as progress_session:
                progress_job = await progress_session.get(ImportJob, job.id)
                if not progress_job:
                    return
                progress_job.stage = "parsing_markdown"
                progress_job.stage_message = f"正在解析 Markdown chunk {current_chunk}/{total_chunks}。"
                await progress_session.commit()

        if job:
            job.stage = "parsing_markdown"
            job.stage_message = "正在切塊並解析 Markdown。"
            if persist_progress:
                await persist_progress()

        existing_conferences = await self._list_known_conference_labels(session)
        parsed_papers = await self.markdown_parser.parse_markdown_papers(
            content,
            existing_conferences=existing_conferences,
            progress_callback=handle_parse_progress if job else None,
        )
        imported: list[Paper] = []
        skipped_count = 0
        failed_count = 0
        abstract_missing_count = 0
        conference_cache: dict[str, Conference] = {}

        if job:
            job.stage = "merging_results"
            job.stage_message = "正在統整與去除重複的解析結果。"
            job.parsed_count = len(parsed_papers)
            if persist_progress:
                await persist_progress()

        for parsed in parsed_papers:
            if job:
                job.stage = "saving_papers"
                job.stage_message = f"正在處理 paper {job.processed_count + 1}/{max(len(parsed_papers), 1)}。"
                if persist_progress:
                    await persist_progress()

            existing = await self._find_existing_paper(session, parsed)
            if existing:
                skipped_count += 1
                if job:
                    job.stage_message = f"跳過重複 paper：{parsed.title}"
                    job.skipped_count = skipped_count
                    job.processed_count += 1
                    if persist_progress:
                        await persist_progress()
                continue

            try:
                conference = await self._resolve_or_create_conference(session, parsed, conference_cache)
                canonical_venue = conference.name if conference else parsed.venue
                canonical_year = conference.year if conference and conference.year else parsed.year
                canonical_source_page_url = conference.source_page_url if conference and conference.source_page_url else parsed.source_page_url
                paper = Paper(
                    title=parsed.title,
                    url=parsed.url,
                    conference_id=conference.id if conference else None,
                    source_page_url=canonical_source_page_url,
                    venue=canonical_venue,
                    year=canonical_year,
                    source_markdown_ref=source_name,
                )
                session.add(paper)
                await session.flush()

                try:
                    abstract = None
                    if parsed.url:
                        if job:
                            job.stage = "fetching_abstracts"
                            job.stage_message = f"正在抓取摘要：{parsed.title}"
                            if persist_progress:
                                await persist_progress()
                        abstract = await self.abstract_fetcher.fetch_abstract(parsed.url)
                except Exception:
                    abstract = None
                    failed_count += 1

                if not abstract:
                    paper.ingest_status = IngestStatus.METADATA_ONLY if not parsed.url else IngestStatus.ABSTRACT_MISSING
                    if parsed.url:
                        abstract_missing_count += 1
                    if job:
                        job.stage = "generating_embeddings"
                        job.stage_message = f"正在建立 metadata embedding：{parsed.title}"
                        if persist_progress:
                            await persist_progress()
                    embedding_vector = await self.embedding_service.embed_text(
                        self._build_embedding_input(
                            ParsedPaper(
                                title=parsed.title,
                                url=parsed.url,
                                source_page_url=canonical_source_page_url,
                                venue=canonical_venue,
                                year=canonical_year,
                            ),
                            None,
                        )
                    )
                    session.add(PaperEmbedding(paper_id=paper.id, embedding=embedding_vector))
                    imported.append(paper)
                else:
                    paper.abstract = abstract
                    paper.ingest_status = IngestStatus.READY
                    if job:
                        job.stage = "generating_embeddings"
                        job.stage_message = f"正在建立 abstract embedding：{parsed.title}"
                        if persist_progress:
                            await persist_progress()
                    embedding_vector = await self.embedding_service.embed_text(
                        self._build_embedding_input(
                            ParsedPaper(
                                title=parsed.title,
                                url=parsed.url,
                                source_page_url=canonical_source_page_url,
                                venue=canonical_venue,
                                year=canonical_year,
                            ),
                            abstract,
                        )
                    )
                    session.add(PaperEmbedding(paper_id=paper.id, embedding=embedding_vector))
                    imported.append(paper)
            except Exception as exc:
                await session.rollback()
                if job:
                    refreshed_job = await session.get(ImportJob, job.id)
                    if refreshed_job:
                        job = refreshed_job
                    job.stage = "saving_papers"
                    job.stage_message = f"略過匯入失敗的 paper：{parsed.title}"
                    job.failed_count = failed_count + 1
                failed_count += 1
                if persist_progress:
                    await persist_progress()
                continue

            if job:
                job.imported_count = len(imported)
                job.failed_count = failed_count
                job.abstract_missing_count = abstract_missing_count
                job.skipped_count = skipped_count
                job.processed_count += 1
                if persist_progress:
                    await persist_progress()

        summary = ImportSummary(
            parsed_count=len(parsed_papers),
            imported_count=len(imported),
            skipped_count=skipped_count,
            failed_count=failed_count,
            abstract_missing_count=abstract_missing_count,
        )
        return ImportResult(summary=summary, papers=imported)

    async def _find_existing_paper(self, session: AsyncSession, parsed: ParsedPaper) -> Paper | None:
        if parsed.url:
            exact_url_match = await session.scalar(select(Paper).where(Paper.url == parsed.url))
            if exact_url_match:
                return exact_url_match

        title_key = normalize_title_for_dedupe(parsed.title)
        title_prefix = parsed.title[:80].strip()
        stmt = select(Paper)

        if parsed.source_page_url:
            stmt = stmt.where(Paper.source_page_url == parsed.source_page_url)
        elif parsed.url:
            stmt = stmt.where(or_(Paper.url == parsed.url, Paper.title.ilike(f"%{title_prefix}%")))
        else:
            if parsed.venue:
                stmt = stmt.where(func.lower(Paper.venue) == parsed.venue.lower())
            if parsed.year:
                stmt = stmt.where(Paper.year == parsed.year)

        if parsed.year:
            stmt = stmt.where(or_(Paper.year == parsed.year, Paper.year.is_(None)))
        if parsed.venue:
            stmt = stmt.where(or_(func.lower(Paper.venue) == parsed.venue.lower(), Paper.venue.is_(None)))

        candidates = list((await session.scalars(stmt.limit(50))).all())
        for candidate in candidates:
            candidate_title_key = normalize_title_for_dedupe(candidate.title)
            if candidate_title_key == title_key:
                return candidate
        return None

    async def _list_known_conference_labels(self, session: AsyncSession) -> list[KnownConferenceLabel]:
        conferences = await self.list_conferences(session)
        return [
            KnownConferenceLabel(
                name=conference.name,
                year=conference.year,
                source_page_url=conference.source_page_url,
            )
            for conference in conferences
        ]

    async def _resolve_or_create_conference(
        self,
        session: AsyncSession,
        parsed: ParsedPaper,
        conference_cache: dict[str, Conference],
    ) -> Conference | None:
        if not parsed.venue:
            return None

        normalized_name = self._normalize_conference_name(parsed.venue)
        identity_key = self._build_conference_identity_key(
            name=parsed.venue,
            year=parsed.year,
            source_page_url=parsed.source_page_url,
        )
        cached = conference_cache.get(identity_key)
        if cached:
            return cached

        conference = await self._find_matching_conference(
            session,
            venue=parsed.venue,
            year=parsed.year,
            source_page_url=parsed.source_page_url,
        )
        if conference:
            conference_cache[identity_key] = conference
            return conference

        conference = Conference(
            name=parsed.venue.strip(),
            normalized_name=normalized_name,
            identity_key=identity_key,
            source_page_url=parsed.source_page_url,
            year=parsed.year,
        )
        session.add(conference)
        await session.flush()
        conference_cache[identity_key] = conference
        return conference

    async def _find_matching_conference(
        self,
        session: AsyncSession,
        venue: str,
        year: int | None,
        source_page_url: str | None,
    ) -> Conference | None:
        normalized_name = self._normalize_conference_name(venue)
        stmt = select(Conference).where(Conference.normalized_name == normalized_name)
        if year is not None:
            stmt = stmt.where(or_(Conference.year == year, Conference.year.is_(None)))
        if source_page_url:
            stmt = stmt.where(or_(Conference.source_page_url == source_page_url, Conference.source_page_url.is_(None)))
        candidates = list((await session.scalars(stmt.limit(20))).all())
        if not candidates:
            return None
        candidates.sort(
            key=lambda conference: (
                0 if conference.source_page_url == source_page_url and source_page_url else 1,
                0 if conference.year == year and year is not None else 1,
                conference.name,
            )
        )
        return candidates[0]

    def _normalize_conference_name(self, name: str) -> str:
        lowered = name.lower()
        alnum_only = "".join(char if char.isalnum() else " " for char in lowered)
        return " ".join(alnum_only.split())

    def _build_conference_identity_key(
        self,
        name: str,
        year: int | None,
        source_page_url: str | None,
    ) -> str:
        return f"{self._normalize_conference_name(name)}::{year or ''}::{source_page_url or ''}"

    def _build_embedding_input(self, parsed: ParsedPaper, abstract: str | None) -> str:
        parts = [parsed.title]
        if abstract:
            parts.append(abstract)
        if parsed.venue:
            parts.append(parsed.venue)
        if parsed.year:
            parts.append(str(parsed.year))
        if parsed.source_page_url:
            parts.append(parsed.source_page_url)
        return "\n\n".join(parts)
