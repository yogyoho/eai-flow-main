"""应用配置"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://asset:asset@localhost:5432/asset"
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    api_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 3002
    log_level: str = "INFO"

    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:4000",
        "http://localhost:2026",
        "http://asset-frontend:3000",
    ]


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
