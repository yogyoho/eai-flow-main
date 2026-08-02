"""Extensions module configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (two levels up from this file: extensions/ -> app/ -> backend/)
_env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
load_dotenv(_env_path, override=False)

from pydantic import BaseModel, Field  # noqa: E402


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


class SmtpConfig(BaseModel):
    """SMTP 配置：用于 OTP 验证码邮件的发送（EAI-CUSTOM 认证门面）。"""

    host: str = Field(default="")
    port: int = Field(default=465)
    user: str = Field(default="")
    password: str = Field(default="")
    from_addr: str = Field(default="no-reply@eai-flow.com")
    use_tls: bool = Field(default=True)
    enabled: bool = Field(default=False)

    @property
    def usable(self) -> bool:
        """SMTP 是否可用：需显式启用且配置了主机地址。"""
        return self.enabled and bool(self.host)

    @classmethod
    def from_env(cls) -> "SmtpConfig":
        """从环境变量读取 SMTP 配置（EAI_SMTP_*）。"""
        return cls(
            host=os.getenv("EAI_SMTP_HOST", ""),
            port=int(os.getenv("EAI_SMTP_PORT", "465")),
            user=os.getenv("EAI_SMTP_USER", ""),
            password=os.getenv("EAI_SMTP_PASSWORD", ""),
            from_addr=os.getenv("EAI_SMTP_FROM", "no-reply@eai-flow.com"),
            use_tls=os.getenv("EAI_SMTP_TLS", "true").lower() == "true",
            enabled=os.getenv("EAI_SMTP_ENABLED", "false").lower() == "true",
        )


class OtpConfig(BaseModel):
    """OTP 登录配置（EAI-CUSTOM 认证门面）。"""

    length: int = Field(default=6, ge=4, le=10)
    ttl_seconds: int = Field(default=300, ge=60)
    send_cooldown_seconds: int = Field(default=60, ge=10)
    max_per_ip_per_hour: int = Field(default=20)

    @classmethod
    def from_env(cls) -> "OtpConfig":
        """从环境变量读取 OTP 配置（EAI_OTP_*）。"""
        return cls(
            length=int(os.getenv("EAI_OTP_LENGTH", "6")),
            ttl_seconds=int(os.getenv("EAI_OTP_TTL_SECONDS", "300")),
            send_cooldown_seconds=int(os.getenv("EAI_OTP_SEND_COOLDOWN_SECONDS", "60")),
            max_per_ip_per_hour=int(os.getenv("EAI_OTP_MAX_PER_IP_HOUR", "20")),
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


class LawDatasetInfo(BaseModel):
    """Display info for a single law dataset."""

    name: str = Field(default="", description="Display name for the knowledge base")
    description: str = Field(default="", description="Description for the knowledge base")


class LawConfig(BaseModel):
    """Law module configuration."""

    dataset_display_info: dict[str, LawDatasetInfo] = Field(
        default_factory=lambda: {
            "ragflow-laws-legal": LawDatasetInfo(
                name="法规标准库 — 法律/法规/规章",
                description="法律、行政法规和部门规章知识库，按条/款/项结构分块",
            ),
            "ragflow-laws-standards": LawDatasetInfo(
                name="法规标准库 — 标准/规范",
                description="国家标准、行业标准、地方标准和技术规范知识库，按章/节标题边界分块",
            ),
        },
        description="Display info for law datasets, keyed by RAGFlow dataset name",
    )

    @classmethod
    def from_env(cls) -> "LawConfig":
        return cls()


class ExtensionsConfig(BaseModel):
    """Extensions module configuration."""

    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    jwt: JWTConfig = Field(default_factory=JWTConfig)
    ragflow: RAGFlowConfig = Field(default_factory=RAGFlowConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    law: LawConfig = Field(default_factory=LawConfig)
    smtp: SmtpConfig = Field(default_factory=SmtpConfig)
    otp: OtpConfig = Field(default_factory=OtpConfig)

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
            law=LawConfig.from_env(),
            smtp=SmtpConfig.from_env(),
            otp=OtpConfig.from_env(),
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
