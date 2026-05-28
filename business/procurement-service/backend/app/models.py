"""SQLAlchemy 模型定义"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class Expert(Base):
    """评标专家"""
    __tablename__ = "experts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    id_card: Mapped[Optional[str]] = mapped_column(String(18), unique=True, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    expertise: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    organization: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    evaluation_count: Mapped[int] = mapped_column(default=0)
    avg_score: Mapped[Optional[float]] = mapped_column(Numeric(3, 2), nullable=True)
    bank_account: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    bank_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=utc_now, nullable=False
    )


class ExpertDraw(Base):
    """专家抽取记录"""
    __tablename__ = "expert_draws"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tender_projects.id"), nullable=False, index=True
    )
    drawn_expert_ids: Mapped[list] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False)
    required_count: Mapped[int] = mapped_column(default=5)
    draw_method: Mapped[str] = mapped_column(String(50), default="random")
    operator_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    drawn_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ExpertReview(Base):
    """专家评价"""
    __tablename__ = "expert_reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    expert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experts.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tender_projects.id"), nullable=False, index=True
    )
    bid_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bids.id"), nullable=True
    )
    punctuality_score: Mapped[Optional[float]] = mapped_column(Numeric(2, 1), nullable=True)
    professional_score: Mapped[Optional[float]] = mapped_column(Numeric(2, 1), nullable=True)
    fairness_score: Mapped[Optional[float]] = mapped_column(Numeric(2, 1), nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewer_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Bidder(Base):
    """投标人"""
    __tablename__ = "bidders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    unified_credit_code: Mapped[Optional[str]] = mapped_column(
        String(18), unique=True, nullable=True
    )
    legal_person: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    contact_person: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    business_scope: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    credit_rating: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="approved", index=True)
    registration_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=utc_now, nullable=False
    )


class TenderPlan(Base):
    """招标计划"""
    __tablename__ = "tender_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plan_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    procurement_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    procurement_method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    dept_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    dept_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    budget: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    estimated_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    funding_source: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    plan_year: Mapped[Optional[int]] = mapped_column(nullable=True, index=True)
    estimated_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    estimated_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        Index("ix_tender_plans_year_type", "plan_year", "procurement_type"),
    )


class TenderProject(Base):
    """招标项目"""
    __tablename__ = "tender_projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    procurement_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    procurement_method: Mapped[str] = mapped_column(String(50), nullable=False)
    dept_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    dept_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    budget: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    control_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    funding_source: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    bid_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    plan_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tender_plans.id"), nullable=True
    )
    announcement_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    qualification_requirements: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="draft", index=True
    )
    bidding_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    bidding_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    evaluation_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=utc_now, nullable=False
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_tender_projects_status_method", "status", "procurement_method"),
    )


class Bid(Base):
    """投标记录"""
    __tablename__ = "bids"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tender_projects.id"), nullable=False, index=True
    )
    bidder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bidders.id"), nullable=False, index=True
    )
    bid_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    bid_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    technical_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    commercial_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    total_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    ranking: Mapped[Optional[int]] = mapped_column(nullable=True)
    technical_proposal_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    compliance_check_passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    compliance_issues: Mapped[Optional[list]] = mapped_column(ARRAY(Text), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="submitted", index=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        Index("ix_bids_project_bidder", "project_id", "bidder_id"),
    )


class Evaluation(Base):
    """评标记录"""
    __tablename__ = "evaluations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tender_projects.id"), nullable=False, index=True
    )
    bid_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bids.id"), nullable=False, index=True
    )
    evaluation_type: Mapped[str] = mapped_column(String(20), default="technical")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    technical_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    commercial_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    total_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    ranking: Mapped[Optional[int]] = mapped_column(nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evaluation_report_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    evaluation_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evaluator_ids: Mapped[Optional[list]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=utc_now, nullable=False
    )


class WinningBid(Base):
    """中标记录"""
    __tablename__ = "winning_bids"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tender_projects.id"), nullable=False, index=True
    )
    bid_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bids.id"), nullable=False
    )
    winning_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    decision_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    decided_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Contract(Base):
    """合同"""
    __tablename__ = "contracts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    contract_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tender_projects.id"), nullable=False, index=True
    )
    winning_bid_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("winning_bids.id"), nullable=True
    )
    bidder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bidders.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    total_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    sign_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_terms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contract_file_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    risk_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    risk_issues: Mapped[Optional[list]] = mapped_column(ARRAY(Text), nullable=True)
    operator_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=utc_now, nullable=False
    )


class Complaint(Base):
    """投诉"""
    __tablename__ = "complaints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tender_projects.id"), nullable=True, index=True
    )
    complaint_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    complaint_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_urls: Mapped[Optional[list]] = mapped_column(ARRAY(String(500)), nullable=True)
    complainer_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    complainer_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="submitted", index=True)
    priority: Mapped[str] = mapped_column(String(20), default="normal", index=True)
    response_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decision_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    responded_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=utc_now, nullable=False
    )


class WitnessRecord(Base):
    """见证记录"""
    __tablename__ = "witness_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tender_projects.id"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    audio_transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risk_warnings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sensitive_words_detected: Mapped[Optional[list]] = mapped_column(ARRAY(String(100)), nullable=True)
    video_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    operator_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VenueSpace(Base):
    """场所工位"""
    __tablename__ = "venue_spaces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    venue_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    space_no: Mapped[str] = mapped_column(String(50), nullable=False)
    floor: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    capacity: Mapped[Optional[int]] = mapped_column(nullable=True)
    equipment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hourly_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="available", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=utc_now, nullable=False
    )
