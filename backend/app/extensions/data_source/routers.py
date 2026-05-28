"""Data source API router — stub implementation."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/extensions/data-sources", tags=["data-sources"])


class _DataSourceStub(BaseModel):
    id: str
    name: str
    type: str = "database"
    connection_config: dict = {}
    auth_type: str = "none"
    sync_mode: str = "manual"
    sync_config: dict | None = None
    status: str = "disconnected"
    last_sync_at: str | None = None
    created_by: str = ""
    created_at: str = ""
    updated_at: str = ""


class _ListResponse(BaseModel):
    items: list[_DataSourceStub] = []


@router.get("", response_model=_ListResponse)
async def list_data_sources() -> _ListResponse:
    return _ListResponse(items=[])
