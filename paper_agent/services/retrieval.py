from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from paper_agent.config import get_settings
from paper_agent.models import IngestStatus, Paper, PaperEmbedding
from paper_agent.schemas import RetrievedPaper
from paper_agent.services.embeddings import EmbeddingService


class RetrievalService:
    def __init__(self, embedding_service: EmbeddingService) -> None:
        self.embedding_service = embedding_service
        self.settings = get_settings()

    async def search_papers(
        self,
        session: AsyncSession,
        query: str,
        venue: str | None = None,
        year: int | None = None,
        top_k: int | None = None,
    ) -> list[RetrievedPaper]:
        query_embedding = await self.embedding_service.embed_text(query)
        limit = top_k or self.settings.retrieval_top_k

        score_expr = (1 - PaperEmbedding.embedding.cosine_distance(query_embedding)).label("score")
        stmt: Select[tuple[Paper, float]] = (
            select(Paper, score_expr)
            .join(PaperEmbedding, PaperEmbedding.paper_id == Paper.id)
            .where(Paper.ingest_status.in_([IngestStatus.READY, IngestStatus.METADATA_ONLY, IngestStatus.ABSTRACT_MISSING]))
            .order_by(score_expr.desc())
            .limit(limit)
        )

        if venue:
            stmt = stmt.where(func.lower(Paper.venue) == venue.lower())
        if year:
            stmt = stmt.where(Paper.year == year)

        rows = (await session.execute(stmt)).all()
        return [
            RetrievedPaper(
                id=paper.id,
                title=paper.title,
                url=paper.url,
                source_page_url=paper.source_page_url,
                venue=paper.venue,
                year=paper.year,
                abstract=paper.abstract,
                score=round(float(score), 4),
            )
            for paper, score in rows
        ]

    async def find_papers_by_title(
        self,
        session: AsyncSession,
        title: str,
        limit: int = 5,
    ) -> list[Paper]:
        normalized = " ".join(title.split())
        if not normalized:
            return []

        exact_stmt = (
            select(Paper)
            .where(func.lower(Paper.title) == normalized.lower())
            .order_by(Paper.created_at.desc())
            .limit(limit)
        )
        exact_matches = list((await session.scalars(exact_stmt)).all())
        if exact_matches:
            return exact_matches

        fuzzy_stmt = (
            select(Paper)
            .where(Paper.title.ilike(f"%{normalized}%"))
            .order_by(Paper.created_at.desc())
            .limit(limit)
        )
        return list((await session.scalars(fuzzy_stmt)).all())

    async def get_papers_by_ids(self, session: AsyncSession, paper_ids: list[str]) -> list[Paper]:
        if not paper_ids:
            return []
        stmt = select(Paper).where(Paper.id.in_(paper_ids)).order_by(Paper.created_at.desc())
        return list((await session.scalars(stmt)).all())
