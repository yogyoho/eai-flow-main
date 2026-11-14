"""bid_write CRUD(批十九 T2)——全部查询带 owner_id 过滤(经 task 联接传导,
与 bid_review/crud.py 同惯例);矩阵行替换式落库(reassemble 幂等:同任务重跑
按 clause_id 全删重建,人工已确认行不重建——见 replace_matrix)。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.bid_write.models import MatrixRow, WriteTask

if TYPE_CHECKING:
    from app.extensions.bid_write.models import TaskDocument


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

    session.add(SkillRun(task_id=task_id, owner_id=owner_id, skills=",".join(skills) if skills else "ALL", schema_version=schema_version, verdict=verdict, blocked=blocked))
    await session.commit()


async def latest_skill_run(session: AsyncSession, task_id: str, owner_id: str):
    """最近一次执行行(无→None,gaps 断言维度 404 不误伤)。"""
    from app.extensions.bid_write.executor.models import SkillRun

    result = await session.execute(select(SkillRun).join(WriteTask, SkillRun.task_id == WriteTask.id).where(SkillRun.task_id == task_id, WriteTask.owner_id == owner_id).order_by(SkillRun.created_at.desc(), SkillRun.id.desc()).limit(1))
    return result.scalar_one_or_none()


async def list_skill_runs(session: AsyncSession, owner_id: str, limit: int = 100) -> list:
    """owner 全任务 skill_runs 倒序(owner 隔离经 task join;批廿三 P1-β
    /metrics 聚合端点消费,取样窗口 limit)。"""
    from app.extensions.bid_write.executor.models import SkillRun

    stmt = select(SkillRun).join(WriteTask, SkillRun.task_id == WriteTask.id).where(WriteTask.owner_id == owner_id).order_by(SkillRun.created_at.desc(), SkillRun.id.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars())


# ── 素材库六类实体(F2/P1-α 批廿二)────────────────────────────────────────


async def create_material(session: AsyncSession, owner_id: str, entity_type: str, name: str, fields: dict | None = None, evidence_refs: list | None = None):
    """新建素材实体;entity_type 非六类→ValueError(routers 转 422)。"""
    from app.extensions.bid_write import contracts

    if entity_type not in contracts.MATERIAL_ENTITY_TYPES:
        raise ValueError(f"非法素材类型: {entity_type}(合法={','.join(contracts.MATERIAL_ENTITY_TYPES)})")
    from app.extensions.bid_write.models import MaterialEntity

    row = MaterialEntity(owner_id=owner_id, entity_type=entity_type, name=name, fields=dict(fields or {}), evidence_refs=list(evidence_refs or []))
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_material(session: AsyncSession, owner_id: str, entity_type: str | None = None):
    """owner 素材清单(可选类型过滤;名归一匹配在消费侧做,crud 保持薄)。"""
    from sqlalchemy import select

    from app.extensions.bid_write.models import MaterialEntity

    stmt = select(MaterialEntity).where(MaterialEntity.owner_id == owner_id).order_by(MaterialEntity.created_at)
    if entity_type:
        stmt = stmt.where(MaterialEntity.entity_type == entity_type)
    result = await session.execute(stmt)
    return list(result.scalars())


async def get_material(session: AsyncSession, material_id: str, owner_id: str):
    from app.extensions.bid_write.models import MaterialEntity

    result = await session.execute(select(MaterialEntity).where(MaterialEntity.id == material_id, MaterialEntity.owner_id == owner_id))
    return result.scalar_one_or_none()


async def update_material(session: AsyncSession, material_id: str, owner_id: str, *, name: str | None = None, fields: dict | None = None, evidence_refs: list | None = None):
    """部分更新(404 面=None;name/fields/evidence_refs 只在显式传时覆盖)。"""
    row = await get_material(session, material_id, owner_id)
    if row is None:
        return None
    if name is not None:
        row.name = name
    if fields is not None:
        row.fields = dict(fields)
    if evidence_refs is not None:
        row.evidence_refs = list(evidence_refs)
    await session.commit()
    await session.refresh(row)
    return row


async def delete_material(session: AsyncSession, material_id: str, owner_id: str) -> bool:
    row = await get_material(session, material_id, owner_id)
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def get_profile(session: AsyncSession, owner_id: str):
    from app.extensions.bid_write.models import MaterialProfile

    result = await session.execute(select(MaterialProfile).where(MaterialProfile.owner_id == owner_id))
    return result.scalar_one_or_none()


async def upsert_profile(session: AsyncSession, owner_id: str, profile: dict):
    """投标主体 profile 单例 upsert(PUT 幂等面)。"""
    from app.extensions.bid_write.models import MaterialProfile

    row = await get_profile(session, owner_id)
    if row is None:
        row = MaterialProfile(owner_id=owner_id, profile=dict(profile or {}))
        session.add(row)
    else:
        row.profile = dict(profile or {})
    await session.commit()
    await session.refresh(row)
    return row


async def collect_material(session: AsyncSession, owner_id: str) -> dict:
    """owner 素材库→build_ctx material 形(entities 键=ent:<id>;bidder_profile 单例
    缺→{};price_history=performance 实体 fields.amount 派生)。verifiable 不落库
    =bool(evidence_refs) 派生,消费侧(gaps/生成面)同口径。"""
    rows = await list_material(session, owner_id)
    prof = await get_profile(session, owner_id)
    return {
        "entities": {f"ent:{r.id}": {"type": r.entity_type, "name": r.name, "fields": dict(r.fields or {}), "evidence_refs": list(r.evidence_refs or [])} for r in rows},
        "bidder_profile": dict(prof.profile or {}) if prof is not None else {},
        "price_history": [{"project": r.name, "amount": (r.fields or {}).get("amount")} for r in rows if r.entity_type == "performance" and (r.fields or {}).get("amount") is not None],
    }


async def get_policy(session: AsyncSession, owner_id: str) -> dict:
    """project.policy.* 配置(owner 单例;缺→{} =零 policy 现行为)。"""
    from app.extensions.bid_write.models import BidWritePolicy

    row = await session.get(BidWritePolicy, owner_id)
    return dict(row.policy or {}) if row is not None else {}


async def upsert_policy(session: AsyncSession, owner_id: str, patch: dict) -> dict:
    """合并语义 upsert(只改传入键不清他键);键白名单校验在 schemas
    (PolicyBody extra=forbid)。返回合并后全形。"""
    from app.extensions.bid_write.models import BidWritePolicy

    row = await session.get(BidWritePolicy, owner_id)
    if row is None:
        row = BidWritePolicy(owner_id=owner_id, policy=dict(patch or {}))
        session.add(row)
    else:
        row.policy = {**dict(row.policy or {}), **dict(patch or {})}
    await session.commit()
    await session.refresh(row)
    return dict(row.policy or {})


async def get_document(session: AsyncSession, task_id: str, owner_id: str) -> TaskDocument | None:
    """正文 AST 读取(批廿八 M2;owner 过滤同矩阵行)。未保存过→None。"""
    from app.extensions.bid_write.models import TaskDocument

    res = await session.execute(select(TaskDocument).where(TaskDocument.task_id == task_id, TaskDocument.owner_id == owner_id))
    return res.scalar_one_or_none()


async def put_document(session: AsyncSession, task_id: str, owner_id: str, *, ast: dict, schema_version: str) -> TaskDocument:
    """正文 AST 保存(批廿八 M2;PUT 幂等全量,首存建行重存覆盖)。调用方
    (routers)先 get_task 卡 owner——越 owner 的 task 在路由层 404,不进本函数。"""
    from app.extensions.bid_write.models import TaskDocument

    doc = await get_document(session, task_id, owner_id)
    if doc is None:
        doc = TaskDocument(task_id=task_id, owner_id=owner_id, ast=ast, schema_version=schema_version)
        session.add(doc)
    else:
        doc.ast = ast
        doc.schema_version = schema_version
    await session.commit()
    await session.refresh(doc)
    return doc
