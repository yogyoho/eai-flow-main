"""SQLAlchemy model for licenses table (metadata mirror only)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base


class License(Base):
    """License metadata mirror — NOT used for authorization decisions.

    Authorization is always decided by real-time JWT verification.
    This table stores metadata for admin UI display and import history.
    """

    __tablename__ = "licenses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    jwt_jti: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="JWT unique ID"
    )
    machine_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="Bound machine ID"
    )
    type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="permanent | trial | subscription"
    )
    customer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    max_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    modules: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    features: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    issued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    jwt_raw: Mapped[str] = mapped_column(Text, nullable=False, comment="Raw JWT string")
    imported_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now()
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<License(id={self.id}, jti={self.jwt_jti}, active={self.is_active})>"
