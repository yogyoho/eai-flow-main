"""bid_review 工作台 API(Task 10)——8 端点(设计文档 §4.7),挂 gateway
``/api/extensions/bid-review``:

  POST /tasks                  multipart 上传 tender+bid 文档建任务(后台直推 advance)
  GET  /tasks                  任务列表(owner 过滤)
  GET  /tasks/{id}             任务详情(含 progress)
  POST /tasks/{id}/confirm     确认门(仅 UI 用;仅 awaiting_confirm 可确认,否则 409;
                               基线全量 confirmed 并续跑 running)
  GET  /tasks/{id}/docs/{doc_id}/content   溯源定位窗口(EAI-CUSTOM 2026-10-30:?quote=
                               文本片段或 ?page= 页码 → 命中页/±10段窗口,整本不回传——D6;
                               未命中 404「未定位到原文」,前端如实呈现)
  GET  /tasks/{id}/docs/{doc_id}/assets/{asset_id}  原图取数(仅限该文档 segments 引用
                               的 asset,FileResponse)
  GET  /tasks/{id}/issues      任务问题列表(owner 过滤)
  GET  /issues/{id}            问题详情(owner 过滤)
  POST /issues/{id}/feedback   复核反馈(写 ReviewFeedback + RulePackMeta.stats 回流;
                               false_positive 走误报回流 verdict/need_human 落库 + fp_samples)
  GET  /tasks/{id}/report      审查报告导出 ?format=md|html(Task 21;首行免责声明+可提交判定
                               提示行+severity 分节;html=M4+ 挂账兑付 2026-11-05,未知格式 422)
  GET  /rulepacks              规则包清单(生产规则包 + DB stats)

owner 隔离:模块级 ``current_owner`` 依赖(必须模块级函数,dependency_overrides 才能打桩),
内部与 contract_price/routers.py 同一登录依赖(require_permission),取 bridged
CurrentUser.id 作 owner_id,全列表端点 owner 过滤。
"""

