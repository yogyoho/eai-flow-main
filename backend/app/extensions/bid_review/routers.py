"""bid_review 工作台 API(Task 10)——8 端点(设计文档 §4.7),挂 gateway
``/api/extensions/bid-review``:

  POST /tasks                  multipart 上传 tender+bid 文档建任务(后台直推 advance)
  GET  /tasks                  任务列表(owner 过滤)
  GET  /tasks/{id}             任务详情(含 progress)
  POST /tasks/{id}/confirm     确认门(仅 UI 用;基线全量 confirmed 并续跑 running)
  GET  /tasks/{id}/issues      任务问题列表(owner 过滤)
  GET  /issues/{id}            问题详情(owner 过滤)
  POST /issues/{id}/feedback   复核反馈(写 ReviewFeedback + RulePackMeta.stats 回流)
  GET  /rulepacks              规则包清单(生产规则包 + DB stats)

owner 隔离:模块级 ``current_owner`` 依赖(必须模块级函数,dependency_overrides 才能打桩),
内部与 contract_price/routers.py 同一登录依赖(require_permission),取 bridged
CurrentUser.id 作 owner_id,全列表端点 owner 过滤。
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.bid_review import crud, worker
from app.extensions.bid_review.models import RulePackMeta
from app.extensions.bid_review.schemas import FeedbackIn, IssueOut, TaskOut
from app.extensions.database import get_db
from app.extensions.schemas import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extensions/bid-review", tags=["Bid Review"])

RULEPACK_NAME = "bid-review-core"


async def current_owner(user: CurrentUser = Depends(require_permission("system:access"))) -> str:
    """owner 隔离依赖(模块级):与 contract_price/routers.py 相同的登录依赖取
    bridged CurrentUser,以其 extensions id 作 owner_id(crud 全函数 owner 过滤)。"""
    return str(user.id)


# ── 后台直推 / 续跑(模块级,测试打桩点)────────────────────────────────


def _enqueue_docs(task, docs: list[dict]) -> None:
    """后台直推(plan Task 10 Step 3):POST /tasks 返回前起后台 advance_task(读已上传
    文档);asyncio.create_task 于请求事件循环内。模块级函数便于测试打桩。"""
    asyncio.create_task(_advance_background(task.id, task.owner_id))


async def _advance_background(task_id: str, owner_id: str) -> None:
    from app.extensions.database import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        try:
            task = await crud.get_task(db, task_id, owner_id)
            if task is None:
                return
            await worker.advance_task(db, task_id, owner_id, docs=worker._load_docs(task), extract_fn=worker._default_extract_fn(), wait_confirm=(task.mode == "deep"))
        except Exception as exc:
            logger.exception("bid_review task %s background advance crashed", task_id)
            await worker._infra_fail(task_id, exc, phase="enqueue")


async def _resume_after_confirm(task_id: str, owner_id: str) -> None:
    """确认门续跑后台包装(独立短会话;模块级便于测试打桩)。"""
    from app.extensions.database import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        try:
            await worker.resume_confirmed(db, task_id, owner_id)
        except Exception as exc:
            logger.exception("bid_review task %s resume crashed", task_id)
            await worker._infra_fail(task_id, exc, phase="resume")


# ── 任务端点 ──────────────────────────────────────────────────────────


@router.post("/tasks", response_model=TaskOut)
async def create_task(
    mode: str = Form("quick"),
    tender_files: list[UploadFile] | None = File(default=None),
    bid_files: list[UploadFile] | None = File(default=None),
    db: AsyncSession = Depends(get_db),
    owner_id: str = Depends(current_owner),
):
    """创建审查任务(multipart 上传 tender+bid 文档)。v1 文档在请求内解码为纯文本落
    engine_meta.docs(worker._load_docs 取数源;PDF/Word 结构化解析缺口见其注释),
    随后后台直推 advance_task(quick 直跑;deep 停确认门)。"""
    if mode not in ("quick", "deep"):
        raise HTTPException(status_code=422, detail="mode 仅支持 quick|deep")
    task = await crud.create_task(db, owner_id=owner_id, mode=mode)
    docs: list[dict] = []
    for f in tender_files or []:
        docs.append({"doc_id": f.filename or "tender-doc", "role": "tender", "text": (await f.read()).decode("utf-8", "replace")})
    for f in bid_files or []:
        docs.append({"doc_id": f.filename or "bid-doc", "role": "bid", "text": (await f.read()).decode("utf-8", "replace")})
    meta = dict(task.engine_meta or {})
    meta["docs"] = docs
    task.engine_meta = meta  # 重新赋值以标记 JSON 列 dirty
    await db.commit()
    await db.refresh(task)
    _enqueue_docs(task, docs)
    return task


@router.get("/tasks")
async def list_tasks(db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    tasks = await crud.list_tasks(db, owner_id=owner_id)
    return {"items": [TaskOut.model_validate(t) for t in tasks]}


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task_detail(task_id: str, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.post("/tasks/{task_id}/confirm", response_model=TaskOut)
async def confirm_task(task_id: str, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """确认门(仅 UI 用,MCP 不暴露):基线全量翻转 confirmed;awaiting_confirm 状态则
    续跑 running→det→done(后台 asyncio 任务,独立短会话)。"""
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    for b in await crud.list_baselines(db, task_id=task_id, owner_id=owner_id):
        await crud.update_baseline(db, b, confirmed=True)
    if task.status == "awaiting_confirm":
        asyncio.create_task(_resume_after_confirm(task.id, owner_id))
    await db.refresh(task)
    return task


# ── 问题端点 ──────────────────────────────────────────────────────────


@router.get("/tasks/{task_id}/issues")
async def list_task_issues(task_id: str, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    if await crud.get_task(db, task_id=task_id, owner_id=owner_id) is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    issues = await crud.list_issues(db, task_id=task_id, owner_id=owner_id)
    return {"items": [IssueOut.model_validate(i) for i in issues]}


@router.get("/issues/{issue_id}", response_model=IssueOut)
async def get_issue_detail(issue_id: str, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    issue = await crud.get_issue(db, issue_id=issue_id, owner_id=owner_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="问题不存在")
    return issue


@router.post("/issues/{issue_id}/feedback", response_model=IssueOut)
async def feedback_issue(issue_id: str, body: FeedbackIn, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """复核反馈:写 ReviewFeedback + RulePackMeta.stats 回流(false_positive→fp+1、
    confirm→adopted+1;severity_change 只落反馈行)。误报回流规则包属 Task 16,此处仅计数。"""
    if body.action not in ("confirm", "false_positive", "severity_change"):
        raise HTTPException(status_code=422, detail="action 仅支持 confirm|false_positive|severity_change")
    if body.action == "severity_change" and body.new_severity not in ("fatal", "major", "minor", "info"):
        raise HTTPException(status_code=422, detail="new_severity 仅支持 fatal|major|minor|info")
    issue = await crud.get_issue(db, issue_id=issue_id, owner_id=owner_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="问题不存在")
    fb = await crud.record_feedback(db, issue_id=issue_id, owner_id=owner_id, action=body.action, new_severity=body.new_severity, note=body.note)
    if fb is None:
        raise HTTPException(status_code=404, detail="问题不存在")
    if body.action == "false_positive":
        await crud.add_rulepack_stats(db, RULEPACK_NAME, issue.rule_id, fp=True)
    elif body.action == "confirm":
        await crud.add_rulepack_stats(db, RULEPACK_NAME, issue.rule_id, adopted=True)
    await db.refresh(issue)
    return issue


# ── 规则包端点 ────────────────────────────────────────────────────────


@router.get("/rulepacks")
async def list_rulepacks(db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """规则包清单:加载生产规则包(engine/rulepacks/bid-review-core)+ DB stats 覆盖。"""
    pack = worker.load_rulepack(worker.RULEPACK_PATH)
    meta = (await db.execute(select(RulePackMeta).where(RulePackMeta.name == pack.name))).scalar_one_or_none()
    return {
        "items": [
            {
                "name": pack.name,
                "version": pack.version,
                "rule_count": len(pack.rules),
                "rules": [{"id": r.id, "name": r.name, "layer": r.layer, "severity": r.severity, "type": r.type} for r in pack.rules],
                "stats": dict(meta.stats or {}) if meta else {},
                "enabled": bool(meta.enabled) if meta else True,
            }
        ]
    }
