"""Extensions module configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (two levels up from this file: extensions/ -> app/ -> backend/)
_env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
load_dotenv(_env_path, override=False)

from pydantic import BaseModel, Field


class DatabaseConfig(BaseModel):
    """Database configuration for extensions module."""

    host: str = Field(default="localhost", description="PostgreSQL host")
    port: int = Field(default=5432, description="PostgreSQL port")
    username: str = Field(default="agentflow", description="PostgreSQL username")
    password: str = Field(default="agentflow123", description="PostgreSQL password")
    name: str = Field(default="agentflow", description="Database name")

    @property
    def url(self) -> str:
        """Get async database URL."""
        return f"postgresql+asyncpg://{self.username}:{self.password}@{self.host}:{self.port}/{self.name}"

    @property
    def sync_url(self) -> str:
        """Get sync database URL for alembic migrations."""
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.name}"

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        return cls(
            host=os.getenv("EXTENSIONS_DB_HOST", "localhost"),
            port=int(os.getenv("EXTENSIONS_DB_PORT", "5432")),
            username=os.getenv("EXTENSIONS_DB_USER", "agentflow"),
            password=os.getenv("EXTENSIONS_DB_PASSWORD", "agentflow123"),
            name=os.getenv("EXTENSIONS_DB_NAME", "agentflow"),
        )


class JWTConfig(BaseModel):
    """JWT configuration."""

    secret: str = Field(default="", description="JWT secret key")
    access_token_expire_minutes: int = Field(default=15, description="Access token expiry in minutes")
    refresh_token_expire_days: int = Field(default=7, description="Refresh token expiry in days")
    algorithm: str = Field(default="HS256", description="JWT algorithm")

    @classmethod
    def from_env(cls) -> "JWTConfig":
        import os as _os

        secret = _os.getenv("JWT_SECRET", "") or _os.getenv("JWT_SECRET_KEY", "")
        return cls(
            secret=secret,
            access_token_expire_minutes=int(_os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "15")),
            refresh_token_expire_days=int(_os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7")),
        )


class RAGFlowConfig(BaseModel):
    """RAGFlow configuration."""

    base_url: str = Field(default="http://localhost:9380", description="RAGFlow API base URL")
    api_key: str = Field(default="", description="RAGFlow API key")
    timeout: int = Field(default=30, description="Request timeout in seconds")

    @classmethod
    def from_env(cls) -> "RAGFlowConfig":
        return cls(
            base_url=os.getenv("RAGFLOW_BASE_URL", "http://localhost:9380"),
            api_key=os.getenv("RAGFLOW_API_KEY", ""),
            timeout=int(os.getenv("RAGFLOW_TIMEOUT", "30")),
        )


class StorageConfig(BaseModel):
    """Storage configuration."""

    type: str = Field(default="local", description="Storage type: local or minio")
    base_path: str = Field(default="./data/users", description="Base path for user data storage")
    retain_local_copy: bool = Field(default=True, description="Keep local file copy after upload")
    minio_endpoint: str = Field(default="localhost:9000", description="MinIO endpoint")
    minio_access_key: str = Field(default="", description="MinIO access key")
    minio_secret_key: str = Field(default="", description="MinIO secret key")
    minio_bucket: str = Field(default="kb-docs", description="MinIO bucket name")
    minio_secure: bool = Field(default=False, description="Use HTTPS for MinIO")
    minio_region: str = Field(default="", description="MinIO region")
    minio_prefix: str = Field(default="knowledge", description="Object key prefix")

    @classmethod
    def from_env(cls) -> "StorageConfig":
        return cls(
            type=os.getenv("KB_STORAGE_TYPE", "local"),
            base_path=os.getenv("KB_STORAGE_BASE_PATH", "./data/users"),
            retain_local_copy=os.getenv("KB_STORAGE_RETAIN_LOCAL_COPY", "true").lower() == "true",
            minio_endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
            minio_access_key=os.getenv("MINIO_ACCESS_KEY", ""),
            minio_secret_key=os.getenv("MINIO_SECRET_KEY", ""),
            minio_bucket=os.getenv("MINIO_BUCKET", "kb-docs"),
            minio_secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
            minio_region=os.getenv("MINIO_REGION", ""),
            minio_prefix=os.getenv("MINIO_PREFIX", "knowledge"),
        )


class ExtensionsConfig(BaseModel):
    """Extensions module configuration."""

    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    jwt: JWTConfig = Field(default_factory=JWTConfig)
    ragflow: RAGFlowConfig = Field(default_factory=RAGFlowConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

    @classmethod
    def from_config(cls, config: dict) -> "ExtensionsConfig":
        """Create config from dictionary (e.g., from config.yaml)."""
        extensions_data = config.get("extensions", {})
        return cls(**extensions_data)

    @classmethod
    def from_env(cls) -> "ExtensionsConfig":
        """Create config from environment variables."""
        return cls(
            database=DatabaseConfig.from_env(),
            jwt=JWTConfig.from_env(),
            ragflow=RAGFlowConfig.from_env(),
            storage=StorageConfig.from_env(),
        )


_extensions_config: ExtensionsConfig | None = None


def get_extensions_config() -> ExtensionsConfig:
    """Get the extensions configuration singleton."""
    global _extensions_config
    if _extensions_config is None:
        _extensions_config = ExtensionsConfig.from_env()
    return _extensions_config


def set_extensions_config(config: ExtensionsConfig) -> None:
    """Set the extensions configuration."""
    global _extensions_config
    _extensions_config = config
