"""ORM models for knowledge factory module."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions.database import Base


class ExtractionDomain(Base):
    """领域/行业定义表（层级结构）"""

    __tablename__ = "extraction_domains"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    standard_chapters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<ExtractionDomain(id={self.id}, name={self.name})>"


class ExtractionTemplate(Base):
    """模板主表（领域 + 版本）"""

    __tablename__ = "extraction_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)  # draft | published | deprecated
    root_sections_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    cross_section_rules: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    completeness_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_report_ids: Mapped[list | None] = mapped_column(ARRAY(UUID), nullable=True)
    parent_template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("extraction_templates.id"), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    versions: Mapped[list["ExtractionTemplateVersion"]] = relationship(
        "ExtractionTemplateVersion",
        back_populates="template",
        cascade="all, delete-orphan",
    )
    sections: Mapped[list["TemplateSection"]] = relationship(
        "TemplateSection",
        back_populates="template",
        cascade="all, delete-orphan",
    )
    created_by_user: Mapped[Optional["User"]] = relationship("User")

    def __repr__(self) -> str:
        return f"<ExtractionTemplate(id={self.id}, name={self.name}, version={self.version})>"


class ExtractionTemplateVersion(Base):
    """模板版本历史（每次发布记录快照）"""

    __tablename__ = "extraction_template_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("extraction_templates.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    published_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), nullable=False)

    # Relationships
    template: Mapped["ExtractionTemplate"] = relationship("ExtractionTemplate", back_populates="versions")
    published_by_user: Mapped[Optional["User"]] = relationship("User")


class ExtractionTask(Base):
    """抽取任务表（记录每次抽取的输入输出）"""

    __tablename__ = "extraction_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_report_ids: Mapped[list] = mapped_column(ARRAY(UUID), nullable=False, default=list)
    target_template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("extraction_templates.id"), nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)  # pending | running | completed | failed | paused
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    steps: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=list)
    result_template_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    created_by_user: Mapped[Optional["User"]] = relationship("User")

    def __repr__(self) -> str:
        return f"<ExtractionTask(id={self.id}, status={self.status})>"


class TemplateSection(Base):
    """章节内容契约表（可独立管理单个章节）"""

    __tablename__ = "template_sections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("extraction_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    section_id: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_contract: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    compliance_rules: Mapped[list | None] = mapped_column(ARRAY(Text), nullable=True)
    rag_sources: Mapped[list | None] = mapped_column(ARRAY(String(200)), nullable=True)
    generation_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    example_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    completeness_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    template: Mapped["ExtractionTemplate"] = relationship("ExtractionTemplate", back_populates="sections")

    def __repr__(self) -> str:
        return f"<TemplateSection(id={self.id}, section_id={self.section_id})>"


# Back-populates for existing models
from app.extensions.models import User

ExtractionTemplate.versions: Mapped[list["ExtractionTemplateVersion"]]  # noqa: F811
ExtractionTemplate.sections: Mapped[list["TemplateSection"]]  # noqa: F811
ExtractionTemplate.created_by_user: Mapped[Optional["User"]]  # noqa: F811
ExtractionTemplateVersion.template: Mapped["ExtractionTemplate"]  # noqa: F811
ExtractionTemplateVersion.published_by_user: Mapped[Optional["User"]]  # noqa: F811
ExtractionTask.created_by_user: Mapped[Optional["User"]]  # noqa: F811
TemplateSection.template: Mapped["ExtractionTemplate"]  # noqa: F811


class ComplianceRule(Base):
    """合规规则表"""

    __tablename__ = "compliance_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    type_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    severity_name: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    industry_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    report_types: Mapped[list] = mapped_column(ARRAY(String(50)), nullable=False, default=list)
    applicable_regions: Mapped[list] = mapped_column(ARRAY(String(50)), nullable=False, default=list)
    national_level: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_sections: Mapped[list] = mapped_column(ARRAY(String(200)), nullable=False, default=list)
    target_sections: Mapped[list] = mapped_column(ARRAY(String(200)), nullable=False, default=list)
    validation_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_fix_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    seed_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    created_by_user: Mapped[Optional["User"]] = relationship("User")
    execution_logs: Mapped[list["ComplianceRuleLog"]] = relationship(
        "ComplianceRuleLog",
        back_populates="rule",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ComplianceRule(id={self.id}, rule_id={self.rule_id}, name={self.name})>"


class ComplianceRuleLog(Base):
    """合规规则执行日志表"""

    __tablename__ = "compliance_rule_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("compliance_rules.id", ondelete="CASCADE"), nullable=False, index=True)
    thread_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    document_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    check_result: Mapped[str] = mapped_column(String(20), nullable=False)
    check_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), nullable=False)

    # Relationships
    rule: Mapped["ComplianceRule"] = relationship("ComplianceRule", back_populates="execution_logs")
    executed_by_user: Mapped[Optional["User"]] = relationship("User")


# Back-populates for ComplianceRule
ComplianceRule.execution_logs: Mapped[list["ComplianceRuleLog"]]  # noqa: F811
ComplianceRule.created_by_user: Mapped[Optional["User"]]  # noqa: F811
ComplianceRuleLog.rule: Mapped["ComplianceRule"]  # noqa: F811
ComplianceRuleLog.executed_by_user: Mapped[Optional["User"]]  # noqa: F811
