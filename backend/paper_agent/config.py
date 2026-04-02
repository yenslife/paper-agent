from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Paper Agent"
    app_env: str = "development"
    openai_model: str = "gpt-4.1-mini"
    openai_parser_model: str = "gpt-4.1-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/paper_agent"
    frontend_origin: str = "http://localhost:5173"
    embedding_dimensions: int = 1536
    retrieval_top_k: int = 5
    http_timeout_seconds: float = 20.0
    web_search_context_size: str = "medium"
    max_history_messages: int = 8
    parser_chunk_size_chars: int = 12000
    parser_chunk_overlap_chars: int = 1800
    parser_max_concurrency: int = 4
    semantic_scholar_api_key: str | None = None
    pdf_markdown_chunk_chars: int = 12000
    pdf_markdown_cache_entries: int = 16
    browser_service_url: str = "http://localhost:8001"
    paper_fetch_user_agent: str = Field(
        default="paper-agent/0.1",
        description="HTTP user agent for fetching paper pages.",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
