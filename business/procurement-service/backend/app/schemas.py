"""Pydantic Schema 定义"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExpertBase(BaseModel):
    name: str = Field(..., max_length=100)
    id_card: Optional[str] = Field(None, max_length=18)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)
    expertise: str = Field(..., max_length=200)
    title: Optional[str] = Field(None, max_length=100)
    organization: Optional[str] = Field(None, max_length=200)
    region: Optional[str] = Field(None, max_length=50)
    is_active: bool = True
    bank_account: Optional[str] = Field(None, max_length=50)
    bank_name: Optional[str] = Field(None, max_length=100)
    remark: Optional[str] = None


class ExpertCreate(ExpertBase):
    pass


class ExpertUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    id_card: Optional[str] = Field(None, max_length=18)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)
    expertise: Optional[str] = Field(None, max_length=200)
    title: Optional[str] = Field(None, max_length=100)
    organization: Optional[str] = Field(None, max_length=200)
    region: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None
    bank_account: Optional[str] = Field(None, max_length=50)
    bank_name: Optional[str] = Field(None, max_length=100)
    remark: Optional[str] = None


class ExpertResponse(ExpertBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    evaluation_count: int
    avg_score: Optional[float] = None
    created_at: datetime
    updated_at: datetime


class ExpertListResponse(BaseModel):
    experts: list[ExpertResponse]
    total: int


class ExpertDrawCreate(BaseModel):
    project_id: UUID
    required_count: int = Field(5, ge=1, le=50)
    draw_method: str = "random"


class ExpertDrawResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    drawn_expert_ids: list[UUID]
    required_count: int
    draw_method: str
    operator_id: Optional[str]
    drawn_at: datetime


class ExpertDrawListResponse(BaseModel):
    draws: list[ExpertDrawResponse]
    total: int


class ExpertReviewCreate(BaseModel):
    expert_id: UUID
    project_id: UUID
    bid_id: Optional[UUID] = None
    punctuality_score: Optional[float] = Field(None, ge=0, le=10)
    professional_score: Optional[float] = Field(None, ge=0, le=10)
    fairness_score: Optional[float] = Field(None, ge=0, le=10)
    comment: Optional[str] = None


class ExpertReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    expert_id: UUID
    project_id: UUID
    bid_id: Optional[UUID]
    punctuality_score: Optional[float]
    professional_score: Optional[float]
    fairness_score: Optional[float]
    comment: Optional[str]
    reviewer_id: Optional[str]
    reviewed_at: datetime


class BidderBase(BaseModel):
    name: str = Field(..., max_length=200)
    unified_credit_code: Optional[str] = Field(None, max_length=18)
    legal_person: Optional[str] = Field(None, max_length=100)
    contact_person: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = Field(None, max_length=300)
    region: Optional[str] = Field(None, max_length=50)
    business_scope: Optional[str] = None
    credit_rating: Optional[str] = Field(None, max_length=20)
    status: str = "approved"
    registration_date: Optional[datetime] = None
    remark: Optional[str] = None


class BidderCreate(BidderBase):
    pass


class BidderUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    unified_credit_code: Optional[str] = Field(None, max_length=18)
    legal_person: Optional[str] = Field(None, max_length=100)
    contact_person: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = Field(None, max_length=300)
    region: Optional[str] = Field(None, max_length=50)
    business_scope: Optional[str] = None
    credit_rating: Optional[str] = Field(None, max_length=20)
    status: Optional[str] = None
    registration_date: Optional[datetime] = None
    remark: Optional[str] = None


class BidderResponse(BidderBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime


class BidderListResponse(BaseModel):
    bidders: list[BidderResponse]
    total: int


class TenderPlanBase(BaseModel):
    plan_no: str = Field(..., max_length=50)
    title: str = Field(..., max_length=300)
    procurement_type: str = Field(..., max_length=50)
    procurement_method: Optional[str] = Field(None, max_length=50)
    dept_id: Optional[str] = Field(None, max_length=100)
    dept_name: Optional[str] = Field(None, max_length=200)
    budget: Optional[Decimal] = None
    estimated_price: Optional[Decimal] = None
    funding_source: Optional[str] = Field(None, max_length=200)
    plan_year: Optional[int] = None
    estimated_start: Optional[datetime] = None
    estimated_end: Optional[datetime] = None
    description: Optional[str] = None
    status: str = "draft"


class TenderPlanCreate(TenderPlanBase):
    pass


class TenderPlanUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=300)
    procurement_type: Optional[str] = Field(None, max_length=50)
    procurement_method: Optional[str] = Field(None, max_length=50)
    dept_id: Optional[str] = Field(None, max_length=100)
    dept_name: Optional[str] = Field(None, max_length=200)
    budget: Optional[Decimal] = None
    estimated_price: Optional[Decimal] = None
    funding_source: Optional[str] = Field(None, max_length=200)
    plan_year: Optional[int] = None
    estimated_start: Optional[datetime] = None
    estimated_end: Optional[datetime] = None
    description: Optional[str] = None
    status: Optional[str] = None


class TenderPlanResponse(TenderPlanBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime


class TenderPlanListResponse(BaseModel):
    plans: list[TenderPlanResponse]
    total: int


class TenderProjectBase(BaseModel):
    project_no: str = Field(..., max_length=50)
    title: str = Field(..., max_length=300)
    procurement_type: str = Field(..., max_length=50)
    procurement_method: str = Field(..., max_length=50)
    dept_id: Optional[str] = Field(None, max_length=100)
    dept_name: Optional[str] = Field(None, max_length=200)
    budget: Optional[Decimal] = None
    control_price: Optional[Decimal] = None
    funding_source: Optional[str] = Field(None, max_length=200)
    bid_amount: Optional[Decimal] = None
    plan_id: Optional[UUID] = None
    announcement_url: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    qualification_requirements: Optional[str] = None
    status: str = "draft"
    bidding_start: Optional[datetime] = None
    bidding_end: Optional[datetime] = None
    evaluation_date: Optional[datetime] = None


class TenderProjectCreate(TenderProjectBase):
    pass


class TenderProjectUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=300)
    procurement_type: Optional[str] = Field(None, max_length=50)
    procurement_method: Optional[str] = Field(None, max_length=50)
    dept_id: Optional[str] = Field(None, max_length=100)
    dept_name: Optional[str] = Field(None, max_length=200)
    budget: Optional[Decimal] = None
    control_price: Optional[Decimal] = None
    funding_source: Optional[str] = Field(None, max_length=200)
    bid_amount: Optional[Decimal] = None
    plan_id: Optional[UUID] = None
    announcement_url: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    qualification_requirements: Optional[str] = None
    status: Optional[str] = None
    bidding_start: Optional[datetime] = None
    bidding_end: Optional[datetime] = None
    evaluation_date: Optional[datetime] = None


class TenderProjectResponse(TenderProjectBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime]


class TenderProjectDetailResponse(TenderProjectResponse):
    bids_count: int = 0
    evaluations_count: int = 0


class TenderProjectListResponse(BaseModel):
    projects: list[TenderProjectResponse]
    total: int


class BidBase(BaseModel):
    project_id: UUID
    bidder_id: UUID
    bid_no: str = Field(..., max_length=50)
    bid_price: Optional[Decimal] = None
    technical_score: Optional[float] = None
    commercial_score: Optional[float] = None
    total_score: Optional[float] = None
    ranking: Optional[int] = None
    technical_proposal_url: Optional[str] = Field(None, max_length=500)
    status: str = "submitted"


class BidCreate(BidBase):
    pass


class BidUpdate(BaseModel):
    bid_price: Optional[Decimal] = None
    technical_score: Optional[float] = None
    commercial_score: Optional[float] = None
    total_score: Optional[float] = None
    ranking: Optional[int] = None
    technical_proposal_url: Optional[str] = Field(None, max_length=500)
    status: Optional[str] = None
    compliance_check_passed: Optional[bool] = None


class BidResponse(BidBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    compliance_check_passed: Optional[bool]
    compliance_issues: Optional[list[str]]
    submitted_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class BidListResponse(BaseModel):
    bids: list[BidResponse]
    total: int


class EvaluationBase(BaseModel):
    project_id: UUID
    bid_id: UUID
    evaluation_type: str = "technical"
    technical_score: Optional[float] = None
    commercial_score: Optional[float] = None
    total_score: Optional[float] = None
    ranking: Optional[int] = None
    evaluation_details: Optional[str] = None


class EvaluationCreate(EvaluationBase):
    evaluator_ids: Optional[list[UUID]] = None


class EvaluationResponse(EvaluationBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: str
    verified: bool
    verification_comment: Optional[str]
    evaluation_report_url: Optional[str]
    evaluator_ids: Optional[list[UUID]]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class EvaluationListResponse(BaseModel):
    evaluations: list[EvaluationResponse]
    total: int


class WinningBidCreate(BaseModel):
    project_id: UUID
    bid_id: UUID
    decision_summary: Optional[str] = None


class WinningBidResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    bid_id: UUID
    winning_price: Optional[Decimal]
    decision_summary: Optional[str]
    confirmed: bool
    confirmed_at: Optional[datetime]
    confirmed_by: Optional[str]
    decided_by: Optional[str]
    decided_at: datetime


class ContractBase(BaseModel):
    contract_no: str = Field(..., max_length=50)
    project_id: UUID
    winning_bid_id: Optional[UUID] = None
    bidder_id: UUID
    title: str = Field(..., max_length=300)
    total_price: Optional[Decimal] = None
    sign_date: Optional[datetime] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    payment_terms: Optional[str] = None
    contract_file_url: Optional[str] = Field(None, max_length=500)
    status: str = "draft"


class ContractCreate(ContractBase):
    pass


class ContractUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=300)
    total_price: Optional[Decimal] = None
    sign_date: Optional[datetime] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    payment_terms: Optional[str] = None
    contract_file_url: Optional[str] = Field(None, max_length=500)
    status: Optional[str] = None


class ContractResponse(ContractBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    risk_level: Optional[str]
    risk_issues: Optional[list[str]]
    operator_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class ContractListResponse(BaseModel):
    contracts: list[ContractResponse]
    total: int


class ComplaintBase(BaseModel):
    project_id: Optional[UUID] = None
    title: str = Field(..., max_length=300)
    complaint_type: str = Field(..., max_length=30)
    description: str
    evidence_urls: Optional[list[str]] = None
    complainer_name: Optional[str] = Field(None, max_length=100)
    complainer_phone: Optional[str] = Field(None, max_length=20)


class ComplaintCreate(ComplaintBase):
    pass


class ComplaintUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=300)
    complaint_type: Optional[str] = Field(None, max_length=30)
    description: Optional[str] = None
    evidence_urls: Optional[list[str]] = None
    priority: Optional[str] = None
    status: Optional[str] = None


class ComplaintResponse(ComplaintBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    complaint_no: str
    status: str
    priority: str
    response_content: Optional[str]
    decision_content: Optional[str]
    responded_by: Optional[str]
    responded_at: Optional[datetime]
    decided_by: Optional[str]
    decided_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class ComplaintListResponse(BaseModel):
    complaints: list[ComplaintResponse]
    total: int


class WitnessRecordBase(BaseModel):
    project_id: UUID
    stage: str = Field(..., max_length=50)
    event_type: str = Field(..., max_length=50)
    description: Optional[str] = None
    audio_transcript: Optional[str] = None
    risk_warnings: Optional[str] = None
    sensitive_words_detected: Optional[list[str]] = None
    video_url: Optional[str] = Field(None, max_length=500)


class WitnessRecordCreate(WitnessRecordBase):
    pass


class WitnessRecordResponse(WitnessRecordBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    operator_id: Optional[str]
    created_at: datetime


class WitnessRecordListResponse(BaseModel):
    records: list[WitnessRecordResponse]
    total: int


class VenueSpaceBase(BaseModel):
    venue_name: str = Field(..., max_length=200)
    space_no: str = Field(..., max_length=50)
    floor: Optional[str] = Field(None, max_length=20)
    capacity: Optional[int] = None
    equipment: Optional[str] = None
    hourly_rate: Optional[Decimal] = None
    description: Optional[str] = None
    status: str = "available"


class VenueSpaceCreate(VenueSpaceBase):
    pass


class VenueSpaceUpdate(BaseModel):
    venue_name: Optional[str] = Field(None, max_length=200)
    space_no: Optional[str] = Field(None, max_length=50)
    floor: Optional[str] = Field(None, max_length=20)
    capacity: Optional[int] = None
    equipment: Optional[str] = None
    hourly_rate: Optional[Decimal] = None
    description: Optional[str] = None
    status: Optional[str] = None


class VenueSpaceResponse(VenueSpaceBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime


class VenueSpaceListResponse(BaseModel):
    spaces: list[VenueSpaceResponse]
    total: int


class DashboardStats(BaseModel):
    active_projects: int
    ongoing_bids: int
    pending_evaluations: int
    active_contracts: int
    pending_complaints: int
    total_budget: Decimal
    total_contracts_value: Decimal


class MessageResponse(BaseModel):
    message: str


class ProcurementDecisionRequest(BaseModel):
    decision_content: str


class ProcurementDecisionResponse(BaseModel):
    success: bool
    message: str
    winning_bid_id: UUID
