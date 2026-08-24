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
    # Resend's sandbox sender - deliverable without a verified domain, but only
    # to the email address associated with the Resend account. Override with a
    # verified domain sender in production.
    resend_from_email: str = "onboarding@resend.dev"
    results_email_to: str = "info@tencapital.group"


@lru_cache
def get_settings() -> Settings:
    return Settings()
