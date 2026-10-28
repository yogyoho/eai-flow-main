"""bid_review CRUD —— 全部查询函数带 owner_id 过滤(仓库惯例:router 层从 auth
依赖显式传参,见 contract_price/crud.py;Issue/Baseline 无 owner 列,过滤经
task 联接传导)。供 routers(Task 10)/worker(Task 9)/mcp(Task 11)复用。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.bid_review.models import (
    BaselinePackage,
    ReviewFeedback,
    ReviewIssue,
    ReviewTask,
    RulePackMeta,
)

# --- ReviewTask --------------------------------------------------------------


async def create_task(session: AsyncSession, owner_id: str, mode: str = "quick") -> ReviewTask:
    task = ReviewTask(owner_id=owner_id, mode=mode)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def list_tasks(session: AsyncSession, owner_id: str) -> list[ReviewTask]:
    result = await session.execute(select(ReviewTask).where(ReviewTask.owner_id == owner_id).order_by(ReviewTask.created_at.desc(), ReviewTask.id))
    return list(result.scalars().all())


async def get_task(session: AsyncSession, task_id: str, owner_id: str) -> ReviewTask | None:
    result = await session.execute(select(ReviewTask).where(ReviewTask.id == task_id, ReviewTask.owner_id == owner_id))
    return result.scalar_one_or_none()


async def set_status(
    session: AsyncSession,
    task: ReviewTask,
    status: str,
    progress: dict | None = None,
    error: str | None = None,
) -> ReviewTask:
    """状态机推进(Task 9 worker 使用);progress/error 传 None 保持原值。"""
    task.status = status
    if progress is not None:
        task.progress = progress
    if error is not None:
        task.error = error
    await session.commit()
    await session.refresh(task)
    return task


# --- ReviewIssue -------------------------------------------------------------


async def add_issue(
    session: AsyncSession,
    task_id: str,
    owner_id: str,
    rule_id: str,
    layer: str,
    severity: str,
    verdict: str,
    message: str,
    fix: str = "",
    evidence: list | None = None,
    *,
    dedup_key: str,
    clause_id: str | None = None,
    need_human: bool = False,
    confidence: float = 1.0,
) -> ReviewIssue | None:
    """按 (task_id, dedup_key) 去重:已存在则 evidence 并集合并(重复条目跳过),
    不新建行、不覆盖已有字段;task 不属于该 owner 时返回 None。

    dedup_key 为必填参数且不得为空串:空/缺省值若参与查重,两条互不相关问题会
    互相命中("")并触发合并黑洞——第二条的 rule_id/verdict 等字段被静默丢弃。
    故 dedup_key 为空时跳过查重直接新建(评审修复 2026-10-29);正常键由
    rule_runner 产出 ``{rule_id}|-|{message前40字}``。
    """
    task = await get_task(session, task_id, owner_id)
    if task is None:
        return None
    existing = None
    if dedup_key:
        existing = (await session.execute(select(ReviewIssue).where(ReviewIssue.task_id == task_id, ReviewIssue.dedup_key == dedup_key))).scalar_one_or_none()
    if existing is not None:
        merged = list(existing.evidence or [])
        for item in evidence or []:
            if item not in merged:
                merged.append(item)
        if len(merged) != len(existing.evidence or []):
            existing.evidence = merged  # 重新赋值以标记 JSON 列 dirty
            await session.commit()
            await session.refresh(existing)
        return existing
    issue = ReviewIssue(
        task_id=task_id,
        rule_id=rule_id,
        layer=layer,
        severity=severity,
        verdict=verdict,
        message=message,
        fix=fix,
        evidence=list(evidence or []),
        dedup_key=dedup_key,
        clause_id=clause_id,
        need_human=need_human,
        confidence=confidence,
    )
    session.add(issue)
    await session.commit()
    await session.refresh(issue)
    return issue


async def list_issues(session: AsyncSession, task_id: str, owner_id: str) -> list[ReviewIssue]:
    result = await session.execute(select(ReviewIssue).join(ReviewTask, ReviewIssue.task_id == ReviewTask.id).where(ReviewIssue.task_id == task_id, ReviewTask.owner_id == owner_id).order_by(ReviewIssue.created_at, ReviewIssue.id))
    return list(result.scalars().all())


async def get_issue(session: AsyncSession, issue_id: str, owner_id: str) -> ReviewIssue | None:
    result = await session.execute(select(ReviewIssue).join(ReviewTask, ReviewIssue.task_id == ReviewTask.id).where(ReviewIssue.id == issue_id, ReviewTask.owner_id == owner_id))
    return result.scalar_one_or_none()


# --- BaselinePackage ---------------------------------------------------------


async def list_baselines(session: AsyncSession, task_id: str, owner_id: str) -> list[BaselinePackage]:
    result = await session.execute(
        select(BaselinePackage).join(ReviewTask, BaselinePackage.task_id == ReviewTask.id).where(BaselinePackage.task_id == task_id, ReviewTask.owner_id == owner_id).order_by(BaselinePackage.created_at, BaselinePackage.id)
    )
    return list(result.scalars().all())


async def update_baseline(session: AsyncSession, baseline: BaselinePackage, *, confirmed: bool = True) -> BaselinePackage:
    """人工确认门翻转(行对象须先经 list_baselines/get 的 owner 过滤取得)。"""
    baseline.confirmed = confirmed
    await session.commit()
    await session.refresh(baseline)
    return baseline


# --- ReviewFeedback ----------------------------------------------------------


async def record_feedback(
    session: AsyncSession,
    issue_id: str,
    owner_id: str,
    action: str,
    new_severity: str | None = None,
    note: str = "",
) -> ReviewFeedback | None:
    """复核三连(Task 16);issue 不属于该 owner 时返回 None(越权/不存在同一形态)。"""
    issue = await get_issue(session, issue_id, owner_id)
    if issue is None:
        return None
    fb = ReviewFeedback(issue_id=issue_id, owner_id=owner_id, action=action, new_severity=new_severity, note=note)
    session.add(fb)
    await session.commit()
    await session.refresh(fb)
    return fb


# --- RulePackMeta ------------------------------------------------------------


async def add_rulepack_stats(
    session: AsyncSession,
    name: str,
    rule_id: str,
    *,
    version: str | None = None,
    hit: bool = False,
    fp: bool = False,
    adopted: bool = False,
) -> RulePackMeta:
    """按 name upsert 规则包元数据,并为 rule_id 累加 {hit, fp, adopted} 计数。"""
    meta = (await session.execute(select(RulePackMeta).where(RulePackMeta.name == name))).scalar_one_or_none()
    if meta is None:
        meta = RulePackMeta(name=name, version=version or "0.0.0", stats={}, enabled=True)
        session.add(meta)
        await session.flush()
    elif version:
        meta.version = version
    stats = dict(meta.stats or {})
    entry = dict(stats.get(rule_id) or {})
    if hit:
        entry["hit"] = entry.get("hit", 0) + 1
    if fp:
        entry["fp"] = entry.get("fp", 0) + 1
    if adopted:
        entry["adopted"] = entry.get("adopted", 0) + 1
    stats[rule_id] = entry
    meta.stats = stats  # 重新赋值以标记 JSON 列 dirty
    await session.commit()
    await session.refresh(meta)
    return meta
