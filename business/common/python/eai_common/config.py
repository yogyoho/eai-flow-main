"""Shared pydantic-settings configuration for all business microservices."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class BusinessServiceSettings(BaseSettings):
    """Base settings loaded from environment variables for all business services."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/service"
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    api_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 3000
    log_level: str = "INFO"

    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:4000",
        "http://localhost:4026",
    ]


@lru_cache
def get_settings() -> BusinessServiceSettings:
    """Return cached settings instance."""
    return BusinessServiceSettings()
