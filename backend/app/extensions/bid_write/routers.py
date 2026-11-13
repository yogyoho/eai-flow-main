"""bid_write 工作台 API(批十九 T5)——挂 gateway ``/api/extensions/bid-write``:

  POST /tasks                       multipart 上传招标文件建任务(后台直推 advance)
  GET  /tasks                       任务列表(owner 过滤)
  GET  /tasks/{id}                  任务详情(含 progress)
  GET  /tasks/{id}/matrix           响应矩阵行(F1;labels=词汇表回显)
  PATCH /tasks/{id}/matrix/{clause_id}  行级人工卡点(strategy/status/note;
                                    ★行 negative 直通 422;blocked 行未确认前
                                    禁跳 confirmed)
  GET  /tasks/{id}/gaps             缺口三态(F2;M0 素材库缺位→全部「无对应素材」,
                                    诚实伪零,素材六类实体批二十兑现)

owner 隔离:与 bid_review/routers.py 同款模块级 current_owner(require_permission)。
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.bid_review import parse
from app.extensions.bid_write import contracts, crud, schemas, worker
from app.extensions.bid_write.executor.models import SkillRun as _SkillRun  # noqa: F401 — import 注册共享 Base metadata(bug-4303 律)
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extensions/bid-write", tags=["Bid Write"])


async def current_owner(user: CurrentUser = Depends(require_permission("system:access"))) -> str:
    return str(user.id)


def _enqueue(task) -> None:
    """后台直推(模块级,测试打桩点):POST /tasks 返回前起后台 advance。"""
    asyncio.create_task(_advance_background(task.id, task.owner_id))


async def _advance_background(task_id: str, owner_id: str) -> None:
    from app.extensions.database import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        try:
            task = await crud.get_task(db, task_id, owner_id)
            if task is None:
                return
            await worker.advance_write_task(db, task_id, owner_id)
        except Exception as exc:
            logger.exception("bid_write task %s background advance crashed", task_id)
            await worker._infra_fail(task_id, exc, owner_hint=owner_id)


@router.post("/tasks", response_model=schemas.WriteTaskOut)
async def create_task(
    tender_files: list[UploadFile] = File(...),
    project_name: str = Form(""),
    lot_name: str = Form(""),
    tender_no: str = Form(""),
    db: AsyncSession = Depends(get_db),
    owner_id: str = Depends(current_owner),
):
    """创建商务写作任务(仅招标文件;投标稿属审查模块)。上传字节复用 bid_review
    parse.save_raw(raw 不进 DB),worker 解析链同款。空上传 422(FastAPI File 必填)。"""
    task = await crud.create_task(
        db,
        owner_id=owner_id,
        project_name=project_name.strip() or None,
        lot_name=lot_name.strip() or None,
        tender_no=tender_no.strip() or None,
    )
    entries = []
    for f in tender_files:
        entries.append(parse.save_raw(owner_id, task.id, "tender", f.filename or "tender-doc", await f.read()))
    meta = dict(task.engine_meta or {})
    meta["docs"] = entries
    meta["schema_version"] = contracts.SCHEMA_VERSION
    task.engine_meta = meta  # 重新赋值以标记 JSON 列 dirty
    await db.commit()
    await db.refresh(task)
    _enqueue(task)
    return task


@router.get("/tasks")
async def list_tasks(db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    tasks = await crud.list_tasks(db, owner_id=owner_id)
    items = []
    for t in tasks:
        out = schemas.WriteTaskOut.model_validate(t)
        rows = await crud.list_matrix(db, task_id=t.id, owner_id=owner_id)
        out.engine_meta = {**out.engine_meta, "matrix_counts": {"total": len(rows), "star": sum(1 for r in rows if r.star), "blocked": sum(1 for r in rows if r.status == "blocked")}}
        items.append(out)
    return {"items": items}


@router.get("/tasks/{task_id}", response_model=schemas.WriteTaskOut)
async def get_task(task_id: str, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("/tasks/{task_id}/matrix")
async def get_matrix(task_id: str, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    rows = await crud.list_matrix(db, task_id=task_id, owner_id=owner_id)
    return {
        "items": [schemas.MatrixRowOut.model_validate(r) for r in rows],
        "schema_version": contracts.SCHEMA_VERSION,
        "vocab": {"strategies": contracts.MATRIX_STRATEGIES, "statuses": contracts.MATRIX_STATUSES, "kinds": contracts.ROW_KINDS},
    }


@router.patch("/tasks/{task_id}/matrix/{clause_id}")
async def patch_matrix_row(task_id: str, clause_id: str, body: schemas.MatrixRowPatch, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """行级人工卡点(F1 确认面):strategy/status/note/target_section/evidence_refs
    单行推进。校验:① strategy/status 枚举 422;② star 行 negative 必须带 note
    (无理由负偏离 422——规格 SK-RT-005 偏离闭环的前置);③ blocked 行直接
    confirmed 422(解阻须先补 note 再确认?M0 口径:确认即解阻,blocked→confirmed
    合法但必须带 note——低置信行无凭据确认=把裁决推给下游,422)。"""
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    row = await crud.get_row(db, task_id=task_id, clause_id=clause_id, owner_id=owner_id)
    if row is None:
        raise HTTPException(status_code=404, detail="矩阵行不存在")
    if body.strategy is not None and body.strategy not in contracts.MATRIX_STRATEGIES:
        raise HTTPException(status_code=422, detail=f"strategy 非法:{body.strategy}(合法:{contracts.MATRIX_STRATEGIES})")
    if body.status is not None and body.status not in contracts.MATRIX_STATUSES:
        raise HTTPException(status_code=422, detail=f"status 非法:{body.status}(合法:{contracts.MATRIX_STATUSES})")
    if body.strategy == "negative" and row.star and not (body.note or "").strip() and not (row.note or "").strip():
        raise HTTPException(status_code=422, detail="★条款负偏离必须给偏离理由与替代方案(note)")
    if row.status == "blocked" and body.status == "confirmed" and not (body.note or "").strip():
        raise HTTPException(status_code=422, detail="blocked(低置信)行确认须带确认依据(note)")
    if body.strategy is not None:
        row.strategy = body.strategy
    if body.status is not None:
        row.status = body.status
    if body.target_section is not None:
        row.target_section = body.target_section.strip()
    if body.note is not None:
        row.note = body.note
    if body.evidence_refs is not None:
        row.evidence_refs = body.evidence_refs
    await db.commit()
    await db.refresh(row)
    return schemas.MatrixRowOut.model_validate(row)


@router.get("/tasks/{task_id}/gaps")
async def get_gaps(task_id: str, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """缺口三态(F2;M0 素材库缺位→要求面全部「无对应素材」,诚实伪零:
    有且可佐证/有但缺佐证两态在素材六类实体批二十落地后按 entity_ref 反查兑现)。"""
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    rows = await crud.list_matrix(db, task_id=task_id, owner_id=owner_id)
    items = [{"clause_id": r.clause_id, "kind": r.kind, "requirement": r.requirement, "star": r.star, "status": r.status, "material_state": "无对应素材", "evidence_refs": r.evidence_refs} for r in rows if r.kind in ("attachment", "clause")]
    return {"items": items, "summary": {"total": len(items), "material_ready": 0, "pending_note": "素材库 P1 批落地;M0 全部为无对应素材(诚实伪零)"}}
