"""Canonical chapter status state machine (single source of truth).

States: pending → draft → reviewing → approved
              ↘ (Tier-1 direct, no review gate) draft → approved
         reviewing → draft (rejection = event + feedback, not a state)
         approved → draft (post-approval rework, mirrors project re-open)

EAI-CUSTOM: 2026-08-02 single-state consolidation (ADR
docs/superpowers/specs/2026-08-02-writing-project-single-state.md).
Removed legacy states writing/completed/error/rejected/editing:
  - 'completed' splits into 'reviewing' (content done + human confirmed,
    submitted for review) / 'approved' (finalized by finalize_document);
  - 'error' and 'rejected' are events/records, not states.
"""
from __future__ import annotations

from enum import StrEnum


class ChapterStatus(StrEnum):
    PENDING = "pending"
    DRAFT = "draft"
    REVIEWING = "reviewing"
    APPROVED = "approved"


VALID_CHAPTER_TRANSITIONS: dict[str, set[str]] = {
    ChapterStatus.PENDING: {ChapterStatus.DRAFT},
    ChapterStatus.DRAFT: {ChapterStatus.REVIEWING, ChapterStatus.APPROVED},
    ChapterStatus.REVIEWING: {ChapterStatus.DRAFT, ChapterStatus.APPROVED},
    ChapterStatus.APPROVED: {ChapterStatus.DRAFT},
}


def validate_chapter_transition(current: str, target: str) -> str | None:
    """Return error message if transition is invalid, else None.

    Canonical-only — the legacy normalize shim was removed (ADR P5), so legacy
    values are rejected fail-closed.
    """
    if target not in VALID_CHAPTER_TRANSITIONS:
        return f"Unknown chapter status: {target!r}"
    allowed = VALID_CHAPTER_TRANSITIONS.get(current, set())
    if target not in allowed:
        return f"Cannot transition chapter from {current!r} to {target!r}"
    return None
