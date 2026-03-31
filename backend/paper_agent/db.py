from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from paper_agent.config import get_settings
from paper_agent.models import Base

settings = get_settings()

engine = create_async_engine(settings.database_url, future=True, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _rename_enum_value_if_present(
    connection,
    enum_name: str,
    old_value: str,
    new_value: str,
) -> None:
    rows = await connection.execute(
        text(
            """
            SELECT enumlabel
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = :enum_name
            """
        ),
        {"enum_name": enum_name},
    )
    labels = {row[0] for row in rows.fetchall()}
    if old_value in labels and new_value not in labels:
        await connection.execute(
            text(f"ALTER TYPE {enum_name} RENAME VALUE '{old_value}' TO '{new_value}'")
        )


async def initialize_database() -> None:
    async with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await _rename_enum_value_if_present(connection, "import_job_status", "PENDING", "pending")
            await _rename_enum_value_if_present(connection, "import_job_status", "RUNNING", "running")
            await _rename_enum_value_if_present(connection, "import_job_status", "COMPLETED", "completed")
            await _rename_enum_value_if_present(connection, "import_job_status", "FAILED", "failed")
            await _rename_enum_value_if_present(connection, "ingest_status", "READY", "ready")
            await _rename_enum_value_if_present(connection, "ingest_status", "ABSTRACT_MISSING", "abstract_missing")
            await _rename_enum_value_if_present(connection, "ingest_status", "FETCH_FAILED", "fetch_failed")
            await connection.execute(text("ALTER TYPE ingest_status ADD VALUE IF NOT EXISTS 'metadata_only'"))
        await connection.run_sync(Base.metadata.create_all)
        if connection.dialect.name == "postgresql":
            await connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS conferences (
                        id VARCHAR(36) PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        normalized_name VARCHAR(255) NOT NULL,
                        identity_key VARCHAR(1024) NOT NULL,
                        source_page_url VARCHAR(2048),
                        year INTEGER,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            )
            await connection.execute(
                text("CREATE UNIQUE INDEX IF NOT EXISTS uq_conferences_identity_key ON conferences (identity_key)")
            )
            await connection.execute(text("CREATE INDEX IF NOT EXISTS ix_conferences_name ON conferences (name)"))
            await connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_conferences_normalized_name ON conferences (normalized_name)")
            )
            await connection.execute(text("CREATE INDEX IF NOT EXISTS ix_conferences_year ON conferences (year)"))
            await connection.execute(text("ALTER TABLE papers ADD COLUMN IF NOT EXISTS source_page_url VARCHAR(2048)"))
            await connection.execute(text("ALTER TABLE papers ADD COLUMN IF NOT EXISTS conference_id VARCHAR(36)"))
            await connection.execute(text("ALTER TABLE papers ALTER COLUMN url DROP NOT NULL"))
            await connection.execute(text("ALTER TABLE papers ALTER COLUMN title TYPE TEXT"))
            await connection.execute(text("CREATE INDEX IF NOT EXISTS ix_papers_conference_id ON papers (conference_id)"))
            await connection.execute(text("ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS stage VARCHAR(64)"))
            await connection.execute(text("ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS stage_message TEXT"))


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
