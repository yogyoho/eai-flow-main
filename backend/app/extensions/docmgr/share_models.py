"""Document share model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base


class DocumentShare(Base):
    """Document share record -- tracks who a document is shared with."""

    __tablename__ = "document_shares"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    share_type: Mapped[str] = mapped_column(String(20), nullable=False)
    share_target_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    share_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    permission: Mapped[str] = mapped_column(String(10), default="read", nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
