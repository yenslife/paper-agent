from dataclasses import dataclass, field

from browser_use import Agent, Browser, ChatOpenAI

from browser_service.config import get_settings
from browser_service.schemas import BrowseResponse


@dataclass(slots=True)
class BrowserTaskResult:
    status: str
    task: str
    final_result: str | None = None
    urls: list[str] = field(default_factory=list)
    extracted_content: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    steps: int = 0

    def to_response(self) -> BrowseResponse:
        return BrowseResponse(
            status=self.status,
            task=self.task,
            final_result=self.final_result,
            urls=self.urls,
            extracted_content=self.extracted_content,
            errors=self.errors,
            steps=self.steps,
        )


class BrowserAutomationService:
    def __init__(
        self,
        browser_cls: type[Browser] = Browser,
        agent_cls: type[Agent] = Agent,
        llm_cls: type[ChatOpenAI] = ChatOpenAI,
    ) -> None:
        self.settings = get_settings()
        self.browser_cls = browser_cls
        self.agent_cls = agent_cls
        self.llm_cls = llm_cls

    async def browse_task(
        self,
        task: str,
        *,
        start_url: str | None = None,
        max_steps: int | None = None,
    ) -> BrowserTaskResult:
        browser = self.browser_cls(
            headless=self.settings.browser_use_headless,
            is_local=True,
            use_cloud=False,
            executable_path=self.settings.browser_use_executable_path,
        )
        llm = self.llm_cls(
            model=self.settings.browser_use_model,
            temperature=0.0,
            reasoning_effort="none",
            api_key=self.settings.openai_api_key,
        )

        full_task = task.strip()
        if start_url:
            full_task = f"Start from {start_url}. {full_task}"

        agent = self.agent_cls(
            task=full_task,
            llm=llm,
            browser=browser,
            use_vision=False,
            max_actions_per_step=3,
            include_recent_events=False,
            use_judge=self.settings.browser_use_enable_judge,
            enable_planning=self.settings.browser_use_enable_planning,
            use_thinking=self.settings.browser_use_use_thinking,
        )

        try:
            history = await agent.run(max_steps=max_steps or self.settings.browser_use_max_steps)
            final_result = getattr(history, "final_result", lambda: None)()
            urls = list(getattr(history, "urls", lambda: [])() or [])
            extracted_content = [item for item in (getattr(history, "extracted_content", lambda: [])() or []) if item]
            errors = [str(item) for item in (getattr(history, "errors", lambda: [])() or []) if item]
            steps = int(getattr(history, "number_of_steps", lambda: 0)() or 0)
            return BrowserTaskResult(
                status="success" if not errors else "partial_success",
                task=task,
                final_result=final_result,
                urls=urls,
                extracted_content=extracted_content,
                errors=errors,
                steps=steps,
            )
        except Exception as exc:
            return BrowserTaskResult(
                status="error",
                task=task,
                errors=[str(exc)],
            )
        finally:
            try:
                await browser.stop()
            except Exception:
                pass
