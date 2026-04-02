from fastapi import FastAPI

from browser_service.config import get_settings
from browser_service.schemas import BrowseRequest, BrowseResponse
from browser_service.service import BrowserAutomationService

settings = get_settings()
browser_service = BrowserAutomationService()

app = FastAPI(title=settings.app_name)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/browse", response_model=BrowseResponse)
async def browse(payload: BrowseRequest) -> BrowseResponse:
    result = await browser_service.browse_task(
        task=payload.task,
        start_url=payload.start_url,
        max_steps=payload.max_steps,
    )
    return result.to_response()
