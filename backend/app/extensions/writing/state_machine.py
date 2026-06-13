"""Chapter status state machine.

States: pending → draft → completed → approved
              ↘ error ↗ (retry)
         completed → pending (rejection rollback)
         approved → pending (rejection rollback)
"""
from __future__ import annotations

from enum import StrEnum


class ChapterStatus(StrEnum):
    PENDING = "pending"
    DRAFT = "draft"
    COMPLETED = "completed"
    APPROVED = "approved"
    ERROR = "error"


VALID_CHAPTER_TRANSITIONS: dict[str, set[str]] = {
    ChapterStatus.PENDING: {ChapterStatus.DRAFT, ChapterStatus.ERROR},
    ChapterStatus.DRAFT: {ChapterStatus.COMPLETED, ChapterStatus.PENDING},
    ChapterStatus.COMPLETED: {ChapterStatus.APPROVED, ChapterStatus.PENDING},
    ChapterStatus.APPROVED: {ChapterStatus.PENDING},
    ChapterStatus.ERROR: {ChapterStatus.PENDING},
}


def validate_chapter_transition(current: str, target: str) -> str | None:
    """Return error message if transition is invalid, else None."""
    if target not in VALID_CHAPTER_TRANSITIONS:
        return f"Unknown chapter status: {target!r}"
    allowed = VALID_CHAPTER_TRANSITIONS.get(current, set())
    if target not in allowed:
        return f"Cannot transition chapter from {current!r} to {target!r}"
    return None
