"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the Backup API.

    Attributes:
        app_name: Name surfaced in the OpenAPI title.
        api_v1_prefix: URL prefix for all versioned endpoints.
        database_url: Async SQLAlchemy connection string (metadata store).
        cors_origins: List of allowed CORS origins (``*`` for all).
        api_key_header: HTTP header used for per-application API keys.
        enable_metrics: Whether to expose the Prometheus ``/metrics`` endpoint.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Backup API"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite+aiosqlite:///./backwatch.db"
    cors_origins: str = "*"
    api_key_header: str = "X-API-Key"
    enable_metrics: bool = True
    secret_key: str = "change-me-in-production"

    @property
    def cors_origin_list(self) -> list[str]:
        """Return the CORS origins as a list.

        Returns:
            A list of origin strings, or ``["*"]`` when the wildcard is set.
        """
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings.

    Returns:
        The single shared Settings instance.
    """
    return Settings()
