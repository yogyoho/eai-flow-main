"""SQLAlchemy models for the QW2 sales foundation.

Business facts (opportunities, todos, approvals) are authoritative in the
`sales` database. Temporal only owns workflow history and timers. The approval
tables here are projections updated by idempotent activities.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, utc_now


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=utc_now, nullable=False)


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class SalesRegion(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "sales_regions"

    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    eai_dept_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    data_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=True)


class UserProfile(TimestampMixin, Base):
    """Sales-specific extension of the EAI user. Passwords/accounts live in EAI."""

    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    sales_role: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    region_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    data_scope: Mapped[str | None] = mapped_column(String(16), nullable=True)
    eai_dept_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=True)


class CustomerGroup(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "customer_groups"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    credit_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_groups.id"), nullable=True)
    region_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    is_new_customer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    data_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=True)
    completeness: Mapped[int] = mapped_column(Integer, default=100, nullable=False)


class Customer(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "customers"

    group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_groups.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    credit_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    region_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    eai_dept_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    related_party_status: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    data_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=True)
    completeness: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    group: Mapped[CustomerGroup | None] = relationship("CustomerGroup")


class Mine(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "mines"

    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_groups.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    region_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    capacity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    data_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=True)


class Workface(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "workfaces"

    mine_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mines.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    mining_height_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    data_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=True)


class Product(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "products"

    product_line: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class Contact(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "contacts"

    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role: Mapped[str | None] = mapped_column(String(80), nullable=True)
    influence: Mapped[str | None] = mapped_column(String(32), nullable=True)
    stance: Mapped[str | None] = mapped_column(String(32), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    data_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=True)


class OpportunityContact(UUIDMixin, Base):
    __tablename__ = "opportunity_contacts"
    __table_args__ = (UniqueConstraint("opportunity_id", "contact_id", name="uq_opportunity_contact"),)

    opportunity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contacts.id"), nullable=False, index=True)
    role: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class PilotProject(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "pilot_projects"

    customer_group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_groups.id"), nullable=False, index=True)
    workface_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("workfaces.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effect: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    data_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=True)


class Opportunity(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        Index("ix_opportunities_stage_status", "stage", "status"),
        Index("ix_opportunities_owner_status", "owner_id", "status"),
        Index("ix_opportunities_match", "customer_id", "workface_id", "product_line"),
        Index("ix_opportunities_region_close", "region_code", "product_line", "expected_close_date"),
    )

    opportunity_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    mine_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("mines.id"), nullable=True)
    workface_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("workfaces.id"), nullable=True)
    product_line: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="CNY", nullable=False)
    stage: Mapped[str] = mapped_column(String(4), default="S1", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False, index=True)
    result: Mapped[str | None] = mapped_column(String(8), nullable=True)
    stage_entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    stage_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    expected_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    owner_org_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    region_code: Mapped[str] = mapped_column(String(32), default="DEFAULT", nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rule_probability: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=10, nullable=False)
    manual_probability: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    manual_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    effective_probability: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=10, nullable=False)
    probability_source: Mapped[str] = mapped_column(String(8), default="rule", nullable=False)
    forecast_excluded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("opportunities.id"), nullable=True)
    lost_reason_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    lost_reason_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    contract_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contract_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    contract_effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    customer: Mapped[Customer] = relationship("Customer")
    mine: Mapped[Mine | None] = relationship("Mine")
    workface: Mapped[Workface | None] = relationship("Workface")


class OpportunityStageHistory(UUIDMixin, Base):
    __tablename__ = "opportunity_stage_history"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True)
    from_stage: Mapped[str | None] = mapped_column(String(4), nullable=True)
    to_stage: Mapped[str] = mapped_column(String(4), nullable=False)
    action: Mapped[str] = mapped_column(String(16), default="advance", nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    remedy: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    operator_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OpportunityProbabilityHistory(UUIDMixin, Base):
    __tablename__ = "opportunity_probability_history"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_probability: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    manual_probability: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    manual_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    effective_probability: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    changed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OpportunityGateCheck(UUIDMixin, Base):
    __tablename__ = "opportunity_gate_checks"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True)
    gate_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    rule_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OpportunityDuplicate(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "opportunity_duplicates"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True)
    duplicate_opportunity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True)
    match_keys: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    resolution: Mapped[str | None] = mapped_column(String(32), nullable=True)
    primary_opportunity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("opportunities.id"), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class QuoteConflict(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "quote_conflicts"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApprovalDefinition(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "approval_definitions"

    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), default="sequential", nullable=False)
    steps_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("code", "version", name="uq_approval_definition_code_version"),)


class ApprovalRequest(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "approval_requests"

    request_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    definition_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    definition_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("opportunities.id"), nullable=False, index=True)
    gate_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending_start", nullable=False, index=True)
    current_step: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    workflow_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    workflow_run_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    platform_instance_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    engine: Mapped[str] = mapped_column(String(32), default="sales_temporal", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    opportunity: Mapped[Opportunity] = relationship("Opportunity")
    steps: Mapped[list[ApprovalStep]] = relationship("ApprovalStep", back_populates="request", cascade="all, delete-orphan", order_by="ApprovalStep.step_no")


class ApprovalStep(UUIDMixin, Base):
    __tablename__ = "approval_steps"
    __table_args__ = (UniqueConstraint("request_id", "step_no", name="uq_approval_step_no"),)

    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), default="sequential", nullable=False)
    approver_role: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    approver_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    platform_task_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    request: Mapped[ApprovalRequest] = relationship("ApprovalRequest", back_populates="steps")
    assignments: Mapped[list[ApprovalAssignment]] = relationship(
        "ApprovalAssignment",
        back_populates="step",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ApprovalAssignment.created_at",
    )


class ApprovalAssignment(UUIDMixin, TimestampMixin, Base):
    """One participant slot inside a ``parallel_all`` / ``parallel_any`` step.

    Sequential steps keep their single decision on ``approval_steps`` for
    backwards compatibility. Parallel steps create one row per slot so each
    participant has an independent todo, decision and idempotency boundary.
    """

    __tablename__ = "approval_assignments"
    __table_args__ = (UniqueConstraint("step_id", "assignment_key", name="uq_approval_assignment_key"),)

    step_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("approval_steps.id", ondelete="CASCADE"), nullable=False, index=True)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    # ``role:<role>``, ``user:<id>`` or a template-supplied stable key.
    assignment_key: Mapped[str] = mapped_column(String(128), nullable=False)
    approver_role: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    approver_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False, index=True)
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delegated_from: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    step: Mapped[ApprovalStep] = relationship("ApprovalStep", back_populates="assignments")


class ApprovalAction(UUIDMixin, Base):
    __tablename__ = "approval_actions"

    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    assignment_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OutboxEvent(UUIDMixin, Base):
    __tablename__ = "outbox_events"

    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=True, index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Todo(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "todos"
    __table_args__ = (
        Index("ix_todos_assignee_status_due", "assignee_id", "status", "due_at"),
        Index("ix_todos_type_severity_status", "type", "severity", "status"),
        Index("ix_todos_object", "object_type", "object_id"),
        Index("uq_todos_open_dedupe", "dedupe_key", unique=True, postgresql_where=text("status IN ('open','in_progress')")),
    )

    todo_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(10), default="medium", nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    source_rule: Mapped[str | None] = mapped_column(String(16), nullable=True)
    assignee_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    assignee_role: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    sla_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class TodoEvent(UUIDMixin, Base):
    __tablename__ = "todo_events"

    todo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("todos.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    operator_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TodoEscalation(UUIDMixin, Base):
    __tablename__ = "todo_escalations"

    todo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("todos.id", ondelete="CASCADE"), nullable=False, index=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    from_assignee: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_assignee: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RoleLoadLimit(Base):
    __tablename__ = "role_load_limits"

    role_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    max_open: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=utc_now, nullable=False)


class RuleConfig(UUIDMixin, Base):
    __tablename__ = "rule_configs"

    rule_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("rule_code", "version", name="uq_rule_config_code_version"),)


class LostReasonCode(Base):
    __tablename__ = "lost_reason_codes"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    requires_note: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class WorkbenchCardConfig(Base):
    __tablename__ = "workbench_card_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    card_code: Mapped[str] = mapped_column(String(64), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("role_code", "card_code", name="uq_workbench_card"),)


class Notification(UUIDMixin, Base):
    __tablename__ = "notifications"

    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), default="system", nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuditEvent(UUIDMixin, Base):
    __tablename__ = "audit_events"

    actor_type: Mapped[str] = mapped_column(String(16), default="user", nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    object_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ImportJob(UUIDMixin, Base):
    __tablename__ = "import_jobs"

    type: Mapped[str] = mapped_column(String(32), nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="completed", nullable=False)
    error_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Attachment(UUIDMixin, Base):
    """Object-storage attachment linked to a sales object.

    Bytes live in MinIO; this table is the authorization and provenance index.
    """

    __tablename__ = "attachments"
    __table_args__ = (Index("ix_attachments_object", "object_type", "object_id"),)

    object_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    uploaded_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class NumberSequence(Base):
    __tablename__ = "number_sequences"

    prefix: Mapped[str] = mapped_column(String(16), primary_key=True)
    period: Mapped[str] = mapped_column(String(16), primary_key=True)
    next_value: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
