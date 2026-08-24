from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""

    claude_extraction_model: str = "claude-haiku-4-5-20251001"
    claude_scoring_model: str = "claude-sonnet-5"

    database_url: str = "sqlite:///./investor_scoring.db"

    max_upload_mb: int = 25

    resend_api_key: str = ""
    # tencapital.group is verified in Resend, so mail can go to any recipient.
    resend_from_email: str = "results@tencapital.group"
    results_email_to: str = "info@tencapital.group"


@lru_cache
def get_settings() -> Settings:
    return Settings()