import asyncio
import html
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.bid_review import crud, parse, worker
from app.extensions.bid_review.engine.attachments import build_checklist
from app.extensions.bid_review.engine.extract import apply_adjudications, compute_score_coverage, derive_score_risk, detect_conflicts, deviation_counts
from app.extensions.bid_review.engine.labels import FIELD_LABELS
from app.extensions.bid_review.models import BaselinePackage, ReviewFeedback, ReviewIssue, RulePackMeta
from app.extensions.bid_review.schemas import AdjudicateIn, FeedbackIn, IssueOut, RuleEnabledIn, TaskOut
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
    project_name: str = Form(""),
    lot_name: str = Form(""),
    tender_no: str = Form(""),
    prev_task_id: str = Form(""),
    db: AsyncSession = Depends(get_db),
    owner_id: str = Depends(current_owner),
):
    """创建审查任务(multipart 上传 tender+bid 文档)。EAI-CUSTOM(2026-10-30 解析层,
    spec §2):上传字节快速落盘 raw/(原始字节不进 DB),engine_meta.docs 只存清单
    (doc_id/role/kind/size/status,全文不上 wire——D6);docx/pdf 解析+OCR 重活全部
    在 worker.advance_task 的 parsing 阶段做(worker.parse 链)。旧实现(UTF-8 硬解码
    直存,docx/pdf 出乱码)退役。随后后台直推 advance_task(quick 直跑;deep 停确认门)。
    EAI-CUSTOM(2026-10-31 裁定12+14):project_name/lot_name/tender_no=弹窗可选覆盖位,
    空串归 None(=引擎抽取回填位,worker 仅填 NULL 列)。"""
    if mode not in ("quick", "deep"):
        raise HTTPException(status_code=422, detail="mode 仅支持 quick|deep")
    # B10 版本链(spec 2026-11-01 §2.3):先校验基准任务存在+属主,后建任务(防孤儿)。
    # ≠自身 422 不设:新任务 id 服务端生成且校验先于建任务,prev==self 必落 404,422 不可达。
    prev_norm = prev_task_id.strip() or None
    if prev_norm is not None and await crud.get_task(db, task_id=prev_norm, owner_id=owner_id) is None:
        raise HTTPException(status_code=404, detail="基准任务不存在")
    task = await crud.create_task(
        db,
        owner_id=owner_id,
        mode=mode,
        project_name=project_name.strip() or None,
        lot_name=lot_name.strip() or None,
        tender_no=tender_no.strip() or None,
        prev_task_id=prev_norm,
    )
    entries: list[dict] = []
    for f in tender_files or []:
        entries.append(parse.save_raw(owner_id, task.id, "tender", f.filename or "tender-doc", await f.read()))
    for f in bid_files or []:
        entries.append(parse.save_raw(owner_id, task.id, "bid", f.filename or "bid-doc", await f.read()))
    meta = dict(task.engine_meta or {})
    meta["docs"] = entries
    task.engine_meta = meta  # 重新赋值以标记 JSON 列 dirty
    await db.commit()
    await db.refresh(task)
    _enqueue_docs(task, entries)
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
    names = await crud.creator_names(db, [t.owner_id for t in tasks])  # B1:单查询 IN,非逐任务
    items = []
    for t in tasks:
        out = TaskOut.model_validate(t)
        issues = await crud.list_issues(db, task_id=t.id, owner_id=owner_id)
        out.fatal_unhandled = sum(1 for i in issues if i.severity == "fatal" and i.verdict != "false_positive")
        out.need_human_count = sum(1 for i in issues if bool(i.need_human))
        out.main_unhandled = sum(1 for i in issues if i.severity == "major" and i.verdict != "false_positive")  # B1 D1-A
        out.created_by_name = names.get(t.owner_id)  # B1:创建人列(COALESCE(full_name, username))
        items.append(out)
    return {"items": items}


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task_detail(task_id: str, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


def _baseline_items(rows: list, adjudications: dict) -> list[dict]:
    """基线行投影(GET 与 adjudicate 共用,二期 spec §1.3):行契约 + candidates/
    fields_conf/conflicts/effective_fields 四个二期扩展。"""
    items = []
    for r in rows:
        payload = r.payload or {}
        fields = payload.get("fields") or {}
        candidates = payload.get("candidates") or {}
        items.append(
            {
                "kind": r.kind,
                "doc_id": payload.get("doc_id"),
                "confirmed": bool(r.confirmed),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "fields": fields,
                "provenance": payload.get("provenance") or {},
                "candidates": candidates,
                "fields_conf": payload.get("fields_conf") or {},
                "conflicts": sorted(detect_conflicts(candidates)),
                "effective_fields": apply_adjudications(fields, adjudications),
                "materials_hash": payload.get("materials_hash") or "",
            }
        )
    return items


@router.get("/tasks/{task_id}/baselines")
async def list_task_baselines(task_id: str, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """基线行级读端点(EAI-CUSTOM 2026-10-30,分期建议一期 s3/s4——
    docs/superpowers/specs/2026-10-30-bid-review-ui-gaps-and-completeness.md §二):
    此前字段级快照仅 MCP bid_review_baseline_get 可达,前端 HTTP 通道缺位,
    BaselineView 只能降级材料卡。行契约=_write_baselines 落库形:每行同全量
    fields 快照 + 本行 doc_id(payload)+ kind/confirmed;provenance 逐字段出处
    {doc_id,page,quote}(extract.normalize_provenance,模型没给的路径缺省不造假)。
    EAI-CUSTOM(2026-10-30 二期 spec §1.3)投影扩展:candidates 多候选 /
    fields_conf 置信 / conflicts 冲突路径(detect_conflicts)/ effective_fields
    (fields ∪ 裁定覆盖)/ 顶层 labels 中文名 + adjudications(engine_meta 透传)。"""
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    rows = await crud.list_baselines(db, task_id=task_id, owner_id=owner_id)
    adjudications = (task.engine_meta or {}).get("adjudications") or {}
    return {"items": _baseline_items(rows, adjudications), "labels": dict(FIELD_LABELS), "adjudications": adjudications}


@router.post("/tasks/{task_id}/baselines/adjudicate")
async def adjudicate_baseline(task_id: str, body: AdjudicateIn, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """冲突裁定写入(EAI-CUSTOM 2026-10-30 二期 spec §1.3):人工从多候选中裁决
    基准值,落 task.engine_meta.adjudications——不建新表(任务级少量状态,与 resume
    链同生命周期)。仅 awaiting_confirm 可裁定(过门后裁定=改审查依据,409);
    path 不在快照 / value 非 JSON 安全类型 → 422。返回更新后的行投影(与 GET 同构)。"""
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "awaiting_confirm":
        raise HTTPException(status_code=409, detail=f"任务不在确认门(当前 {task.status}):裁定仅确认前有效")
    rows = await crud.list_baselines(db, task_id=task_id, owner_id=owner_id)
    if not rows:
        raise HTTPException(status_code=404, detail="基线未生成")
    fields = (rows[0].payload or {}).get("fields") or {}
    if body.path not in fields:
        raise HTTPException(status_code=422, detail=f"未知字段路径:{body.path}")
    if body.value is None or not isinstance(body.value, str | int | float | bool | dict | list):
        raise HTTPException(status_code=422, detail="value 须为 JSON 安全类型且非 null(放弃抽取值请直接不裁定)")
    meta = dict(task.engine_meta or {})
    adjudications = dict(meta.get("adjudications") or {})
    adjudications[body.path] = {"value": body.value, "at": datetime.now(UTC).isoformat(), **({"note": body.note} if body.note else {})}
    meta["adjudications"] = adjudications
    task.engine_meta = meta  # 重新赋值以标记 JSON 列 dirty
    await db.commit()
    await db.refresh(task)
    adjudications = (task.engine_meta or {}).get("adjudications") or {}
    return {"items": _baseline_items(rows, adjudications), "labels": dict(FIELD_LABELS), "adjudications": adjudications}


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
    # 二期 spec §1.3 门收紧:存在「冲突且未裁定」路径 → 409(错误基准 → 全盘误判,
    # 冲突不裁定即过门等于把裁决推给审查引擎)。与未复核致命 409 同语义层。
    conflict_paths: set[str] = set()
    for b in await crud.list_baselines(db, task_id=task_id, owner_id=owner_id):
        payload = b.payload if isinstance(b.payload, dict) else {}
        conflict_paths |= set(detect_conflicts(payload.get("candidates") or {}))
    adj = (task.engine_meta or {}).get("adjudications") or {}
    unresolved = sorted(p for p in conflict_paths if p not in adj)
    if unresolved:
        raise HTTPException(status_code=409, detail=f"存在 {len(unresolved)} 个未裁定冲突字段:请在基准确认页裁决后重试")
    for b in await crud.list_baselines(db, task_id=task_id, owner_id=owner_id):
        await crud.update_baseline(db, b, confirmed=True)
    if task.status == "awaiting_confirm":
        asyncio.create_task(_resume_after_confirm(task.id, owner_id))
    await db.refresh(task)
    return task


# ── 文档溯源取数(EAI-CUSTOM 2026-10-30,spec §2/D6/D8)──────────────────


def _find_doc_entry(task, doc_id: str) -> dict | None:
    return next((e for e in (task.engine_meta or {}).get("docs") or [] if isinstance(e, dict) and e.get("doc_id") == doc_id), None)


@router.get("/tasks/{task_id}/docs/{doc_id}/content")
async def get_doc_content(
    task_id: str,
    doc_id: str,
    quote: str = "",
    page: int | None = None,
    db: AsyncSession = Depends(get_db),
    owner_id: str = Depends(current_owner),
):
    """溯源定位窗口:证据 chip「定位原文」取数端点。docx 无页边界(D8)走 quote 片段
    命中段 ±10 条窗口;pdf 优先 ?page= 直取整页(真页码),quote 兜底定位。片段匹配
    忽略全部空白(PDF 抽取换行/OCR 断行与模型引用常不一致)。只回窗口不回整本(D6:
    几百页文档全文不上面);未命中 404,前端如实呈现「未定位到原文」。"""
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    entry = _find_doc_entry(task, doc_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    segs = parse.load_segments(owner_id, task_id, str(entry.get("slug") or ""))
    if not segs:
        raise HTTPException(status_code=404, detail="文档尚未解析完成")
    hit = None
    if page is not None:
        hit = next((s for s in segs if s.get("page") == page), None)
    elif quote:
        q = "".join(quote.split())
        if q:
            hit = next((s for s in segs if q in "".join(str(s.get("text") or "").split())), None)
    if hit is None:
        raise HTTPException(status_code=404, detail="未定位到原文")
    if hit.get("page") is not None:
        win = [s for s in segs if s.get("page") == hit["page"]]
    else:
        win = parse.excerpt_window(segs, int(hit["seq"] or 0))
    return {
        "doc": {k: entry.get(k) for k in ("doc_id", "role", "kind", "pages", "chars", "assets", "status")},
        "page": hit.get("page"),
        "seq": hit.get("seq"),
        "segments": win,
    }


@router.get("/tasks/{task_id}/docs/{doc_id}/assets/{asset_id}")
async def get_doc_asset(
    task_id: str,
    doc_id: str,
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    owner_id: str = Depends(current_owner),
):
    """原图取数(盖章页/图片 OCR 的原件预览)。asset 必须已被该文档 segments 引用
    (防跨文档探测);asset_id 由解析层生成为 hex md5[:16],无路径注入面。"""
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    entry = _find_doc_entry(task, doc_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    segs = parse.load_segments(owner_id, task_id, str(entry.get("slug") or ""))
    if asset_id not in {str(s.get("asset_id") or "") for s in segs}:
        raise HTTPException(status_code=404, detail="资产不存在")
    matches = list((parse.task_dir(owner_id, task_id) / "assets").glob(f"{asset_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="资产文件缺失")
    import mimetypes

    mt = mimetypes.guess_type(matches[0].name)[0] or "application/octet-stream"
    return FileResponse(matches[0], media_type=mt)


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


# ── B2 复核落库投影(EAI-CUSTOM 2026-10-31 Plan9 spec §4.6)────────────────
# 反馈动作 → review_state;最新动作即真源,verdict 不参与(confirm/severity_change
# 不改 verdict,单独投影才能表达 maintained/severity_changed)。
_REVIEW_ACTION_STATE = {
    "confirm": "maintained",
    "false_positive": "false_positive",
    "severity_change": "severity_changed",
    "need_human": "deferred",
}


def _with_review_state(issue, states: dict[str, str]) -> IssueOut:
    out = IssueOut.model_validate(issue)
    out.review_state = _REVIEW_ACTION_STATE.get(states.get(issue.id, ""), "unresolved")
    return out


_LAYER_RANK = {"L1": 0, "L2": 1, "L3": 2}


def _cross_layer_group(issues: list) -> dict[str, dict]:
    """跨层实体去重投影(L2 P2,spec 2026-11-02 §7 挂账行,EAI-CUSTOM;现算不落库,
    先例=deviations/attachment_checklist):同一实体键(entity_keys 交集)且跨 ≥2 层的
    violation(非 need_human)归并——keep most_severe(并列取层序 L1>L2>L3,再取
    created_at 稳定),其余行标 grouped_into=keep.id,keep 行带 related_issues 摘要。
    条目不删:items 仍全量返回(前端隐藏 grouped 行),summary 口径不变。
    need_human 不参与归并(待人工必须可见)。多实体键行按键名字序迭代保稳定。
    多键行 grouped_into 取按名字序最后命中键的 keep(确定性 last-wins)。"""
    info: dict[str, dict] = {}
    keyed: dict[str, list] = {}
    for i in issues:
        if getattr(i, "verdict", "") != "violation" or getattr(i, "need_human", False):
            continue
        for k in getattr(i, "entity_keys", None) or []:
            keyed.setdefault(k, []).append(i)
    for key in sorted(keyed):
        group = keyed[key]
        layers = {getattr(i, "layer", "") for i in group}
        if len(layers) < 2 or len({i.id for i in group}) < 2:
            continue
        ranked = sorted(group, key=lambda i: (_SEV_RANK.get(getattr(i, "severity", ""), 9), _LAYER_RANK.get(getattr(i, "layer", ""), 9), getattr(i, "created_at", "")))
        keep = ranked[0]
        for i in ranked[1:]:
            if i.id == keep.id:
                continue
            info.setdefault(i.id, {"grouped_into": None, "related": []})["grouped_into"] = keep.id
            kentry = info.setdefault(keep.id, {"grouped_into": None, "related": []})
            if all(r["id"] != i.id for r in kentry["related"]):
                kentry["related"].append({"id": i.id, "rule_id": i.rule_id, "layer": i.layer, "severity": i.severity, "message": i.message})
    return info


@router.get("/tasks/{task_id}/issues")
async def list_task_issues(task_id: str, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    if await crud.get_task(db, task_id=task_id, owner_id=owner_id) is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    issues = await crud.list_issues(db, task_id=task_id, owner_id=owner_id)
    states = await crud.latest_feedback_actions(db, [i.id for i in issues])
    grouping = _cross_layer_group(issues)  # L2 P2 跨层实体去重(现算,不落库)
    items = []
    for i in issues:
        out = _with_review_state(i, states)
        g = grouping.get(i.id)
        if g:
            out.grouped_into = g["grouped_into"]
            out.related_issues = g["related"]
        items.append(out)
    return {
        "items": items,
        # 汇总分级(A12 T14 集成约束①,与 worker progress.summary 共用 summarize_issues
        # 同一口径):正式违规计数(fatal/major/minor/info)不含 need_human 条目,待人工
        # 单列;条目不删——items 仍全量返回(工作台待人工格与 verdict 过滤消费)。
        # L2 P2(D8):口径不变——grouped 行仍计入 summary(前端隐藏由展示层负责)。
        "summary": worker.summarize_issues(issues),
    }


@router.get("/issues/{issue_id}", response_model=IssueOut)
async def get_issue_detail(issue_id: str, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    issue = await crud.get_issue(db, issue_id=issue_id, owner_id=owner_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="问题不存在")
    return _with_review_state(issue, await crud.latest_feedback_actions(db, [issue.id]))


@router.post("/issues/{issue_id}/feedback", response_model=IssueOut)
async def feedback_issue(issue_id: str, body: FeedbackIn, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """复核反馈:写 ReviewFeedback + RulePackMeta.stats 回流。false_positive 走误报回流
    (apply_false_positive:verdict/need_human 落库 + fp+1 + fp_samples 滚动);confirm→
    adopted+1 且清 need_human(EAI-CUSTOM 2026-10-30 待人工闭环:待人工→确认后不再挂
    待人工格);need_human→verdict="need_human" 落库,不计规则包统计(非误报也非认可,
    引擎无法判定的人工挂起,A12 三值语义);severity_change 只落反馈行且允许任意合法档位
    ——人工降级不拦(端点校验只拦非法值;模型侧 fatal 降级拦截是 verify 层
    normalize_severity 职责)。"""
    if body.action not in ("confirm", "false_positive", "severity_change", "need_human"):
        raise HTTPException(status_code=422, detail="action 仅支持 confirm|false_positive|severity_change|need_human")
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
    elif body.action == "need_human":
        issue.need_human = True
        issue.verdict = "need_human"  # 不计规则包统计(非误报非认可;正式违规口径按 verdict 排除)
    elif body.action == "confirm":
        issue.need_human = False  # 待人工闭环:确认后不再挂待人工格(need_human_count 自然回落)
        await crud.add_rulepack_stats(db, RULEPACK_NAME, issue.rule_id, adopted=True)
    await db.refresh(issue)
    out = IssueOut.model_validate(issue)
    out.review_state = _REVIEW_ACTION_STATE.get(body.action, "unresolved")
    return out


# ── 报告导出(Task 21;html 导出属 M4,本轮不做)───────────────────────

REPORT_DISCLAIMER = "本报告为辅助提示,最终责任由投标主体承担"
SEVERITY_LABELS = {"fatal": "致命", "major": "主要", "minor": "次要", "info": "提示"}


def _oneline(text: str) -> str:
    """md 结构行安全化:message/fix 换行拍平为空格,防条目文本撞坏分节结构。"""
    return " ".join(str(text or "").split())


def _fmt_evidence(evidence: list) -> str:
    """证据列表 → 逐条「doc_id · p.页码(摘录:…)」分号连接;空列表回「无」。"""
    parts: list[str] = []
    for ev in evidence or []:
        if not isinstance(ev, dict):
            continue
        loc = _oneline(str(ev.get("doc_id") or "未知文档"))
        page = ev.get("page")
        if isinstance(page, int) and not isinstance(page, bool):
            loc += f" · p.{page}"
        excerpt = _oneline(str(ev.get("text") or ""))
        if excerpt:
            loc += f"(摘录:{excerpt})"
        parts.append(loc)
    return ";".join(parts) if parts else "无"


def _feedback_summary(feedback: list) -> str:
    """对齐审计③(2026-11-05):复核耗时真数据落位(「待补充」假占位删除)。
    0 条=未复核;1 条=1 次动作;≥2 条=首末动作跨度(下界——中间空档不计,
    无从知晓复核是否连续,标 ≥ 不造假)。"""
    stamps = [f.created_at for f in feedback if getattr(f, "created_at", None)]
    if not stamps:
        return "人工复核:未复核"
    if len(stamps) == 1:
        return f"人工复核:1 次动作(首条 {stamps[0]:%Y-%m-%d %H:%M} UTC)"
    span_h = (max(stamps) - min(stamps)).total_seconds() / 3600
    return f"人工复核:≥{span_h:.1f}h(首末动作跨度,下界;{len(stamps)} 次动作)"


def _fatal_hits(issues: list) -> list:
    """可提交判定口径(双渲染器共享,防漂移;spec 2026-11-05 R4):正式 fatal 违规=
    severity=fatal 且 verdict=violation 且非 need_human——人工误报与待人工条目不计入命中红线。"""
    return [i for i in issues if i.severity == "fatal" and i.verdict == "violation" and not i.need_human]


def _esc(v) -> str:
    """html 报告动态文本全量转义(spec R2);None 归空串。"""
    return html.escape(str(v if v is not None else ""))


def _render_report_html(task, issues: list, feedback: list | None = None, deviations: dict | None = None) -> str:
    """审查报告 html 渲染(M4+ 挂账兑付,spec 2026-11-05):与 _render_report_md 内容
    对等(R4,口径共享 _fatal_hits),全动态文本经 _esc(R2);单文件内联样式、无外部
    资源,配 Content-Disposition attachment 强制下载(gateway XSS 姿态)。"""
    issues = [i for i in issues if i.verdict != "false_positive"]
    fatal_hits = _fatal_hits(issues)
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    tid = _esc(task.id[:8])
    meta_lines = [
        f"任务 ID:{_esc(task.id)}",
        f"任务状态:{_esc(task.status)}",
        f"审查模式:{_esc(task.mode)}",
        _esc(_feedback_summary(feedback or [])),
        f"生成时间:{_esc(now)}",
    ]
    gate_txt = f"命中致命红线 {len(fatal_hits)} 项,建议整改后重新审查。" if fatal_hits else "未命中致命红线,可进入人工终审。"
    parts = [
        "<!doctype html>",
        '<html lang="zh"><head><meta charset="utf-8">',
        f"<title>投标审查报告 {tid}</title>",
        "<style>",
        "body{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem;line-height:1.6;color:#111}",
        ".disclaimer{color:#666;border-left:3px solid #ccc;padding-left:.8rem}",
        ".meta{list-style:none;padding-left:0;color:#444;font-size:.95rem}",
        ".hit{color:#b91c1c;font-weight:600}.ok{color:#166534;font-weight:600}",
        "article.issue{border:1px solid #ddd;border-radius:6px;padding:.5rem .9rem;margin:.5rem 0}",
        "article.issue h3{margin:.2rem 0;font-size:1rem}",
        ".tag{display:inline-block;border-radius:4px;padding:0 .45rem;font-size:.8rem;color:#fff}",
        ".sev-fatal{background:#b91c1c}.sev-major{background:#d97706}.sev-minor{background:#6b7280}.sev-info{background:#2563eb}",
        ".kv{color:#444;margin:.15rem 0}",
        "h2{border-bottom:1px solid #eee;padding-bottom:.2rem;margin-top:1.6rem}",
        "@media print{body{margin:0}}",
        "</style></head><body>",
        f'<p class="disclaimer">免责声明:{_esc(REPORT_DISCLAIMER)}</p>',
        f"<h1>投标审查报告 {tid}</h1>",
        '<ul class="meta">' + "".join(f"<li>{m}</li>" for m in meta_lines) + "</ul>",
        f'<h2>可提交判定</h2><p class="{"hit" if fatal_hits else "ok"}">{_esc(gate_txt)}</p>',
    ]
    for sev in ("fatal", "major", "minor", "info"):
        rows = [i for i in issues if i.severity == sev]
        parts.append(f"<h2>{_esc(SEVERITY_LABELS[sev])}({sev})——{len(rows)} 项</h2>")
        if not rows:
            parts.append("<p>无</p>")
            continue
        for i in rows:
            parts.append(
                '<article class="issue">'
                f'<span class="tag sev-{_esc(sev)}">{_esc(sev)}</span>'
                f"<h3>{_esc('【待人工】' if i.need_human else '')}{_esc(i.rule_id)} {_esc(_oneline(i.message))}</h3>"
                f'<p class="kv">判定:{_esc(i.verdict)}</p>'
                f'<p class="kv">证据:{_esc(_fmt_evidence(list(i.evidence or [])))}</p>'
                f'<p class="kv">修复建议:{_esc(_oneline(i.fix)) or "无"}</p>'
                "</article>"
            )
    # 响应偏离表节:同 md 渲染器口径(deviations={counts, items})
    counts = (deviations or {}).get("counts") or {}
    items = (deviations or {}).get("items") or []
    parts.append(f"<h2>响应偏离表(缺失 {_esc(counts.get('missing', 0))} · 增项 {_esc(counts.get('extra', 0))} · 负偏离 {_esc(counts.get('negative', 0))})</h2>")
    if not items:
        parts.append("<p>无记录(本任务抽取时未包含偏离维度或未检出偏离项)。</p>")
    else:
        parts.append(
            "<ul>"
            + "".join(f"<li>{_esc(_oneline(str(d.get('item') or '')))}:{_esc(d.get('kind') or '?')}(招标:{_esc(_oneline(str(d.get('tender_value') or '无')))} ↔ 投标:{_esc(_oneline(str(d.get('bid_value') or '无')))})</li>" for d in items)
            + "</ul>"
        )
    parts.append("</body></html>")
    return "\n".join(parts)


def _render_report_md(task, issues: list, feedback: list | None = None, deviations: dict | None = None) -> str:
    """审查报告 md 渲染(plan Task 21 Step 1 契约,报告呈现形态以 plan 原文为准):
    首行免责声明 → 任务元信息(复核耗时=feedback 真聚合,对齐审计③ 2026-11-05)→
    可提交判定提示行(措辞照 ui-spec §3.5 照抄;口径=正式 fatal 违规:severity=fatal
    且 verdict=violation 且非 need_human——人工误报与待人工条目不计入命中红线)→
    按 severity 四档分节,每条含规则 ID/证据(doc+page)/修复建议;need_human 条目
    不删除,按 severity 归节并标注【待人工】;false_positive 人工误报不进正文;
    尾部响应偏离表节(对齐审计⑩:counts+逐条,同 /deviations 投影口径)。"""
    issues = [i for i in issues if i.verdict != "false_positive"]
    fatal_hits = _fatal_hits(issues)  # 口径共享(spec 2026-11-05 R4,防双渲染器漂移)
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"> 免责声明:{REPORT_DISCLAIMER}",
        "",
        f"# 投标审查报告 {task.id[:8]}",
        "",
        f"- 任务 ID:{task.id}",
        f"- 任务状态:{task.status}",
        f"- 审查模式:{task.mode}",
        _feedback_summary(feedback or []),
        f"- 生成时间:{now}",
        "",
        "## 可提交判定",
        "",
        (f"命中致命红线 {len(fatal_hits)} 项,建议整改后重新审查。" if fatal_hits else "未命中致命红线,可进入人工终审。"),
        "",
    ]
    for sev in ("fatal", "major", "minor", "info"):
        rows = [i for i in issues if i.severity == sev]
        lines += [f"## {SEVERITY_LABELS[sev]}({sev})——{len(rows)} 项", ""]
        if not rows:
            lines += ["无", ""]
            continue
        for i in rows:
            lines += [
                f"### {'【待人工】' if i.need_human else ''}{i.rule_id} {_oneline(i.message)}",
                f"- 判定:{i.verdict}",
                f"- 证据:{_fmt_evidence(list(i.evidence or []))}",
                f"- 修复建议:{_oneline(i.fix) or '无'}",
                "",
            ]
    # 对齐审计⑩(2026-11-05):响应偏离表节(deviations={counts, items},同 /deviations 端点口径)
    counts = (deviations or {}).get("counts") or {}
    items = (deviations or {}).get("items") or []
    lines += [f"## 响应偏离表(缺失 {counts.get('missing', 0)} · 增项 {counts.get('extra', 0)} · 负偏离 {counts.get('negative', 0)})", ""]
    if not items:
        lines += ["无记录(本任务抽取时未包含偏离维度或未检出偏离项)。", ""]
    else:
        for d in items:
            lines.append(f"- {_oneline(str(d.get('item') or ''))}:{d.get('kind') or '?'}(招标:{_oneline(str(d.get('tender_value') or '无'))} ↔ 投标:{_oneline(str(d.get('bid_value') or '无'))})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


@router.get("/tasks/{task_id}/report")
async def export_task_report(
    task_id: str,
    format: str = "md",
    db: AsyncSession = Depends(get_db),
    owner_id: str = Depends(current_owner),
):
    """审查报告导出(plan Task 21):format=md 返回 markdown 文本(首行免责声明、
    可提交判定提示行、按 severity 分节、每条含规则 ID/证据/修复建议、复核耗时占位);
    format=html 返回单文件 HTML(M4+ 挂账兑付,spec 2026-11-05:原生渲染全转义 +
    attachment 强制下载,内容与 md 对等);未知格式 422 拒绝不静默降级;owner 过滤同
    既有端点,Content-Disposition attachment 供浏览器直接下载。状态门(QUAL 修复):
    仅 done 可导,半程任务 409——基于空/半程 issue 集算出的可提交判定行不得冒充审查
    结论流出到非 UI 消费方(与 WorkbenchView 前端 done 门同口径)。"""
    if format not in ("md", "html"):
        raise HTTPException(status_code=422, detail="format 仅支持 md|html")
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "done":
        raise HTTPException(status_code=409, detail=f"任务未完成(当前 {task.status}):仅 done 可导出报告,半程数据不构成审查结论")
    issues = await crud.list_issues(db, task_id=task_id, owner_id=owner_id)
    feedback = await crud.list_task_feedback(db, task_id=task_id, owner_id=owner_id)  # 对齐审计③
    # 对齐审计⑩:偏离投影同 /deviations 端点先例(基线跨行按 item 名去重,counts 服务端算)
    baselines = await crud.list_baselines(db, task_id=task_id, owner_id=owner_id)
    dev_items: list[dict] = []
    seen_names: set[str] = set()
    for row in baselines:
        for item in (row.payload or {}).get("fields", {}).get("deviation.items") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("item") or "").strip()
            if name and name not in seen_names:
                seen_names.add(name)
                dev_items.append(item)
    deviations = {"counts": deviation_counts(dev_items), "items": dev_items}
    render = _render_report_md if format == "md" else _render_report_html
    return Response(
        content=render(task, issues, feedback=feedback, deviations=deviations),
        media_type="text/markdown; charset=utf-8" if format == "md" else "text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="bid-review-report-{task_id[:8]}.{format}"'},
    )


# ── B7 版本 diff(spec §5)──────────────────────────────────────────


_SEV_RANK = {"fatal": 0, "major": 1, "minor": 2, "info": 3}


def _rule_verdicts(issues: list) -> dict[str, dict]:
    """问题按 rule_id 归并(B10 spec §2.1):present=存在 verdict≠false_positive 的问题;
    severity=其中最严(_SEV_RANK 小者优先)。仅误报的 rule_id 不入结果(并集=非误报并集)。"""
    by_rule: dict[str, list] = {}
    for i in issues:
        if (i.verdict or "") == "false_positive":
            continue
        by_rule.setdefault(i.rule_id, []).append(i)
    return {rid: {"present": True, "severity": min((r.severity for r in rows), key=lambda s: _SEV_RANK.get(s, 9))} for rid, rows in by_rule.items()}


@router.get("/tasks/{task_id}/diff")
async def diff_task(
    task_id: str,
    prev: str,
    db: AsyncSession = Depends(get_db),
    owner_id: str = Depends(current_owner),
):
    """版本 diff(spec §5 B7):问题级三态 {added, removed, unchanged_count}。
    匹配键 = dedup_key(rule_id+锚定字段路径——与引擎查重 crud.add_issue 同源语义,
    重复命中共键合并,天然抗重跑抖动);空 dedup_key 永不匹配(按新增/消失计,
    crud 契约里空键本就跳过查重)。added 带判定面字段供前端「新增问题列表」直渲,
    removed 只带计数面三字段(消失问题详情在上一版任务);各自按 severity 降序
    (致命在前)。prev 不存在或属他者 → 404(owner 隔离,不泄漏他者任务存在性)。
    前端消费:/results 版本对比卡片(spec §4.5,轻量)+ s8 整屏 /diff(spec
    2026-11-01 B10:扩展 fields/rules 两键,既有三键原样=向后兼容)。"""
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    prev_task = await crud.get_task(db, task_id=prev, owner_id=owner_id)
    if task is None or prev_task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    cur = await crud.list_issues(db, task_id=task_id, owner_id=owner_id)
    old = await crud.list_issues(db, task_id=prev, owner_id=owner_id)
    old_keys = {i.dedup_key for i in old if i.dedup_key}
    cur_keys = {i.dedup_key for i in cur if i.dedup_key}
    added = sorted(
        (i for i in cur if not i.dedup_key or i.dedup_key not in old_keys),
        key=lambda i: _SEV_RANK.get(i.severity, 9),
    )
    removed = sorted(
        (i for i in old if not i.dedup_key or i.dedup_key not in cur_keys),
        key=lambda i: _SEV_RANK.get(i.severity, 9),
    )
    # B10 fields(§2.1):两版基线首行 fields 快照逐路径机械对比,值不同才列
    # (JSON-safe !=);label 取 FIELD_LABELS,未收录回退原路径。单侧无基线 →
    # 不比(空表):null 在此语义是「未抽取」,冒充「旧版没有」= 造假差异。
    cur_baselines = await crud.list_baselines(db, task_id=task_id, owner_id=owner_id)
    prev_baselines = await crud.list_baselines(db, task_id=prev, owner_id=owner_id)
    cur_fields = (cur_baselines[0].payload or {}).get("fields", {}) if cur_baselines else {}
    prev_fields = (prev_baselines[0].payload or {}).get("fields", {}) if prev_baselines else {}
    field_rows = (
        [{"path": p, "label": FIELD_LABELS.get(p, p), "prev": prev_fields.get(p), "cur": cur_fields.get(p)} for p in sorted(set(prev_fields) | set(cur_fields)) if prev_fields.get(p) != cur_fields.get(p)]
        if cur_baselines and prev_baselines
        else []
    )
    # B10 rules(§2.1):两版问题按 rule_id 归并(_rule_verdicts 剔误报),并集;
    # 有变化者(present 或 severity 不同)排前,余按 rule_id 稳定排序。
    prev_rules = _rule_verdicts(old)
    cur_rules = _rule_verdicts(cur)
    absent = {"present": False, "severity": None}
    rule_rows = [{"rule_id": rid, "prev": prev_rules.get(rid, absent), "cur": cur_rules.get(rid, absent)} for rid in sorted(set(prev_rules) | set(cur_rules))]
    rule_rows.sort(key=lambda r: (0 if r["prev"] != r["cur"] else 1, r["rule_id"]))
    return {
        "added": [
            {
                "id": i.id,
                "rule_id": i.rule_id,
                "layer": i.layer,
                "severity": i.severity,
                "message": i.message,
                "need_human": i.need_human,
            }
            for i in added
        ],
        "removed": [{"rule_id": i.rule_id, "severity": i.severity, "message": i.message} for i in removed],
        "unchanged_count": len(cur_keys & old_keys),
        "fields": field_rows,
        "rules": rule_rows,
    }


@router.get("/tasks/{task_id}/score_coverage")
async def task_score_coverage(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    owner_id: str = Depends(current_owner),
):
    """评分覆盖度(spec §5 B4):基线评分办法项 × 生产规则包 inputs 机械求交。
    评分办法项由抽取层落 baseline fields.tender.scoring_items(项携带
    related_paths,限定字段字典路径);基线每行携带同全量快照 → 逐行收集后按
    name 去重。旧任务/未抽出评分项 → {total:0, covered:0, items:[]}(前端据此
    回落「规则命中」meter 现状口径,spec §4.5 line 117;空短路形状字节不变,
    score-risk spec R4/R5)。
    评分涉险面(score-risk spec 2026-11-05):本体键之上派生 at_risk_max_score /
    at_risk_item_names / unresolved_item_names 三事实键——涉险**上界**非预计扣分
    (引擎不知评分裁量矩阵,拒绝编造);归因链=违规规则 id ∩ covered_by_rules,
    与覆盖度同源交集。MCP bid_review_score_coverage **out 透传自动浮出。"""
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    baselines = await crud.list_baselines(db, task_id=task_id, owner_id=owner_id)
    raw_items: list[dict] = []
    seen_names: set[str] = set()
    for row in baselines:
        for item in (row.payload or {}).get("fields", {}).get("tender.scoring_items") or []:
            if isinstance(item, dict) and str(item.get("name") or "").strip() not in seen_names:
                name = str(item.get("name") or "").strip()
                if name:
                    seen_names.add(name)
                    raw_items.append(item)
    if not raw_items:
        return {"total": 0, "covered": 0, "items": []}
    pack = worker.load_rulepack(worker.RULEPACK_PATH)
    out = compute_score_coverage(raw_items, pack.rules)
    issues = await crud.list_issues(db, task_id=task_id, owner_id=owner_id)
    violation_rule_ids = {i.rule_id for i in issues if i.verdict == "violation" and not i.need_human}
    unresolved_rule_ids = {i.rule_id for i in issues if i.verdict != "false_positive" and (i.need_human or i.verdict == "unclear")}
    out.update(derive_score_risk(out, violation_rule_ids, unresolved_rule_ids))
    return out


@router.get("/tasks/{task_id}/deviations")
async def task_deviations(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    owner_id: str = Depends(current_owner),
):
    """响应偏离表(spec 2026-11-01 §1.2 B9):基线 fields["deviation.items"] 投影
    (抽取期 LLM 逐条对照招标↔投标)。基线每行携带同全量快照 → 按 item 名跨行
    去重(B4 手法);counts 服务端算单一事实源。旧任务/未抽出 → 零投影(counts 全
    0 + items 空,前端空态引导「本任务抽取时未包含偏离维度」)。"""
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    baselines = await crud.list_baselines(db, task_id=task_id, owner_id=owner_id)
    items: list[dict] = []
    seen_names: set[str] = set()
    for row in baselines:
        for item in (row.payload or {}).get("fields", {}).get("deviation.items") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("item") or "").strip()
            if name and name not in seen_names:
                seen_names.add(name)
                items.append(item)
    return {"counts": deviation_counts(items), "items": items}


@router.get("/tasks/{task_id}/attachment_checklist")
async def task_attachment_checklist(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    owner_id: str = Depends(current_owner),
):
    """附件核对表(L2 P1 spec 2026-11-02 §4):基线 fields tender.attachment_requirements
    × bid.attachment_index 经 engine.attachments.build_checklist 两级精确匹配投影
    (现算不落库,先例=/deviations /score_coverage)。要求按 (no,name) 跨行去重,提供项
    逐行收集;refs 注入 bid 侧首 doc_id(engine_meta.docs role=bid;解不到 → null,前端
    chip 降级纯文本)。零投影(旧任务无附件维度)→ counts 全 0 + items [](诚实空态)。"""
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    baselines = await crud.list_baselines(db, task_id=task_id, owner_id=owner_id)
    reqs: list[dict] = []
    seen_req: set[tuple[str, str]] = set()
    provided: list[dict] = []
    for row in baselines:
        fields = (row.payload or {}).get("fields", {})
        for item in fields.get("tender.attachment_requirements") or []:
            if isinstance(item, dict):
                key = (str(item.get("no") or "").strip(), str(item.get("name") or "").strip())
                if key not in seen_req:
                    seen_req.add(key)
                    reqs.append(item)
        for item in fields.get("bid.attachment_index") or []:
            if isinstance(item, dict):
                provided.append(item)
    if not reqs:
        return build_checklist([], [], bid_doc_id=None)
    docs = (task.engine_meta or {}).get("docs") or []
    bid_doc = next(
        (str(d.get("doc_id")) for d in docs if isinstance(d, dict) and d.get("role") == "bid" and d.get("doc_id")),
        None,
    )
    return build_checklist(reqs, provided, bid_doc_id=bid_doc)


@router.post("/tasks/{task_id}/retry", response_model=TaskOut)
async def retry_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    owner_id: str = Depends(current_owner),
):
    """重试解析(spec §4.1 B8,任务列表操作列):仅 failed 终态可重试——终态
    done/awaiting_confirm 不复活、created/在途不双跑(409),不存在/属他者 404。
    重试 = error 清空 + infra_attempts 归零(手动重试给全新预算,不继承自动失败
    链计数)+ 回 created + _enqueue_docs 后台直推。解析幂等:失败文档条目仍是
    raw,重入 parsing 只补解析失败文档,已解析条目不重复跑 OCR(worker.advance_task
    仅解析 status=="raw" 条目)。"""
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "failed":
        raise HTTPException(status_code=409, detail="仅失败任务可重试")
    meta = dict(task.engine_meta or {})
    meta["infra_attempts"] = 0
    task.engine_meta = meta  # 重新赋值以标记 JSON 列 dirty
    task.error = None
    await crud.set_status(db, task, "created", progress={"stage": "parsing", "pct": 0, "msg": "手动重试,重新解析"})
    _enqueue_docs(task, [])
    await db.refresh(task)
    return task


# ── 规则包端点 ────────────────────────────────────────────────────────


def _rule_op(chk: dict) -> str | None:
    """判定算子投影(B5,M5 §4.7):op 形态回白名单原值,steps 链形态归一 "steps"
    (表列 mono 展示;加载器保证非 steps 必有 op)。"""
    if "steps" in chk:
        return "steps"
    return chk.get("op")


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
                # 2026-10-30 前端工作台证据行回退:det 规则 issue 无 doc/page 证据(anchors.py 未落地),回退展示判定输入字段
                "rules": [{"id": r.id, "name": r.name, "layer": r.layer, "severity": r.severity, "type": r.type, "op": _rule_op(r.check or {}), "inputs": list(r.inputs or [])} for r in pack.rules],
                "stats": dict(meta.stats or {}) if meta else {},
                "enabled": bool(meta.enabled) if meta else True,
            }
        ]
    }


@router.get("/rulepacks/{name}/rules")
async def rulepack_rule_details(name: str, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """规则定义五块明细(B5,M5 §4.7,治理页只读抽屉):PRECONDITION / EXPR /
    ON_MISSING_INPUT / MESSAGE_TPL / FIX_TPL。EXPR 取 steps/all/values 链或
    `left op right` 单式;on_missing_input 从包级 conventions 投影到每条。本页零写
    路径——修订须走规则包版本发布;name 不匹配生产包 404(当前单包 bid-review-core)。
    enabled 投影生效态(yaml ∧ DB override,对齐审计⑨ 2026-11-05)。"""
    pack = worker.load_rulepack(worker.RULEPACK_PATH)
    if name != pack.name:
        raise HTTPException(status_code=404, detail=f"未知规则包 {name}")
    meta = (await db.execute(select(RulePackMeta).where(RulePackMeta.name == pack.name))).scalar_one_or_none()
    overrides = dict(meta.rule_overrides or {}) if meta else {}
    items = []
    for r in pack.rules:
        chk = r.check or {}
        if "steps" in chk:
            expr_lines = [str(e) for e in chk.get("steps", [])]
        elif "all" in chk:
            expr_lines = [str(e) for e in chk.get("all", [])]
        elif "values" in chk:
            expr_lines = [str(e) for e in chk.get("values", [])]
        else:
            expr_lines = [f"{chk.get('left', '')} {chk.get('op', '')} {chk.get('right', '')}"]
        items.append(
            {
                "id": r.id,
                "name": r.name,
                "layer": r.layer,
                "severity": r.severity,
                "type": r.type,
                "op": _rule_op(chk),
                "precondition": str(chk["precondition"]) if "precondition" in chk else None,
                "expr_lines": expr_lines,
                "on_missing_input": str(pack.conventions.get("on_missing_input") or "") or None,
                "message_tpl": r.message_tpl,
                "fix_tpl": r.fix_tpl,
                "evidence": list(r.evidence or []),
                "enabled": bool(r.enabled) and overrides.get(r.id, True),
            }
        )
    return {"pack": {"name": pack.name, "version": pack.version}, "items": items}


@router.post("/rulepacks/{name}/rules/{rule_id}/enabled")
async def set_rule_enabled(name: str, rule_id: str, body: RuleEnabledIn, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """规则级启用开关(对齐审计⑨,2026-11-05):落 DB RulePackMeta.rule_overrides
    {rule_id: bool} 而非改写 yaml(git 跟踪源文件禁运行时改写);生效语义 =
    yaml enabled ∧ DB override(worker._apply_rule_overrides 相与),下次审查跑批
    生效。未知规则/未知包 404。"""
    pack = worker.load_rulepack(worker.RULEPACK_PATH)
    if name != pack.name:
        raise HTTPException(status_code=404, detail=f"未知规则包 {name}")
    if rule_id not in {r.id for r in pack.rules}:
        raise HTTPException(status_code=404, detail=f"未知规则 {rule_id}")
    meta = await crud.get_or_create_rulepack_meta(db, pack.name, version=pack.version)
    overrides = dict(meta.rule_overrides or {})
    overrides[rule_id] = body.enabled
    meta.rule_overrides = overrides  # 重新赋值以标记 JSON 列 dirty
    await db.commit()
    await db.refresh(meta)
    return {"success": True, "rule_id": rule_id, "enabled": body.enabled, "rule_overrides": overrides}


@router.get("/metrics/fail_attribution")
async def metrics_fail_attribution(db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """FAIL 归因(B6,M5 §4.8):false_positive 反馈经 ReviewIssue join 取 rule_id,
    按规则聚合误报原因(note 首段「误报原因:X」折进约定,到首个分号止;无前缀 →
    未归因,不伪造)。治理域口径同 GET /rulepacks:全库聚合,owner 仅作鉴权。"""
    rows = (await db.execute(select(ReviewIssue.rule_id, ReviewFeedback.note).join(ReviewFeedback, ReviewFeedback.issue_id == ReviewIssue.id).where(ReviewFeedback.action == "false_positive"))).all()
    agg: dict[str, dict[str, int]] = {}
    for rule_id, note in rows:
        reason = _fp_reason_of(note)
        bucket = agg.setdefault(rule_id, {})
        bucket[reason] = bucket.get(reason, 0) + 1
    items = [
        {
            "rule_id": rid,
            "total": sum(counts.values()),
            "reasons": [{"reason": reason, "count": count} for reason, count in sorted(counts.items(), key=lambda kv: -kv[1])],
        }
        for rid, counts in sorted(agg.items(), key=lambda kv: -sum(kv[1].values()))
    ]
    return {"items": items}


def _fp_reason_of(note: object) -> str:
    """误报原因折 note 约定(工作台/结果页同口径):「误报原因:」后到首个分号止;
    无前缀或空白 → 未归因。"""
    s = str(note or "")
    if s.startswith("误报原因:"):
        return s[len("误报原因:") :].split(";")[0].strip() or "未归因"
    return "未归因"


@router.get("/metrics/trends")
async def metrics_trends(db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """近 6 周误报率趋势(B6,M5 §4.8):ReviewFeedback 按自然周(周一始)分桶,
    周误报率 = false_positive / (false_positive + confirm);其余动作不进分母。
    空周 rate=None——伪零纪律:无回流数据的周不给 0%。"""
    fbs = (await db.execute(select(ReviewFeedback).where(ReviewFeedback.action.in_(("false_positive", "confirm"))))).scalars().all()
    today = datetime.now(UTC).date()
    this_monday = today - timedelta(days=today.weekday())
    starts = [this_monday - timedelta(weeks=i) for i in range(5, -1, -1)]
    buckets: dict = {s: [0, 0] for s in starts}
    for fb in fbs:
        d = fb.created_at.date() if fb.created_at is not None else None
        if d is None:
            continue
        mon = d - timedelta(days=d.weekday())
        if mon in buckets:
            buckets[mon][0 if fb.action == "false_positive" else 1] += 1
    weeks = []
    for s in starts:
        fp, confirmed = buckets[s]
        weeks.append(
            {
                "week_start": s.isoformat(),
                "fp": fp,
                "confirmed": confirmed,
                "rate": round(fp / (fp + confirmed) * 100, 1) if (fp + confirmed) > 0 else None,
            }
        )
    return {"weeks": weeks}


@router.get("/metrics/extraction")
async def metrics_extraction(db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """抽取质量指标(B立项 M5,§十指标投影,2026-11-05):每任务取**最新**基线行的
    crosscheck(worker 交叉自检段产物,created_at asc 后写覆盖=最新),聚合核心字段
    成功率均值 / 页偏移任务数 / 正副本冲突总数 / 声明 missing 与 extra 总数。治理域
    口径同 GET /rulepacks 与既有两 metrics 端点:全库聚合,owner 仅作鉴权。伪零纪律:
    无任务计数 0、均值 None,不伪造;无 crosscheck 键的基线行(旧任务/隔离失败)不计。"""
    rows = (await db.execute(select(BaselinePackage).order_by(BaselinePackage.created_at, BaselinePackage.id))).scalars().all()
    latest: dict[str, dict] = {}
    for b in rows:
        p = b.payload if isinstance(b.payload, dict) else {}
        if isinstance(p.get("crosscheck"), dict) and p["crosscheck"]:
            latest[b.task_id] = p["crosscheck"]
    decl_missing = lambda c: len((c.get("declarations") or {}).get("missing") or [])  # noqa: E731
    decl_extra = lambda c: len((c.get("declarations") or {}).get("extra") or [])  # noqa: E731
    rates = [c["core_success_rate"] for c in latest.values() if isinstance(c.get("core_success_rate"), (int, float)) and not isinstance(c.get("core_success_rate"), bool)]
    return {
        "tasks": len(latest),
        "core_success_rate_avg": round(sum(rates) / len(rates), 4) if rates else None,
        "page_offset_tasks": sum(1 for c in latest.values() if (c.get("page_offset") or {}).get("flag")),
        "copy_conflict_total": sum(len(c.get("copy_conflicts") or []) for c in latest.values()),
        "declarations_missing_total": sum(decl_missing(c) for c in latest.values()),
        "declarations_extra_total": sum(decl_extra(c) for c in latest.values()),
    }
