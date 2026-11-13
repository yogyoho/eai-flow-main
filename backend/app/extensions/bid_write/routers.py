"""bid_write 工作台 API(批十九 T5)——挂 gateway ``/api/extensions/bid-write``:

  POST /tasks                       multipart 上传招标文件建任务(后台直推 advance)
  GET  /tasks                       任务列表(owner 过滤)
  GET  /tasks/{id}                  任务详情(含 progress)
  GET  /tasks/{id}/matrix           响应矩阵行(F1;labels=词汇表回显)
  PATCH /tasks/{id}/matrix/{clause_id}  行级人工卡点(strategy/status/note;
                                    ★行 negative 直通 422;blocked 行未确认前
                                    禁跳 confirmed)
  GET  /tasks/{id}/gaps             缺口三态(F2;M0 素材库缺位→全部「无对应素材」,
                                    诚实伪零,素材六类实体批二十兑现)+断言维度
                                    (M1-c:最近执行行 pending/skipped/门禁裁决)

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
    有且可佐证/有但缺佐证两态在素材六类实体批二十落地后按 entity_ref 反查兑现)
    + 断言维度(批二十 M1-c):最近一次执行行的待补清单/SKIPPED 注记/门禁裁决;
    未执行过断言=断言维度 null(不造空绿)。"""
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    rows = await crud.list_matrix(db, task_id=task_id, owner_id=owner_id)
    # 批廿二 P1-α:素材三态兑现——attachment 行与 owner 素材库做名归一包含匹配
    # (att 行 requirement=「no=.. name=.. clause=..」拼接摘录,故用包含而非全等;
    # 与 attachment_index 名归一同律);verifiable=bool(evidence_refs) 派生;
    # clause 行素材不适用(material_state=null)。
    ents = await crud.list_material(db, owner_id)

    def _norm(s: str) -> str:
        return "".join(str(s or "").split()).lower()

    def _state(requirement: str):
        req = _norm(requirement)
        for e in ents:
            n = _norm(e.name)
            if n and (n in req or req in n):
                return ("有且可佐证" if e.evidence_refs else "有但缺佐证"), f"ent:{e.id}"
        return "无对应素材", None

    items = []
    ready = 0
    for r in rows:
        if r.kind not in ("attachment", "clause"):
            continue
        if r.kind == "attachment":
            state, ref = _state(r.requirement)
            ready += state == "有且可佐证"
        else:
            state, ref = None, None
        items.append({"clause_id": r.clause_id, "kind": r.kind, "requirement": r.requirement, "star": r.star, "status": r.status, "material_state": state, "entity_ref": ref, "evidence_refs": r.evidence_refs})

    from app.extensions.bid_write.executor import report as exec_report

    run = await crud.latest_skill_run(db, task_id=task_id, owner_id=owner_id)
    assertions = None
    if run is not None:
        results = (run.verdict or {}).get("results") or []
        assertions = {
            "run_at": run.created_at.isoformat() if run.created_at else None,
            "skills": run.skills,
            "schema_version": run.schema_version,
            "blocked": run.blocked,
            "pending": exec_report.pending_from(results),
            "skipped": exec_report.skipped_from(results),
        }
    att = [i for i in items if i["kind"] == "attachment"]
    return {
        "items": items,
        "summary": {
            "total": len(items),
            "material_ready": ready,
            "material_missing": sum(1 for i in att if i["material_state"] == "无对应素材"),
            "material_unverified": sum(1 for i in att if i["material_state"] == "有但缺佐证"),
            "pending_note": "素材三态=有且可佐证/有但缺佐证/无对应素材(P1-α 兑现;素材库 /materials 维护)",
        },
        "assertions": assertions,
    }


@router.get("/registry")
async def get_assertion_registry(_owner_id: str = Depends(current_owner)):
    """断言注册表只读投影(写作前端「断言注册表」页):p0.yaml 加载期校验后的
    AssertionDef/levels/schema_version。静态内容禁热改;不返回任何可写句柄。"""
    from dataclasses import asdict

    from app.extensions.bid_write.executor import load_registry

    registry = load_registry()
    return {
        "schema_version": registry.schema_version,
        "levels": registry.levels,
        "items": [asdict(item) for item in registry.assertions],
    }


