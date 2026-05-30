from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkflowDefinitionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    report_type: str | None = None
    graph_json: dict = Field(..., description="DAG nodes and edges from React Flow")
    is_template: bool = False


class WorkflowDefinitionUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    report_type: str | None = None
    graph_json: dict | None = None
    is_template: bool | None = None


class WorkflowDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    report_type: str | None = None
    graph_json: dict
    is_template: bool = False
    created_by: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WorkflowDefinitionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    report_type: str | None = None
    is_template: bool = False
    created_at: datetime | None = None


class WorkflowDefinitionListResponse(BaseModel):
    items: list[WorkflowDefinitionListItem] = Field(default_factory=list)
    total: int = 0


class DAGValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WorkflowStartRequest(BaseModel):
    workflow_id: UUID


class WorkflowSignalRequest(BaseModel):
    signal_name: str
    signal_payload: dict | None = None


class ContentSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    chapter_id: UUID
    block_index: int
    source_type: str
    source_ref: str | None = None
    snippet: str | None = None
    confidence: float | None = None
    metadata: dict | None = None
    created_at: datetime | None = None


class ContentSourceListResponse(BaseModel):
    sources: list[ContentSourceOut] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)


class SourceMissingResult(BaseModel):
    block_index: int
    preview: str = ""
