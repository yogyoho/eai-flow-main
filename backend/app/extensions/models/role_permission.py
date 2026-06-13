"""Unified role-permission model — single source of truth for all project RBAC."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions.database import Base


class ProjectRole(str, enum.Enum):
    """Unified project-level roles — ONE taxonomy for the entire system."""

    OWNER = "owner"
    PHASE_LEAD = "phase_lead"
    WRITER = "writer"
    REVIEWER = "reviewer"
    APPROVER = "approver"


DEFAULT_ROLE_PERMISSIONS: dict[ProjectRole, set[str]] = {
    ProjectRole.OWNER: {
        "project:edit",
        "project:delete",
        "member:add",
        "member:remove",
        "chapter:write_any",
        "chapter:review_any",
        "ai:start_writing",
        "ai:stop_writing",
        "approval:submit",
        "approval:review",
        "approval:approve",
        "workflow:start",
        "workflow:cancel",
        "settings:edit",
        "export:generate",
    },
    ProjectRole.PHASE_LEAD: {
        "chapter:write_any",
        "chapter:review_any",
        "ai:start_writing",
        "approval:submit",
        "member:add",
        "outline:edit",
    },
    ProjectRole.WRITER: {
        "chapter:write_own",
        "chapter:confirm",
    },
    ProjectRole.REVIEWER: {
        "chapter:review",
        "approval:review",
    },
    ProjectRole.APPROVER: {
        "approval:approve",
        "approval:view",
    },
}


class RolePermission(Base):
    """Maps a ProjectRole to a set of permissions. Admin-editable at runtime."""

    __tablename__ = "role_permissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<RolePermission(role={self.role}, permission={self.permission})>"
