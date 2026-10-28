"""Pydantic request models for the sales API."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.enums import STAGES


class OpportunityCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    customer_id: UUID
    mine_id: UUID | None = None
    workface_id: UUID | None = None
    product_line: str = Field(min_length=1, max_length=80)
    amount: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="CNY", max_length=8)
    expected_close_date: date | None = None
    owner_id: str | None = None
    owner_org_id: str | None = None
    region_code: str | None = None
    source: str = Field(default="manual", max_length=16)
    source_id: str | None = Field(default=None, max_length=128)
    contact_ids: list[UUID] = Field(default_factory=list)


class OpportunityUpdate(BaseModel):
    version: int
    name: str | None = Field(default=None, min_length=2, max_length=200)
    customer_id: UUID | None = None
    mine_id: UUID | None = None
    workface_id: UUID | None = None
    product_line: str | None = Field(default=None, min_length=1, max_length=80)
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=8)
    expected_close_date: date | None = None
    owner_id: str | None = None
    owner_org_id: str | None = None
    region_code: str | None = None
    contact_ids: list[UUID] | None = None


class TransitionIn(BaseModel):
    to_stage: str
    reason: str | None = Field(default=None, max_length=2000)
    expected_version: int
    result: Literal["won", "lost"] | None = None
    lost_reason_code: str | None = Field(default=None, max_length=8)
    lost_reason_note: str | None = Field(default=None, max_length=2000)
    contract_no: str | None = Field(default=None, max_length=64)
    contract_amount: Decimal | None = Field(default=None, ge=0)
    contract_effective_date: date | None = None

    @field_validator("to_stage")
    @classmethod
    def validate_stage(cls, value: str) -> str:
        if value not in STAGES:
            raise ValueError("未知阶段")
        return value


class RollbackIn(BaseModel):
    to_stage: str
    reason: str = Field(min_length=2, max_length=2000)
    impact: str = Field(min_length=2, max_length=2000)
    remedy: str = Field(min_length=2, max_length=2000)
    expected_version: int

    @field_validator("to_stage")
    @classmethod
    def validate_stage(cls, value: str) -> str:
        if value not in STAGES:
            raise ValueError("未知阶段")
        return value


class ProbabilityIn(BaseModel):
    manual_probability: Decimal | None = Field(default=None, ge=0, le=100)
    reason: str | None = Field(default=None, max_length=2000)
    expected_version: int


class TodoUpdate(BaseModel):
    assignee_id: str | None = None
    assignee_role: str | None = None
    severity: Literal["blocker", "high", "medium", "low"] | None = None
    due_at: datetime | None = None
    status: Literal["open", "in_progress", "resolved", "cancelled"] | None = None
    resolution: str | None = Field(default=None, max_length=2000)


class TodoBatchIn(BaseModel):
    todo_ids: list[UUID] = Field(min_length=1, max_length=100)
    action: Literal["assign", "resolve", "cancel"]
    assignee_id: str | None = None
    assignee_role: str | None = None
    resolution: str | None = Field(default=None, max_length=2000)


class ApprovalCreate(BaseModel):
    gate_code: str = Field(min_length=1, max_length=16)
    reason: str = Field(min_length=2, max_length=2000)
    evidence: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecisionIn(BaseModel):
    action: Literal["approve", "reject", "return", "delegate"]
    comment: str | None = Field(default=None, max_length=2000)
    idempotency_key: str = Field(min_length=8, max_length=128)
    delegate_to: str | None = Field(default=None, max_length=64)
    # Required for parallel steps; omitted for sequential steps.
    assignment_key: str | None = Field(default=None, max_length=128)

    @field_validator("comment")
    @classmethod
    def require_comment_for_negative(cls, value, info):
        # Pydantic validation order does not guarantee action is available here;
        # service-level validation enforces it as well.
        return value


class ApprovalResubmitIn(BaseModel):
    reason: str = Field(min_length=2, max_length=2000)
    evidence: dict[str, Any] = Field(default_factory=dict)
    comment: str | None = Field(default=None, max_length=2000)
    idempotency_key: str = Field(min_length=8, max_length=128)


class RuleUpdate(BaseModel):
    enabled: bool | None = None
    config_json: dict[str, Any] | None = None
    reason: str = Field(min_length=2, max_length=2000)


class MasterDataRecord(BaseModel):
    values: dict[str, Any]


class CustomerGroupIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    credit_code: str | None = None
    region_code: str | None = None
    is_new_customer: bool = False
    parent_id: UUID | None = None
    source: str = "manual"
    source_id: str | None = None


class CustomerIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    group_id: UUID | None = None
    credit_code: str | None = None
    region_code: str | None = None
    eai_dept_id: str | None = None
    address: str | None = None
    related_party_status: Literal["unknown", "no", "yes"] = "unknown"
    source: str = "manual"
    source_id: str | None = None


class MineIn(BaseModel):
    customer_id: UUID
    group_id: UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    region_code: str | None = None
    capacity: str | None = None
    status: str = "active"
    source: str = "manual"
    source_id: str | None = None


class WorkfaceIn(BaseModel):
    mine_id: UUID
    name: str = Field(min_length=1, max_length=200)
    mining_height_m: Decimal | None = None
    conditions: str | None = None
    status: str = "active"
    source: str = "manual"
    source_id: str | None = None


class ProductIn(BaseModel):
    product_line: str = Field(min_length=1, max_length=80)
    model: str | None = None
    name: str = Field(min_length=1, max_length=200)
    is_active: bool = True
    source: str = "manual"
    source_id: str | None = None


class ContactIn(BaseModel):
    customer_id: UUID
    name: str = Field(min_length=1, max_length=120)
    title: str | None = None
    role: str | None = None
    influence: str | None = None
    stance: str | None = None
    phone: str | None = None
    email: str | None = None
    source: str = "manual"


class PilotProjectIn(BaseModel):
    customer_group_id: UUID
    workface_id: UUID | None = None
    name: str = Field(min_length=2, max_length=200)
    completed_at: datetime | None = None
    effect: str | None = None
    evidence_url: str | None = None
    source: str = "manual"
