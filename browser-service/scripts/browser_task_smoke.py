import asyncio
import os

from browser_service.service import BrowserAutomationService


async def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required for browser task smoke test")

    service = BrowserAutomationService()
    result = await service.browse_task(
        task="Read the page title and confirm the page says ok.",
        start_url="data:text/html,<title>Paper Agent Browser Smoke</title><h1>ok</h1>",
        max_steps=2,
    )

    assert result.status in {"success", "partial_success"}, result
    assert result.final_result, result


if __name__ == "__main__":
    asyncio.run(main())
