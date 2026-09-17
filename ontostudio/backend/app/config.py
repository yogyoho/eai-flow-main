"""扩展库连接配置（独立服务本地最小切片）.

EAI-CUSTOM: 自 backend/app/extensions/config.py 机械移植 DatabaseConfig 切片——ontology 包
迁出独立（设计: docs/superpowers/specs/2026-09-17-ontostudio-standalone-design.md）后，
app/ontology/connectors.py `_ext_url()` 的回退语义保持同源（env EXTENSIONS_DB_* 优先级与
默认值逐字段一致）。dg_* 表暂留 extensions DB（设计 §2 数据）。
"""

from __future__ import annotations

import os

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
    def from_env(cls) -> DatabaseConfig:
        return cls(
            host=os.getenv("EXTENSIONS_DB_HOST", "localhost"),
            port=int(os.getenv("EXTENSIONS_DB_PORT", "5432")),
            username=os.getenv("EXTENSIONS_DB_USER", "agentflow"),
            password=os.getenv("EXTENSIONS_DB_PASSWORD", "agentflow123"),
            name=os.getenv("EXTENSIONS_DB_NAME", "agentflow"),
        )


class ExtensionsConfig(BaseModel):
    """Extensions module configuration（独立服务只消费 database 切片）."""

    database: DatabaseConfig = Field(default_factory=DatabaseConfig)

    @classmethod
    def from_env(cls) -> ExtensionsConfig:
        """Create config from environment variables."""
        return cls(database=DatabaseConfig.from_env())


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
