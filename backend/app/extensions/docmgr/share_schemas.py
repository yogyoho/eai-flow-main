"""Document share schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ShareCreateRequest(BaseModel):
    share_type: str = Field(..., pattern="^(user|department|link)$")
    share_target_id: str | None = None
    permission: str = Field(default="read", pattern="^(read|edit)$")


class ShareResponse(BaseModel):
    id: UUID
    document_id: UUID
    share_type: str
    share_target_id: str | None = None
    share_token: str | None = None
    permission: str
    created_by: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
