"""bid_review CRUD —— 全部查询函数带 owner_id 过滤(仓库惯例:router 层从 auth
依赖显式传参,见 contract_price/crud.py;Issue/Baseline 无 owner 列,过滤经
task 联接传导)。供 routers(Task 10)/worker(Task 9)/mcp(Task 11)复用。
"""

from datetime import UTC, datetime

from sqlalchemy import String, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.bid_review.models import (
    BaselinePackage,
    ReviewFeedback,
    ReviewIssue,
    ReviewTask,
    RulePackMeta,
)

# --- ReviewTask --------------------------------------------------------------


def _seq_of(biz_no: str | None) -> int | None:
    """'TBR-YYYYMMDD-NNNN' 尾段序号;None/畸形返回 None(从 0001 重开)。"""
    if not biz_no:
        return None
    parts = biz_no.rsplit("-", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        return None
    return int(parts[1])


async def _next_biz_no(session: AsyncSession) -> str:
    """TBR-{YYYYMMDD}-{seq:04d}:当日 max 尾段+1,零填充;唯一性由迁移索引兜底
    (B1,2026-10-31;存量行 biz_no NULL 不参与 max)。"""
    prefix = f"TBR-{datetime.now(UTC).strftime('%Y%m%d')}-"
    row = await session.execute(select(func.max(ReviewTask.biz_no)).where(ReviewTask.biz_no.like(prefix + "%")))
    seq = _seq_of(row.scalar_one_or_none())
    return f"{prefix}{(seq or 0) + 1:04d}"


async def create_task(
    session: AsyncSession,
    owner_id: str,
    mode: str = "quick",
    *,
    project_name: str | None = None,
    lot_name: str | None = None,
    tender_no: str | None = None,
    prev_task_id: str | None = None,
) -> ReviewTask:
    # 裁定12+14(EAI-CUSTOM 2026-10-31):身份字段=弹窗可选覆盖位;None 落列,
    # worker 抽取回填仅填 NULL 列(人工手填优先,见 worker 回填守卫)。
    # prev_task_id(B10 版本链,spec 2026-11-01 §2.3):路由层先校验存在+属主才传入。
    task = ReviewTask(
        owner_id=owner_id,
        mode=mode,
        biz_no=await _next_biz_no(session),
        project_name=project_name,
        lot_name=lot_name,
        tender_no=tender_no,
        prev_task_id=prev_task_id,
    )
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


async def creator_names(session: AsyncSession, owner_ids: list[str]) -> dict[str, str]:
    """owner_id → 显示名(COALESCE(full_name, username);B1 2026-10-31)。单查询 IN
    非逐任务 N+1;users 表缺失(单测五表子集库)或无匹配行时安全返回 {}——
    TaskOut.created_by_name 保持 None(伪零纪律:查不到不冒充)。"""
    if not owner_ids:
        return {}
    try:
        from app.extensions.models import User

        rows = await session.execute(select(func.cast(User.id, String).label("oid"), func.coalesce(User.full_name, User.username)).where(func.cast(User.id, String).in_(owner_ids)))
        return {oid: name for oid, name in rows.all() if name}
    except SQLAlchemyError:
        return {}


async def set_status(
    session: AsyncSession,
    task: ReviewTask,
    status: str,
    progress: dict | None = None,
    error: str | None = None,
) -> ReviewTask:
    """状态机推进(Task 9 worker 使用);progress/error 传 None 保持原值。"""
    task.status = status
    if status == "done" and task.done_at is None:  # B1:完成时刻一次性落点(幂等)
        task.done_at = datetime.now(UTC)
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
    entity_keys: list | None = None,
    semantic_verdict: str | None = None,
    state: str | None = None,
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
        # L2 P2(EAI-CUSTOM):实体键同样并集去重(排序稳定),与 evidence 共用同一 dirty-commit 窗口
        merged_keys = sorted(set(list(existing.entity_keys or []) + list(entity_keys or [])))
        if len(merged) != len(existing.evidence or []) or merged_keys != list(existing.entity_keys or []):
            existing.evidence = merged  # 重新赋值以标记 JSON 列 dirty
            existing.entity_keys = merged_keys  # 同上
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
        entity_keys=list(entity_keys or []),
        semantic_verdict=semantic_verdict,
        state=state,
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


async def latest_feedback_actions(session: AsyncSession, issue_ids: list[str]) -> dict[str, str]:
    """issue_id → 最新一次复核反馈动作(B2 review_state 投影,routers 映射为复核态)。

    同 created_at 按 id 定序兜底;空入参直接返回空表(列表页无反馈时零查询)。
    """
    if not issue_ids:
        return {}
    result = await session.execute(select(ReviewFeedback).where(ReviewFeedback.issue_id.in_(issue_ids)).order_by(ReviewFeedback.created_at, ReviewFeedback.id))
    latest: dict[str, str] = {}
    for fb in result.scalars():
        latest[fb.issue_id] = fb.action
    return latest


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


async def list_task_feedback(session: AsyncSession, task_id: str, owner_id: str) -> list[ReviewFeedback]:
    """任务级复核动作(feedback 表无 task_id 列,JOIN issues 取归属——不加列不迁移,
    对齐审计③ 2026-11-05)。created_at 升序:复核耗时聚合方按序取首末动作。"""
    rows = (
        (
            await session.execute(
                select(ReviewFeedback).join(ReviewIssue, ReviewFeedback.issue_id == ReviewIssue.id).where(ReviewIssue.task_id == task_id, ReviewFeedback.owner_id == owner_id).order_by(ReviewFeedback.created_at, ReviewFeedback.id)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


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


async def get_or_create_rulepack_meta(session: AsyncSession, name: str, version: str | None = None) -> RulePackMeta:
    """按 name 取/建规则包元数据(规则 enabled 切换端点用,对齐审计⑨ 2026-11-05);
    与 add_rulepack_stats 的 upsert 并存:本函数不带 stats 语义,纯元数据行。"""
    meta = (await session.execute(select(RulePackMeta).where(RulePackMeta.name == name))).scalar_one_or_none()
    if meta is None:
        meta = RulePackMeta(name=name, version=version or "0.0.0", stats={}, enabled=True, rule_overrides={})
        session.add(meta)
        await session.commit()
        await session.refresh(meta)
    return meta
