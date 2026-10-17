"""Application settings — Pydantic v2 + pydantic-settings."""

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # FastAPI server settings
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = True

    # Supabase configuration
    supabase_url: str = "https://placeholder.supabase.co"
    supabase_key: str = "placeholder-key"
    supabase_service_role_key: str | None = None
    supabase_jwt_secret: str = "super-secret-jwt-token-with-at-least-32-chars-long"
    database_url: str = "postgresql://postgres:postgres@localhost:5432/postgres"

    # Security & CORS settings
    cors_origins: list[str] = ["http://localhost:3000"]
    cors_origin_regex: str | None = r"^https://.*\.vercel\.app$"
    trusted_proxies: list[str] = ["127.0.0.1", "::1"]

    # Billing & Subscription settings
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    default_free_interviews_limit: int = 5
    default_free_tokens_limit: int = 50000

    # Document ingestion settings
    supabase_storage_bucket: str = "documents"
    max_file_size_bytes: int = 10 * 1024 * 1024  # 10 MB limit
    ingestion_max_retries: int = 3
    ingestion_retry_delay_seconds: float = 1.0

    @field_validator("supabase_url", "supabase_key", "supabase_jwt_secret", "database_url")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Value must be provided and non-empty")
        return v

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
