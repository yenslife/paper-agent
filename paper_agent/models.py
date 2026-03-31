import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBEDDING_DIMENSIONS = 1536


class Base(DeclarativeBase):
    pass


class IngestStatus(str, enum.Enum):
    READY = "ready"
    METADATA_ONLY = "metadata_only"
    ABSTRACT_MISSING = "abstract_missing"
    FETCH_FAILED = "fetch_failed"


class ImportJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


def enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [str(item.value) for item in enum_cls]


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True, unique=True, index=True)
    conference_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("conferences.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_page_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    venue: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_markdown_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ingest_status: Mapped[IngestStatus] = mapped_column(
        Enum(IngestStatus, name="ingest_status", values_callable=enum_values),
        nullable=False,
        default=IngestStatus.ABSTRACT_MISSING,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    embedding: Mapped["PaperEmbedding | None"] = relationship(
        back_populates="paper",
        uselist=False,
        cascade="all, delete-orphan",
    )
    conference: Mapped["Conference | None"] = relationship(back_populates="papers")


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[ImportJobStatus] = mapped_column(
        Enum(ImportJobStatus, name="import_job_status", values_callable=enum_values),
        nullable=False,
        default=ImportJobStatus.PENDING,
    )
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stage_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    abstract_missing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Conference(Base):
    __tablename__ = "conferences"
    __table_args__ = (UniqueConstraint("identity_key", name="uq_conferences_identity_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    identity_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_page_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    papers: Mapped[list["Paper"]] = relationship(back_populates="conference")


class PaperEmbedding(Base):
    __tablename__ = "paper_embeddings"
    __table_args__ = (UniqueConstraint("paper_id", name="uq_paper_embeddings_paper_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    paper_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    paper: Mapped[Paper] = relationship(back_populates="embedding")
