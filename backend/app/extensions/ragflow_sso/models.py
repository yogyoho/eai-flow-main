"""EAI-CUSTOM: RAGFlow SSO — per-user credential cache — 本地定制,非上游.

RAGFlow 的 API token 长期有效;首次 mode=api 交换取得后按 EAI 用户持久化,
后续调用直接复用(existing_token 归属校验见 RAGFlow spec §3.4)。
表由 Base.metadata.create_all 自动建(仓库无 alembic,见 extensions/database.py:196)。
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base


class RagflowCredential(Base):
    """One row per EAI user: their RAGFlow per-user API token."""

    __tablename__ = "ragflow_credentials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    eai_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    api_token: Mapped[str] = mapped_column(String(255), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
