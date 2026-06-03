"""SQLAlchemy model for layout_templates table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base


class LayoutTemplate(Base):
    __tablename__ = "layout_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    report_type: Mapped[str] = mapped_column(String(100), nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    page_settings: Mapped[dict] = mapped_column(JSONB, nullable=False)
    cover_template: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    toc_settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    body_styles: Mapped[dict] = mapped_column(JSONB, nullable=False)
    heading_styles: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    table_styles: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    figure_styles: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    header_footer: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reference_style: Mapped[str] = mapped_column(String(50), nullable=False, default="gb7714")
    appendix_rules: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now())
