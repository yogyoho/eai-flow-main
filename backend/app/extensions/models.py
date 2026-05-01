"""SQLAlchemy data models for extensions module."""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions.database import Base


class User(Base):
    """User model."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dept_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)
    role_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    emp_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    department: Mapped[Optional["Department"]] = relationship("Department", back_populates="users", foreign_keys=[dept_id])
    role: Mapped[Optional["Role"]] = relationship("Role", back_populates="users")
    user_departments: Mapped[list["UserDepartment"]] = relationship("UserDepartment", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username})>"


class Role(Base):
    """Role model."""

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    permissions: Mapped[list] = mapped_column(ARRAY(String), default=[])
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=10)
    parent_role_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # Relationships
    users: Mapped[list["User"]] = relationship("User", back_populates="role")
    parent_role: Mapped[Optional["Role"]] = relationship("Role", remote_side=[id], back_populates="child_roles")
    child_roles: Mapped[list["Role"]] = relationship("Role", back_populates="parent_role")

    def __repr__(self) -> str:
        return f"<Role(id={self.id}, name={self.name})>"


class Department(Base):
    """Department model (tree structure)."""

    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    leader_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # Relationships
    parent: Mapped[Optional["Department"]] = relationship("Department", back_populates="children", remote_side=[id])
    children: Mapped[list["Department"]] = relationship("Department", back_populates="parent")
    users: Mapped[list["User"]] = relationship("User", back_populates="department", foreign_keys="User.dept_id")
    user_departments: Mapped[list["UserDepartment"]] = relationship("UserDepartment", back_populates="department", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Department(id={self.id}, name={self.name})>"


class UserDepartment(Base):
    """User-Department many-to-many association table."""

    __tablename__ = "user_departments"
    __table_args__ = (UniqueConstraint("user_id", "dept_id", name="uq_user_dept"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="user_departments")
    department: Mapped["Department"] = relationship("Department", back_populates="user_departments")


class KnowledgeBase(Base):
    """Knowledge base model."""

    __tablename__ = "knowledge_bases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    ragflow_dataset_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    access_type: Mapped[str] = mapped_column(String(20), default="private")
    kb_type: Mapped[str] = mapped_column(String(50), default="ragflow")
    allowed_depts: Mapped[list | None] = mapped_column(ARRAY(UUID), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chunk_method: Mapped[str] = mapped_column(String(50), default="naive")
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # Relationships
    owner: Mapped["User"] = relationship("User", backref="knowledge_bases")

    def __repr__(self) -> str:
        return f"<KnowledgeBase(id={self.id}, name={self.name})>"


class Document(Base):
    """Document model for knowledge base."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_bases.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    file_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ragflow_document_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # Relationships
    knowledge_base: Mapped["KnowledgeBase"] = relationship("KnowledgeBase", back_populates="documents")

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, name={self.name})>"


# Add back-populates for KnowledgeBase
KnowledgeBase.documents: Mapped[list[Document]] = relationship("Document", back_populates="knowledge_base")


class AIDocument(Base):
    """AI-generated document model for document space management."""

    __tablename__ = "ai_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    source_thread_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    folder: Mapped[str] = mapped_column(String(255), default="默认文件夹", nullable=False)
    is_starred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="ai_documents")

    def __repr__(self) -> str:
        return f"<AIDocument(id={self.id}, title={self.title})>"


class Conversation(Base):
    """Conversation model - maps thread_id to user_id for data isolation."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    thread_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="conversations")

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, thread_id={self.thread_id}, user_id={self.user_id})>"


User.conversations: Mapped[list[Conversation]] = relationship("Conversation", back_populates="user")

User.ai_documents: Mapped[list[AIDocument]] = relationship("AIDocument", back_populates="user")


class UserMemory(Base):
    """User-specific memory model for storing personalized memory data."""

    __tablename__ = "user_memories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    memory_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[str] = mapped_column(String(10), nullable=False, default="1.0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="user_memories")

    def __repr__(self) -> str:
        return f"<UserMemory(user_id={self.user_id})>"


User.user_memories: Mapped[list[UserMemory]] = relationship("UserMemory", back_populates="user")


class ScrapDraft(Base):
    """网页爬取草稿模型"""

    __tablename__ = "scrap_drafts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    schema_name: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    tags: Mapped[list] = mapped_column(ARRAY(String), default=[])
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_provider: Mapped[str] = mapped_column(String(50), default="browser_use_local")
    scrape_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(
        String(20),
        default="draft",
        nullable=False,
        index=True,
    )
    knowledge_base_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id"),
        nullable=True,
    )
    document_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship("User", back_populates="scrap_drafts")
    knowledge_base: Mapped[Optional["KnowledgeBase"]] = relationship(
        "KnowledgeBase",
        back_populates="scrap_drafts",
    )

    def __repr__(self) -> str:
        return f"<ScrapDraft(id={self.id}, title={self.title[:30] if self.title else 'None'}, status={self.status})>"


# 添加反向关系
User.scrap_drafts: Mapped[list["ScrapDraft"]] = relationship(
    "ScrapDraft",
    back_populates="user",
    cascade="all, delete-orphan",
)

KnowledgeBase.scrap_drafts: Mapped[list["ScrapDraft"]] = relationship(
    "ScrapDraft",
    back_populates="knowledge_base",
)


class Law(Base):
    """Law/regulation data model."""

    __tablename__ = "laws"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    law_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    law_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    department: Mapped[str | None] = mapped_column(String(200), nullable=True)
    effective_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ref_count: Mapped[int] = mapped_column(Integer, default=0)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ragflow_dataset_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ragflow_document_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_synced: Mapped[str] = mapped_column(String(10), default="pending")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    template_relations: Mapped[list["LawTemplateRelation"]] = relationship("LawTemplateRelation", back_populates="law", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Law(id={self.id}, title={self.title}, type={self.law_type})>"


class LawTemplateRelation(Base):
    """Law and template relation model."""

    __tablename__ = "law_template_relations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    law_id: Mapped[str] = mapped_column(String(36), ForeignKey("laws.id", ondelete="CASCADE"), index=True, nullable=False)
    template_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    section_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    law: Mapped["Law"] = relationship("Law", back_populates="template_relations")

    def __repr__(self) -> str:
        return f"<LawTemplateRelation(law_id={self.law_id}, template_id={self.template_id})>"
