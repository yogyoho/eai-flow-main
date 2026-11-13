"""bid_write CRUD(批十九 T2)——全部查询带 owner_id 过滤(经 task 联接传导,
与 bid_review/crud.py 同惯例);矩阵行替换式落库(reassemble 幂等:同任务重跑
按 clause_id 全删重建,人工已确认行不重建——见 replace_matrix)。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.bid_write.models import MatrixRow, WriteTask


def _seq_of(biz_no: str | None) -> int | None:
    if not biz_no:
        return None
    parts = biz_no.rsplit("-", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        return None
    return int(parts[1])


async def _next_biz_no(session: AsyncSession) -> str:
    """TBW-{YYYYMMDD}-{seq:04d}(与审查端 TBR 同构,前缀区分)。"""
    prefix = f"TBW-{datetime.now(UTC).strftime('%Y%m%d')}-"
    row = await session.execute(select(func.max(WriteTask.biz_no)).where(WriteTask.biz_no.like(prefix + "%")))
    seq = _seq_of(row.scalar_one_or_none())
    return f"{prefix}{(seq or 0) + 1:04d}"


async def create_task(
    session: AsyncSession,
    owner_id: str,
    *,
    project_name: str | None = None,
    lot_name: str | None = None,
    tender_no: str | None = None,
) -> WriteTask:
    task = WriteTask(
        owner_id=owner_id,
        biz_no=await _next_biz_no(session),
        project_name=project_name,
        lot_name=lot_name,
        tender_no=tender_no,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def list_tasks(session: AsyncSession, owner_id: str) -> list[WriteTask]:
    result = await session.execute(select(WriteTask).where(WriteTask.owner_id == owner_id).order_by(WriteTask.created_at.desc(), WriteTask.id))
    return list(result.scalars().all())


async def get_task(session: AsyncSession, task_id: str, owner_id: str) -> WriteTask | None:
    result = await session.execute(select(WriteTask).where(WriteTask.id == task_id, WriteTask.owner_id == owner_id))
    return result.scalar_one_or_none()


async def set_status(session: AsyncSession, task: WriteTask, status: str, progress: dict | None = None, error: str | None = None) -> WriteTask:
    task.status = status
    if progress is not None:
        task.progress = progress
    if error is not None:
        task.error = error
    await session.commit()
    await session.refresh(task)
    return task


# --- MatrixRow ----------------------------------------------------------------


async def replace_matrix(session: AsyncSession, task_id: str, rows: list[dict]) -> list[MatrixRow]:
    """矩阵全量重挂(幂等):同任务旧行全删重建。人工状态保留面(P1 增量):M0
    无生成下游,重跑=全量重置为 draft/pending(诚实:抽取结果可能已变,旧裁定
    失效;P1 增量重审时按 clause_id 保留 confirmed 行)。"""
    await session.execute(delete(MatrixRow).where(MatrixRow.task_id == task_id))
    objs = [MatrixRow(task_id=task_id, **row) for row in rows]
    session.add_all(objs)
    await session.commit()
    for obj in objs:
        await session.refresh(obj)
    return objs


async def list_matrix(session: AsyncSession, task_id: str, owner_id: str) -> list[MatrixRow]:
    result = await session.execute(select(MatrixRow).join(WriteTask, MatrixRow.task_id == WriteTask.id).where(MatrixRow.task_id == task_id, WriteTask.owner_id == owner_id).order_by(MatrixRow.kind, MatrixRow.clause_id))
    return list(result.scalars().all())


async def get_row(session: AsyncSession, task_id: str, clause_id: str, owner_id: str) -> MatrixRow | None:
    result = await session.execute(select(MatrixRow).join(WriteTask, MatrixRow.task_id == WriteTask.id).where(MatrixRow.task_id == task_id, MatrixRow.clause_id == clause_id, WriteTask.owner_id == owner_id))
    return result.scalar_one_or_none()


# --- SkillRun(批二十 M1-c 断言执行落库)---------------------------------------


async def record_skill_run(session: AsyncSession, task_id: str, owner_id: str, verdict: dict, *, skills=None, schema_version: str = "", blocked: bool = False) -> None:
    """断言执行结果落库(报告 JSON=导出物非真相源,行才是)。owner 过滤经 task
    存在性校验间接传导:调用方须先 get_task(db, task_id, owner_id)(404 面)。"""
    from app.extensions.bid_write.executor.models import SkillRun

    session.add(SkillRun(task_id=task_id, owner_id=owner_id, skills=list(skills) if skills else "ALL", schema_version=schema_version, verdict=verdict, blocked=blocked))
    await session.commit()


async def latest_skill_run(session: AsyncSession, task_id: str, owner_id: str):
    """最近一次执行行(无→None,gaps 断言维度 404 不误伤)。"""
    from app.extensions.bid_write.executor.models import SkillRun

    result = await session.execute(select(SkillRun).join(WriteTask, SkillRun.task_id == WriteTask.id).where(SkillRun.task_id == task_id, WriteTask.owner_id == owner_id).order_by(SkillRun.created_at.desc(), SkillRun.id.desc()).limit(1))
    return result.scalar_one_or_none()
