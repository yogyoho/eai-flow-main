"""Finalize flow — precondition check → compliance → confirm → lock."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession


class FinalizeStatus(StrEnum):
    READY = "ready"
    WARNINGS = "warnings"
    BLOCKED = "blocked"


@dataclass
class PreconditionResult:
    status: FinalizeStatus
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def check_preconditions(
    chapters: list[dict],
    reviews_approved: bool,
    unresolved_comments: int = 0,
    source_coverage: float = 0.8,
    coverage_threshold: float = 0.8,
) -> PreconditionResult:
    """Check finalization preconditions.

    Args:
        chapters: List of {id, title, status} dicts
        reviews_approved: Whether all review gates have passed
        unresolved_comments: Count of unresolved comments
        source_coverage: Fraction of paragraphs with source citations
        coverage_threshold: Minimum acceptable coverage (default 0.8)
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not reviews_approved:
        errors.append("审核尚未全部通过，无法定稿")
        return PreconditionResult(status=FinalizeStatus.BLOCKED, errors=errors)

    incomplete = [c for c in chapters if c["status"] not in ("completed", "approved")]
    if incomplete:
        titles = ", ".join(c["title"] for c in incomplete)
        errors.append(f"以下章节未完成: {titles}")
        return PreconditionResult(status=FinalizeStatus.BLOCKED, errors=errors)

    if unresolved_comments > 0:
        warnings.append(f"存在 {unresolved_comments} 条未解决的评论")

    if source_coverage < coverage_threshold:
        warnings.append(f"溯源覆盖率 {source_coverage:.0%} 低于阈值 {coverage_threshold:.0%}")

    if warnings:
        return PreconditionResult(status=FinalizeStatus.WARNINGS, warnings=warnings)

    return PreconditionResult(status=FinalizeStatus.READY)


async def execute_finalize(
    db: AsyncSession,
    project_id: uuid.UUID,
    exemptions: list[dict] | None = None,
):
    """Execute finalization: lock chapters, create final document."""
    from app.extensions.models import ProjectChapter, ReportProject
    from sqlalchemy import update as sa_update

    project = await db.get(ReportProject, project_id)
    if not project:
        return {"status": "error", "detail": "Project not found"}

    await db.execute(
        sa_update(ProjectChapter)
        .where(ProjectChapter.project_id == project_id)
        .where(ProjectChapter.status.in_(("completed", "approved")))
        .values(status="approved")
    )

    project.status = "completed"

    from app.extensions.models import AIDocument
    final_doc = AIDocument(
        project_id=project_id,
        title=f"{project.name} (定稿)",
        content="",
        doc_type="final",
        status="final",
    )
    db.add(final_doc)
    await db.commit()
    await db.refresh(final_doc)

    return {"status": "ok", "document_id": str(final_doc.id)}
