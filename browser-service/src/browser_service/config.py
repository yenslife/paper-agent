from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Paper Agent Browser Service"
    openai_api_key: str = ""
    browser_use_model: str = "gpt-4.1-mini"
    browser_use_headless: bool = True
    browser_use_max_steps: int = 12
    browser_use_executable_path: str | None = None
    browser_use_enable_judge: bool = False
    browser_use_enable_planning: bool = False
    browser_use_use_thinking: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
