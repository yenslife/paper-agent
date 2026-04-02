from pydantic import BaseModel, Field


class BrowseRequest(BaseModel):
    task: str
    start_url: str | None = None
    max_steps: int | None = Field(default=None, ge=1, le=100)


class BrowseResponse(BaseModel):
    status: str
    task: str
    final_result: str | None = None
    urls: list[str] = Field(default_factory=list)
    extracted_content: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    steps: int = 0
