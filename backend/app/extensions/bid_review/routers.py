"""bid_review 工作台 API(Task 10)——8 端点(设计文档 §4.7),挂 gateway
``/api/extensions/bid-review``:

  POST /tasks                  multipart 上传 tender+bid 文档建任务(后台直推 advance)
  GET  /tasks                  任务列表(owner 过滤)
  GET  /tasks/{id}             任务详情(含 progress)
  POST /tasks/{id}/confirm     确认门(仅 UI 用;仅 awaiting_confirm 可确认,否则 409;
                               基线全量 confirmed 并续跑 running)
  GET  /tasks/{id}/issues      任务问题列表(owner 过滤)
  GET  /issues/{id}            问题详情(owner 过滤)
  POST /issues/{id}/feedback   复核反馈(写 ReviewFeedback + RulePackMeta.stats 回流;
                               false_positive 走误报回流 verdict/need_human 落库 + fp_samples)
  GET  /rulepacks              规则包清单(生产规则包 + DB stats)

owner 隔离:模块级 ``current_owner`` 依赖(必须模块级函数,dependency_overrides 才能打桩),
内部与 contract_price/routers.py 同一登录依赖(require_permission),取 bridged
CurrentUser.id 作 owner_id,全列表端点 owner 过滤。
"""

import asyncio
import logging
from datetime import UTC, datetime

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
FP_SAMPLES_CAP = 20  # 误报回流候选滚动上限(Task 16:stats[rule].fp_samples ≤20,最旧先出)


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
    """任务列表(owner 过滤)。micro-A 2026-10-29:每任务附问题计数(ui-spec §3.1
    「指标格数据=GET /tasks 聚合」,替代前端逐任务拉 issues 的 N+1):fatal_unhandled=
    fatal 且未被人工判误报(verdict≠false_positive,误报经 apply_false_positive 落库后
    自然回落;与 TasksView 行级致命数同口径),need_human_count=need_human 旗标计数
    (工作台待人工格口径)。仅本端点聚合填充,单任务端点 None=未统计(禁伪零);数据量小
    逐任务 crud.list_issues 简单聚合。"""
    tasks = await crud.list_tasks(db, owner_id=owner_id)
    items = []
    for t in tasks:
        out = TaskOut.model_validate(t)
        issues = await crud.list_issues(db, task_id=t.id, owner_id=owner_id)
        out.fatal_unhandled = sum(1 for i in issues if i.severity == "fatal" and i.verdict != "false_positive")
        out.need_human_count = sum(1 for i in issues if bool(i.need_human))
        items.append(out)
    return {"items": items}


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task_detail(task_id: str, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.post("/tasks/{task_id}/confirm", response_model=TaskOut)
async def confirm_task(task_id: str, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """确认门(仅 UI 用,MCP 不暴露):仅 awaiting_confirm 可确认(其余状态 409——
    确认门是唯一续跑通道,旁路直投/重复确认一律拒,基线不翻转);基线全量翻转 confirmed
    后续跑 running→det→done(后台 asyncio 任务,独立短会话)。"""
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "awaiting_confirm":
        raise HTTPException(status_code=409, detail=f"任务不在确认门(当前 {task.status}):仅 awaiting_confirm 可确认续跑")
    for b in await crud.list_baselines(db, task_id=task_id, owner_id=owner_id):
        await crud.update_baseline(db, b, confirmed=True)
    if task.status == "awaiting_confirm":
        asyncio.create_task(_resume_after_confirm(task.id, owner_id))
    await db.refresh(task)
    return task


# ── 误报回流(Task 16,工作台与 MCP 共用)──────────────────────────────


def _fp_snapshot(issue) -> dict:
    """误报回流候选快照(脱敏):仅留规则判定面——issue_id/规则/层/严重度 + 标记时间。
    **不带 message**:规则消息模板渲染后携带材料值(报价/最高限价/主体名/资质等级等),
    而该 stats 经 GET /rulepacks 对任何持 system:access 的用户原样返回(含普通 user
    角色),材料摘录一旦入统计即对全体用户可见;也不带 task/owner 归属与 evidence 正文。
    消息正文仍经 owner 过滤的 issues 端点可达,不丢信息;issue_id 是不透明 UUID,取全量
    仍需 owner 过滤 API,不构成泄露面。"""
    return {
        "issue_id": issue.id,
        "rule_id": issue.rule_id,
        "layer": issue.layer,
        "severity": issue.severity,
        "marked_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


async def apply_false_positive(db: AsyncSession, issue):
    """误报回流(Task 16;工作台 feedback 端点与 MCP bid_review_feedback 共用同一实现):
    issue 翻 ``verdict="false_positive"`` 且 ``need_human=False`` 落库(A8:人工回写值仅
    落库,不经 issue-schema.json emission 校验);RulePackMeta.stats[rule].fp+=1;脱敏
    快照追加进 stats[rule].fp_samples(≤FP_SAMPLES_CAP 滚动,最旧先出)。"""
    issue.need_human = False
    issue.verdict = "false_positive"
    await db.commit()
    await db.refresh(issue)
    await crud.add_rulepack_stats(db, RULEPACK_NAME, issue.rule_id, fp=True)
    meta = (await db.execute(select(RulePackMeta).where(RulePackMeta.name == RULEPACK_NAME))).scalar_one_or_none()
    if meta is not None:
        stats = dict(meta.stats or {})
        entry = dict(stats.get(issue.rule_id) or {})
        samples = [s for s in (entry.get("fp_samples") or []) if isinstance(s, dict)]
        samples.append(_fp_snapshot(issue))
        entry["fp_samples"] = samples[-FP_SAMPLES_CAP:]
        stats[issue.rule_id] = entry
        meta.stats = stats  # 重新赋值以标记 JSON 列 dirty
        await db.commit()
        await db.refresh(meta)
    return issue


# ── 问题端点 ──────────────────────────────────────────────────────────


@router.get("/tasks/{task_id}/issues")
async def list_task_issues(task_id: str, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    if await crud.get_task(db, task_id=task_id, owner_id=owner_id) is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    issues = await crud.list_issues(db, task_id=task_id, owner_id=owner_id)
    return {
        "items": [IssueOut.model_validate(i) for i in issues],
        # 汇总分级(A12 T14 集成约束①,与 worker progress.summary 共用 summarize_issues
        # 同一口径):正式违规计数(fatal/major/minor/info)不含 need_human 条目,待人工
        # 单列;条目不删——items 仍全量返回(工作台待人工格与 verdict 过滤消费)。
        "summary": worker.summarize_issues(issues),
    }


@router.get("/issues/{issue_id}", response_model=IssueOut)
async def get_issue_detail(issue_id: str, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    issue = await crud.get_issue(db, issue_id=issue_id, owner_id=owner_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="问题不存在")
    return issue


@router.post("/issues/{issue_id}/feedback", response_model=IssueOut)
async def feedback_issue(issue_id: str, body: FeedbackIn, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """复核反馈:写 ReviewFeedback + RulePackMeta.stats 回流。false_positive 走误报回流
    (apply_false_positive:verdict/need_human 落库 + fp+1 + fp_samples 滚动);confirm→
    adopted+1;severity_change 只落反馈行且允许任意合法档位——人工降级不拦(端点校验只
    拦非法值;模型侧 fatal 降级拦截是 verify 层 normalize_severity 职责)。"""
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
        await apply_false_positive(db, issue)
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
