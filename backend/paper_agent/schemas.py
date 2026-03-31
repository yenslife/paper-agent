from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ImportMarkdownRequest(BaseModel):
    content: str = Field(..., min_length=1, description="Markdown content containing paper links.")
    source_name: str | None = Field(default=None, description="Optional logical name for the source list.")


class FetchMarkdownResponse(BaseModel):
    source_url: str
    fetched_url: str
    markdown: str


class ImportSummary(BaseModel):
    parsed_count: int
    imported_count: int
    skipped_count: int
    failed_count: int
    abstract_missing_count: int


class ImportJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_name: str | None = None
    status: str
    cancel_requested: bool = False
    stage: str | None = None
    stage_message: str | None = None
    parsed_count: int
    processed_count: int
    imported_count: int
    skipped_count: int
    failed_count: int
    abstract_missing_count: int
    error_message: str | None = None


class PaperRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    url: str | None = None
    conference_id: str | None = None
    conference_name: str | None = None
    source_page_url: str | None = None
    venue: str | None = None
    year: int | None = None
    abstract: str | None = None
    ingest_status: str


class PaperListResponse(BaseModel):
    items: list[PaperRead]
    page: int
    page_size: int
    total_items: int
    total_pages: int


class PaperUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1)
    conference_id: str | None = None
    url: str | None = None
    source_page_url: str | None = None
    venue: str | None = None
    year: int | None = None
    abstract: str | None = None


class ConferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    normalized_name: str
    source_page_url: str | None = None
    year: int | None = None
    paper_count: int = 0


class ConferenceListResponse(BaseModel):
    items: list[ConferenceRead]


class PaperConferenceResolution(BaseModel):
    paper: PaperRead
    conference: ConferenceRead | None = None
    status: Literal["already_attached", "reused_existing", "created_new", "unresolved"]
    duplicate_detected: bool = False
    message: str


class BatchConferenceBindingResult(BaseModel):
    total_candidates: int
    bound_count: int
    reused_existing_count: int
    created_new_count: int
    unresolved_count: int
    message: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None
    history: list[ChatMessage] = Field(default_factory=list)


class Citation(BaseModel):
    title: str
    url: str | None = None
    source_page_url: str | None = None
    venue: str | None = None
    year: int | None = None
    source_type: Literal["local_paper_db", "web_search"]


class SourceSummary(BaseModel):
    source_type: Literal["local_paper_db", "web_search"]
    description: str


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    citations: list[Citation]
    sources: list[SourceSummary]


class RetrievedPaper(BaseModel):
    id: str
    title: str
    url: str | None = None
    source_page_url: str | None = None
    venue: str | None = None
    year: int | None = None
    abstract: str | None = None
    score: float
