from dataclasses import asdict, dataclass, field

import httpx

from paper_agent.config import get_settings


@dataclass(slots=True)
class BrowserUseTaskResult:
    status: str
    task: str
    final_result: str | None = None
    urls: list[str] = field(default_factory=list)
    extracted_content: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    steps: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class BrowserUseService:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = get_settings()
        self.base_url = (base_url or self.settings.browser_service_url).rstrip("/")
        self.http_client = http_client

    async def browse_task(
        self,
        task: str,
        *,
        start_url: str | None = None,
        max_steps: int | None = None,
    ) -> BrowserUseTaskResult:
        payload = {
            "task": task,
            "start_url": start_url,
            "max_steps": max_steps,
        }

        try:
            if self.http_client is not None:
                response = await self.http_client.post(f"{self.base_url}/browse", json=payload)
                response.raise_for_status()
                data = response.json()
                return BrowserUseTaskResult(**data)

            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(f"{self.base_url}/browse", json=payload)
                response.raise_for_status()
                data = response.json()
                return BrowserUseTaskResult(**data)
        except httpx.HTTPError as exc:
            return BrowserUseTaskResult(
                status="error",
                task=task,
                errors=[str(exc)],
            )
