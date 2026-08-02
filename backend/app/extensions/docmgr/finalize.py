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

    incomplete = [c for c in chapters if c["status"] not in ("reviewing", "approved")]  # EAI-CUSTOM: canonical (ADR 2026-08-02)
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
    """Execute finalization: merge chapters, create final document, lock chapters.

    Returns the merged final document with all chapter content assembled in
    sort_order, not an empty shell.
    """
    from sqlalchemy import func as _func, select, update as sa_update
    from app.extensions.models import AIDocument, Folder, ProjectChapter, ReportProject

    project = await db.get(ReportProject, project_id)
    if not project:
        return {"status": "error", "detail": "Project not found"}

    # ── Merge chapter content ──
    ch_result = await db.execute(
        select(ProjectChapter)
        .where(ProjectChapter.project_id == project_id)
        .where(ProjectChapter.status.in_(("reviewing", "approved")))  # EAI-CUSTOM: canonical (ADR 2026-08-02)
        .where(ProjectChapter.content.isnot(None))
        .where(_func.length(ProjectChapter.content) > 0)
        .order_by(ProjectChapter.sort_order)
    )
    chapters = ch_result.scalars().all()

    report_type_label = (getattr(project, "report_type", None) or "报告")
    _REPORT_TYPE_LABELS: dict[str, str] = {
        "safety_assessment": "安全评价报告",
        "environmental_impact": "环境影响报告",
        "fire_protection": "消防设计报告",
        "geological_report": "地质勘查报告",
        "coal_eia": "煤炭环评报告",
    }
    type_suffix = _REPORT_TYPE_LABELS.get(report_type_label, report_type_label)
    title = f"{project.name}_{type_suffix}"

    if chapters:
        parts = [f"# {title}\n\n"]
        for ch in chapters:
            parts.append(f"## {ch.title}\n\n{ch.content or ''}\n\n")
        merged_content = "".join(parts)
    else:
        merged_content = ""

    # ── Resolve or create project folder ──
    proj_folder_id: uuid.UUID | None = None
    pfx_result = await db.execute(
        select(Folder.id)
        .where(Folder.project_id == project_id)
        .where(Folder.parent_id.is_(None))
        .limit(1)
    )
    pfx_row = pfx_result.first()
    if pfx_row:
        proj_folder_id = pfx_row[0]
    else:
        # Resolve owner from project members
        from app.extensions.models import ProjectMember
        pm_result = await db.execute(
            select(ProjectMember.user_id).where(
                ProjectMember.project_id == project_id,
                ProjectMember.role == "owner",
            ).limit(1)
        )
        owner_row = pm_result.first()
        owner_id = owner_row[0] if owner_row else uuid.UUID(int=0)
        pfx = Folder(
            name=project.name,
            owner_id=owner_id,
            project_id=project_id,
            parent_id=None,
        )
        db.add(pfx)
        await db.flush()
        proj_folder_id = pfx.id

    # ── Create final document with merged content ──
    final_doc = AIDocument(
        user_id=owner_id if chapters else uuid.UUID(int=0),
        project_id=project_id,
        folder_id=proj_folder_id,
        title=title,
        content=merged_content,
        folder="项目文件夹",
        doc_type="final",
        status="final",
    )
    db.add(final_doc)

    # ── Lock all completed/approved chapters to approved ──
    await db.execute(
        sa_update(ProjectChapter)
        .where(ProjectChapter.project_id == project_id)
        .where(ProjectChapter.status.in_(("reviewing", "approved")))  # EAI-CUSTOM: canonical (ADR 2026-08-02)
        .values(status="approved")
    )

    # ── Mark project as approved (canonical, ADR 2026-08-02) ──
    project.status = "approved"

    await db.commit()
    await db.refresh(final_doc)

    return {
        "status": "ok",
        "document_id": str(final_doc.id),
        "title": title,
        "chapter_count": len(chapters),
    }
