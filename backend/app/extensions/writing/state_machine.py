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

# EAI-CUSTOM migration shim: legacy chapter statuses -> canonical.
# Kept only until the P4 switch removes legacy producers; do not grow this map.
LEGACY_CHAPTER_STATUS_MAP: dict[str, str] = {
    "writing": "draft",
    "editing": "draft",
    "in_progress": "draft",
    "rejected": "draft",
    "error": "draft",
    "review": "reviewing",
    "in_review": "reviewing",
    "reviewed": "approved",
    "signed": "approved",
    "completed": "reviewing",  # content-done-not-submitted; finalized -> approved
}


def normalize_chapter_status(value: str) -> str:
    """Map a legacy chapter status to the canonical set.

    Unknown values are returned unchanged so callers can reject them against
    VALID_CHAPTER_TRANSITIONS (no silent default).
    """
    if value in VALID_CHAPTER_TRANSITIONS:
        return value
    return LEGACY_CHAPTER_STATUS_MAP.get(value, value)


def validate_chapter_transition(current: str, target: str) -> str | None:
    """Return error message if transition is invalid, else None.

    Both current and target are normalized to canonical values, so the machine
    accepts legacy producers until the P4 switch removes them.
    """
    cur = normalize_chapter_status(current)
    tgt = normalize_chapter_status(target)
    if tgt not in VALID_CHAPTER_TRANSITIONS:
        return f"Unknown chapter status: {target!r}"
    allowed = VALID_CHAPTER_TRANSITIONS.get(cur, set())
    if tgt not in allowed:
        return f"Cannot transition chapter from {current!r} to {target!r}"
    return None
