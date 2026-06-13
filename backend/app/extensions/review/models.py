"""Review Context ORM models — unified replacement for PhaseReview + ApprovalWorkflow."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base


class ReviewAssignment(Base):
    """A review task assigned to one reviewer for one workflow node."""

    __tablename__ = "review_assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_projects.id"), nullable=False, index=True
    )
    phase_node: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    reviewer_role: Mapped[str] = mapped_column(
        String(50), nullable=False, default="reviewer"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending | approved | rejected
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    dimensions: Mapped[list] = mapped_column(ARRAY(String), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    previous_judgments: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<ReviewAssignment(id={self.id}, status={self.status})>"
