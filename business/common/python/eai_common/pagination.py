"""Shared Pydantic pagination utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Generic, TypeVar

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from uuid import UUID

T = TypeVar("T")


class PageParams(BaseModel):
    """Standard pagination parameters."""

    skip: int = Field(0, ge=0)
    limit: int = Field(20, ge=1, le=100)
    keyword: str | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard paginated list response."""

    items: list[T]
    total: int
    skip: int
    limit: int
