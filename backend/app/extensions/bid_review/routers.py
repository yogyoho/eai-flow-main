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
  GET  /tasks/{id}/report      审查报告导出 ?format=md(Task 21;首行免责声明+可提交判定
                               提示行+severity 分节;html 导出属 M4 不做,422)
  GET  /rulepacks              规则包清单(生产规则包 + DB stats)

owner 隔离:模块级 ``current_owner`` 依赖(必须模块级函数,dependency_overrides 才能打桩),
内部与 contract_price/routers.py 同一登录依赖(require_permission),取 bridged
CurrentUser.id 作 owner_id,全列表端点 owner 过滤。
"""

import asyncio
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import require_permission
from app.extensions.bid_review import crud, parse, worker
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
    """创建审查任务(multipart 上传 tender+bid 文档)。EAI-CUSTOM(2026-10-30 解析层,
    spec §2):上传字节快速落盘 raw/(原始字节不进 DB),engine_meta.docs 只存清单
    (doc_id/role/kind/size/status,全文不上 wire——D6);docx/pdf 解析+OCR 重活全部
    在 worker.advance_task 的 parsing 阶段做(worker.parse 链)。旧实现(UTF-8 硬解码
    直存,docx/pdf 出乱码)退役。随后后台直推 advance_task(quick 直跑;deep 停确认门)。"""
    if mode not in ("quick", "deep"):
        raise HTTPException(status_code=422, detail="mode 仅支持 quick|deep")
    task = await crud.create_task(db, owner_id=owner_id, mode=mode)
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


@router.get("/tasks/{task_id}/baselines")
async def list_task_baselines(task_id: str, db: AsyncSession = Depends(get_db), owner_id: str = Depends(current_owner)):
    """基线行级读端点(EAI-CUSTOM 2026-10-30,分期建议一期 s3/s4——
    docs/superpowers/specs/2026-10-30-bid-review-ui-gaps-and-completeness.md §二):
    此前字段级快照仅 MCP bid_review_baseline_get 可达,前端 HTTP 通道缺位,
    BaselineView 只能降级材料卡。行契约=_write_baselines 落库形:每行同全量
    fields 快照 + 本行 doc_id(payload)+ kind/confirmed;provenance 逐字段出处
    {doc_id,page,quote}(extract.normalize_provenance,模型没给的路径缺省不造假)。
    冲突裁定/置信度/锚点=引擎二期缺口,不在本端点承诺。"""
    if await crud.get_task(db, task_id=task_id, owner_id=owner_id) is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    rows = await crud.list_baselines(db, task_id=task_id, owner_id=owner_id)
    return {
        "items": [
            {
                "kind": r.kind,
                "doc_id": (r.payload or {}).get("doc_id"),
                "confirmed": bool(r.confirmed),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "fields": (r.payload or {}).get("fields") or {},
                "provenance": (r.payload or {}).get("provenance") or {},
                "materials_hash": (r.payload or {}).get("materials_hash") or "",
            }
            for r in rows
        ]
    }


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
    return issue


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


def _render_report_md(task, issues: list) -> str:
    """审查报告 md 渲染(plan Task 21 Step 1 契约,报告呈现形态以 plan 原文为准):
    首行免责声明 → 任务元信息(含复核耗时占位——人工复核耗时统计 v1 未接入)→
    可提交判定提示行(措辞照 ui-spec §3.5 照抄;口径=正式 fatal 违规:severity=fatal
    且 verdict=violation 且非 need_human——人工误报与待人工条目不计入命中红线)→
    按 severity 四档分节,每条含规则 ID/证据(doc+page)/修复建议;need_human 条目
    不删除,按 severity 归节并标注【待人工】;false_positive 人工误报不进正文。"""
    issues = [i for i in issues if i.verdict != "false_positive"]
    fatal_hits = [i for i in issues if i.severity == "fatal" and i.verdict == "violation" and not i.need_human]
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"> 免责声明:{REPORT_DISCLAIMER}",
        "",
        f"# 投标审查报告 {task.id[:8]}",
        "",
        f"- 任务 ID:{task.id}",
        f"- 任务状态:{task.status}",
        f"- 审查模式:{task.mode}",
        "- 复核耗时:待补充(人工复核耗时统计未接入,占位)",
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
    format 白名单只收 md——html 导出属 M4,422 拒绝不静默降级;owner 过滤同既有端点,
    Content-Disposition attachment 供浏览器直接下载。状态门(QUAL 修复):仅 done 可导,
    半程任务 409——基于空/半程 issue 集算出的可提交判定行不得冒充审查结论流出到
    非 UI 消费方(与 WorkbenchView 前端 done 门同口径)。"""
    if format != "md":
        raise HTTPException(status_code=422, detail="format 仅支持 md(html 导出属 M4)")
    task = await crud.get_task(db, task_id=task_id, owner_id=owner_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "done":
        raise HTTPException(status_code=409, detail=f"任务未完成(当前 {task.status}):仅 done 可导出报告,半程数据不构成审查结论")
    issues = await crud.list_issues(db, task_id=task_id, owner_id=owner_id)
    return Response(
        content=_render_report_md(task, issues),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="bid-review-report-{task_id[:8]}.md"'},
    )


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
                # 2026-10-30 前端工作台证据行回退:det 规则 issue 无 doc/page 证据(anchors.py 未落地),回退展示判定输入字段
                "rules": [{"id": r.id, "name": r.name, "layer": r.layer, "severity": r.severity, "type": r.type, "inputs": list(r.inputs or [])} for r in pack.rules],
                "stats": dict(meta.stats or {}) if meta else {},
                "enabled": bool(meta.enabled) if meta else True,
            }
        ]
    }
