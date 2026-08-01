"""Collab Workspace — 分层 Tier 派生。

EAI-CUSTOM: 全新模块。信号自动升高（粘性单向），recompute_tier 从写端点幂等调用，不加调度器。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import CollabMember, CollabProject, CollabSection

# 信号常量
S_SECOND_PARTICIPANT = "second_participant"
S_RELEASE = "release"
S_COMPLIANCE = "compliance_pin"
S_SECTION_COUNT = "section_count"

# 规则阈值（spec §6.1）
QUICKDOC_HEADING_THRESHOLD = 8
QUICKDOC_CHAR_THRESHOLD = 5000
REPORT_SECTION_THRESHOLD = 6


def _count_headings(markdown: str) -> int:
    """统计 ## 二级标题数（quickdoc S4 信号）。"""
    if not markdown:
        return 0
    count = 0
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("## ") or stripped == "##":
            count += 1
    return count


async def recompute_tier(db: AsyncSession, project: CollabProject, *, markdown: str | None = None) -> str:
    """根据信号派生 tier_state。粘性单向：升了不降级。返回新 tier。

    从写端点调用（成员增删 / release / 章节创建 / 文档保存）。不加调度器。
    """
    signals = list(project.tier_signals or [])
    current = project.tier_state or "tier1"
    # EAI-CUSTOM: DB 列 TIMESTAMP WITHOUT TIME ZONE，用 naive UTC
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    async def _escalate(to: str, signal: str) -> None:
        nonlocal current
        if _rank(to) > _rank(current):
            current = to
            project.tier_state = to
            project.escalated_at = now
            signals.append({"signal": signal, "at": now.isoformat(), "to": to})

    # S1: 第二参与者（成员 ≥2 或任一 agent 成员）→ T2
    member_count = await db.scalar(
        select(func.count(CollabMember.id)).where(CollabMember.project_id == project.id)
    ) or 0
    if member_count >= 2:
        await _escalate("tier2", S_SECOND_PARTICIPANT)

    # S3: 合规钉 → T3
    if project.compliance_pin:
        await _escalate("tier3", S_COMPLIANCE)

    # S4: 章节数 → T2（quickdoc 用标题/字符；report 用章节行数）
    if project.kind == "quickdoc":
        if markdown:
            if _count_headings(markdown) >= QUICKDOC_HEADING_THRESHOLD or len(markdown) >= QUICKDOC_CHAR_THRESHOLD:
                await _escalate("tier2", S_SECTION_COUNT)
    else:
        section_count = await db.scalar(
            select(func.count(CollabSection.id)).where(
                CollabSection.project_id == project.id,
                CollabSection.status != "deleted",
            )
        ) or 0
        if section_count >= REPORT_SECTION_THRESHOLD:
            await _escalate("tier2", S_SECTION_COUNT)

    # S2: release（由 POST /release 端点显式触发，这里不检查 status 以避免循环）
    if project.status == "submitted_for_release":
        await _escalate("tier3", S_RELEASE)

    project.tier_signals = signals
    return current


def _rank(tier: str) -> int:
    return {"tier1": 1, "tier2": 2, "tier3": 3}.get(tier, 1)