@router.post("/tasks/{task_id}/generate")
async def generate_task(task_id: str, body: schemas.GenerateKnobs | None = None, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """批廿一 M2:装配生成+断言/规则预审查+导出门禁+skill_run 落库。body 旋钮
    合并进 meta.knobs(None 键不覆盖);409=矩阵未就绪面。"""
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "matrix_ready":
        raise HTTPException(status_code=409, detail=f"矩阵未就绪(status={task.status})")
    if body is not None:
        meta = dict(task.engine_meta or {})
        knobs = dict(meta.get("knobs") or {})
        knobs.update({k: v for k, v in body.model_dump().items() if v is not None})
        meta["knobs"] = knobs
        task.engine_meta = meta
        await db.commit()
        await db.refresh(task)
    export = await worker.generate_and_record(db, task, owner_id)
    return {"verdict": export, "blocked": export["blocked"], "biz_no": task.biz_no, "status": task.status}


@router.post("/tasks/{task_id}/export-precheck")
async def export_precheck(task_id: str, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """批廿一 M2:导出前置校验只读重算(D0 断言+L1 fatal det 规则层→blocked/
    reasons/水印恒加);零落库无副作用。"""
    from app.extensions.bid_write.precheck import run_export_gate

    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "matrix_ready":
        raise HTTPException(status_code=409, detail=f"矩阵未就绪(status={task.status})")
    ctx = await worker.build_task_ctx(db, task, owner_id)
    return await run_export_gate(ctx)


# ── 素材库六类实体(F2/P1-α 批廿二)────────────────────────────────────────


def _material_out(r) -> dict:
    return {"id": r.id, "entity_type": r.entity_type, "name": r.name, "fields": r.fields or {}, "evidence_refs": r.evidence_refs or [], "verifiable": bool(r.evidence_refs), "created_at": r.created_at.isoformat() if r.created_at else None}


@router.get("/materials")
async def list_materials(entity_type: str | None = None, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """owner 素材清单(可选类型过滤);verifiable=派生 bool(evidence_refs)。"""
    rows = await crud.list_material(db, owner_id, entity_type)
    return {"items": [_material_out(r) for r in rows]}


@router.post("/materials")
async def create_material(body: schemas.MaterialIn, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    try:
        row = await crud.create_material(db, owner_id, body.entity_type, body.name, fields=body.fields, evidence_refs=body.evidence_refs)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _material_out(row)


@router.patch("/materials/{material_id}")
async def patch_material(material_id: str, body: schemas.MaterialPatch, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    row = await crud.update_material(db, material_id, owner_id, name=body.name, fields=body.fields, evidence_refs=body.evidence_refs)
    if row is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    return _material_out(row)


@router.delete("/materials/{material_id}")
async def delete_material(material_id: str, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    if not await crud.delete_material(db, material_id, owner_id):
        raise HTTPException(status_code=404, detail="素材不存在")
    return {"deleted": True}


@router.get("/materials/profile")
async def get_material_profile(db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    prof = await crud.get_profile(db, owner_id)
    return {"profile": dict(prof.profile or {}) if prof is not None else {}}


@router.put("/materials/profile")
async def put_material_profile(body: schemas.ProfileIn, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    prof = await crud.upsert_profile(db, owner_id, body.profile)
    return {"profile": dict(prof.profile or {})}


# ── project.policy.* 配置面(P1-β 批廿三;owner 单例,镜像 profile 律)────────


@router.get("/policy")
async def get_policy(db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """owner policy 配置(缺→{} =零 policy 现行为)。"""
    return {"policy": await crud.get_policy(db, owner_id)}


@router.put("/policy")
async def put_policy(body: schemas.PolicyBody, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """合并语义(只改传入键);键白名单/税率越界 422(pydantic extra=forbid+ge/le)。"""
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    policy = await crud.upsert_policy(db, owner_id, patch)
    return {"policy": policy}


# ── 埋点六指标(P1-β 批廿三;spec §3)──────────────────────────────────────


@router.get("/tasks/{task_id}/metrics")
async def get_task_metrics(task_id: str, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """最近一次执行的埋点面;未执行过=null(不造空绿,同 gaps 断言维度口径)。"""
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    run = await crud.latest_skill_run(db, task_id=task_id, owner_id=owner_id)
    return {
        "metrics": (run.verdict or {}).get("metrics") if run is not None else None,
        "run_at": run.created_at.isoformat() if run is not None and run.created_at else None,
    }


@router.get("/metrics")
async def get_metrics_aggregate(db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """owner 聚合(P1-β):runs/latency p95·median/断言通过率均值/D0·D1 总计;
    取样窗口=最近 100 run;无 run 诚实零形(runs=0 余 null)。"""
    import math

    runs = await crud.list_skill_runs(db, owner_id)
    metrics = [(r.verdict or {}).get("metrics") or {} for r in runs]
    lat = sorted(m["latency_ms"] for m in metrics if isinstance(m.get("latency_ms"), int))
    rates = [m["assertion_pass_rate"] for m in metrics if m.get("assertion_pass_rate") is not None]

    def _pct(seq: list, q: float):
        if not seq:
            return None
        return seq[max(0, math.ceil(q * len(seq)) - 1)]

    return {
        "runs": len(runs),
        "latency_p95_ms": _pct(lat, 0.95),
        "latency_median_ms": _pct(lat, 0.5),
        "assertion_pass_rate_mean": round(sum(rates) / len(rates), 4) if rates else None,
        "d0_total": sum(m.get("d0_count") or 0 for m in metrics),
        "d1_total": sum(m.get("d1_count") or 0 for m in metrics),
    }
