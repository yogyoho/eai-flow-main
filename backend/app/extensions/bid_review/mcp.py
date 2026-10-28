"""bid_review MCP server(Task 11)——七工具供对话 agent 调用,**无确认门**。

照 contract_price/mcp.py 模式:裸 mcp.server.Server + _run_in_db 短连接引擎,只读为主
(feedback 为唯一写通道,且不触基线确认)。七工具:
  bid_review_start(mode, tender_doc_note, bid_doc_note)  建任务,返回任务 id+工作台链接
  bid_review_status(task_id)                             状态+progress
  bid_review_issues(task_id, severity?, layer?)          问题列表(可过滤)
  bid_review_issue(issue_id)                             问题详情(含 evidence)
  bid_review_feedback(issue_id, action, new_severity?, note?)  复核反馈(误报回流同工作台语义)
  bid_review_baseline_get(task_id)                       基线只读(不提供 confirm)
  bid_review_rulepacks()                                 规则包清单

鉴权边界(translation/mcp.py R7 同款):stdio 子进程无用户身份 → 七工具一律按服务级
owner(MCP_OWNER)隔离——工作台 UI 建的任务对 MCP 不可见,反之亦然;基线人工确认门
只在工作台 UI,agent 不可代确认(plan Task 11 契约 + Task 15 收紧)。
"""

from __future__ import annotations

import asyncio
import json
import os

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

MCP_OWNER = "mcp-bid-review"  # stdio 无身份 → 服务级 owner(UI 任务互相隔离)
WORKBENCH_URL = "/bid-review"
RULEPACK_NAME = "bid-review-core"

_FEEDBACK_ACTIONS = ("confirm", "false_positive", "severity_change")
_SEVERITIES = ("fatal", "major", "minor", "info")


async def _resolve_db_url() -> str:
    if os.environ.get("BID_REVIEW_QUERY_DB_URL"):
        return os.environ["BID_REVIEW_QUERY_DB_URL"]
    from app.extensions.config import get_extensions_config

    return get_extensions_config().database.url


async def _run_in_db(func):
    """Run func(session) against the extensions DB with a short-lived engine."""
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    engine = create_async_engine(await _resolve_db_url(), pool_size=2, max_overflow=0)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            return await func(session)
    finally:
        await engine.dispose()


def _ok(payload: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))]


# ── tools 注册表(dict[str, Tool];键=工具名,测试断言"confirm 不在任何键中")──

TOOLS: dict[str, Tool] = {
    "bid_review_start": Tool(
        name="bid_review_start",
        description=("创建一条投标方案审查任务(quick=快审直跑;deep=基线人工确认后跑),返回任务 id 与工作台链接。文档经聊天上传由用户先传,注记材料名称即可;任务文档的正式挂接在工作台完成。基线确认门在工作台 UI,agent 不可代确认。"),
        inputSchema={
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["quick", "deep"], "description": "quick=快审;deep=先出基线停确认门"},
                "tender_doc_note": {"type": "string", "description": "招标文件名称/说明(注记)"},
                "bid_doc_note": {"type": "string", "description": "投标文件名称/说明(注记)"},
            },
            "required": [],
        },
    ),
    "bid_review_status": Tool(
        name="bid_review_status",
        description="查询投标审查任务状态与进度(created/parsing/extracting/awaiting_confirm/running/done/failed + progress 百分比)。",
        inputSchema={"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]},
    ),
    "bid_review_issues": Tool(
        name="bid_review_issues",
        description="列出某投标审查任务的全部问题,可按 severity(fatal/major/minor/info)与 layer(L1/L2/L3/L4)过滤。",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "severity": {"type": "string", "enum": list(_SEVERITIES)},
                "layer": {"type": "string", "enum": ["L1", "L2", "L3", "L4"]},
            },
            "required": ["task_id"],
        },
    ),
    "bid_review_issue": Tool(
        name="bid_review_issue",
        description="查询单条审查问题详情:判定、证据锚点(文档/页码/摘录)、修复建议。",
        inputSchema={"type": "object", "properties": {"issue_id": {"type": "string"}}, "required": ["issue_id"]},
    ),
    "bid_review_feedback": Tool(
        name="bid_review_feedback",
        description="对一条审查问题做人工复核反馈:false_positive=误报 / severity_change=改级(需 new_severity) / confirm=认可;误报与认可回流规则包统计。",
        inputSchema={
            "type": "object",
            "properties": {
                "issue_id": {"type": "string"},
                "action": {"type": "string", "enum": list(_FEEDBACK_ACTIONS)},
                "new_severity": {"type": "string", "enum": list(_SEVERITIES), "description": "action=severity_change 时必填"},
                "note": {"type": "string"},
            },
            "required": ["issue_id", "action"],
        },
    ),
    "bid_review_baseline_get": Tool(
        name="bid_review_baseline_get",
        description="只读拉取某任务的基线包(逐份材料:kind/字段快照/确认状态)。只读;确认操作在工作台 UI,不提供于此。",
        inputSchema={"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]},
    ),
    "bid_review_rulepacks": Tool(
        name="bid_review_rulepacks",
        description="列出规则包(名称/版本/规则清单/误报-认可统计),供 agent 向用户解释审查口径。",
        inputSchema={"type": "object", "properties": {}},
    ),
}


# ── handlers ──────────────────────────────────────────────────────────


async def _handle_start(arguments: dict) -> list[TextContent]:
    from app.extensions.bid_review import crud

    mode = str(arguments.get("mode") or "quick")
    if mode not in ("quick", "deep"):
        return _ok({"success": False, "message": "mode 仅支持 quick|deep"})

    async def _q(session):
        task = await crud.create_task(session, owner_id=MCP_OWNER, mode=mode)
        meta = dict(task.engine_meta or {})
        meta["tender_doc_note"] = str(arguments.get("tender_doc_note") or "")
        meta["bid_doc_note"] = str(arguments.get("bid_doc_note") or "")
        task.engine_meta = meta  # 重新赋值以标记 JSON 列 dirty
        await session.commit()
        await session.refresh(task)
        return task

    task = await _run_in_db(_q)
    return _ok(
        {
            "success": True,
            "task_id": task.id,
            "status": task.status,
            "mode": task.mode,
            "workbench_url": WORKBENCH_URL,
            "message": "任务已建。请引导用户在工作台上传招标/投标文档并跟进进度(bid_review_status);基线确认门在工作台 UI,agent 不可代确认。",
        }
    )


async def _get_task(session, task_id: str):
    from app.extensions.bid_review import crud

    return await crud.get_task(session, task_id=task_id, owner_id=MCP_OWNER)


async def _handle_status(arguments: dict) -> list[TextContent]:
    task_id = str(arguments.get("task_id") or "")
    task = await _run_in_db(lambda s: _get_task(s, task_id))
    if task is None:
        return _ok({"success": False, "message": f"任务不存在或不可见: {task_id}"})
    return _ok(
        {
            "success": True,
            "id": task.id,
            "status": task.status,
            "mode": task.mode,
            "progress": task.progress,
            "error": task.error,
            "workbench_url": WORKBENCH_URL,
            "engine_meta": {k: v for k, v in (task.engine_meta or {}).items() if k != "docs"},
        }
    )


async def _handle_issues(arguments: dict) -> list[TextContent]:
    from sqlalchemy import select

    from app.extensions.bid_review.models import ReviewIssue, ReviewTask

    task_id = str(arguments.get("task_id") or "")
    severity, layer = arguments.get("severity"), arguments.get("layer")
    if severity is not None and severity not in _SEVERITIES:
        return _ok({"success": False, "message": f"severity 仅支持 {_SEVERITIES}"})
    if layer is not None and layer not in ("L1", "L2", "L3", "L4"):
        return _ok({"success": False, "message": "layer 仅支持 L1|L2|L3|L4"})

    async def _q(session):
        if await _get_task(session, task_id) is None:
            return None
        stmt = select(ReviewIssue).join(ReviewTask, ReviewIssue.task_id == ReviewTask.id).where(ReviewIssue.task_id == task_id, ReviewTask.owner_id == MCP_OWNER).order_by(ReviewIssue.created_at, ReviewIssue.id)
        return list((await session.execute(stmt)).scalars().all())

    rows = await _run_in_db(_q)
    if rows is None:
        return _ok({"success": False, "message": f"任务不存在或不可见: {task_id}"})
    filtered = [i for i in rows if (not severity or i.severity == severity) and (not layer or i.layer == layer)]
    return _ok(
        {
            "success": True,
            "task_id": task_id,
            "count": len(filtered),
            "issues": [
                {
                    "id": i.id,
                    "rule_id": i.rule_id,
                    "layer": i.layer,
                    "severity": i.severity,
                    "verdict": i.verdict,
                    "need_human": i.need_human,
                    "message": i.message,
                    "fix": i.fix,
                    "evidence_count": len(i.evidence or []),
                }
                for i in filtered
            ],
            "workbench_url": WORKBENCH_URL,
        }
    )


async def _handle_issue(arguments: dict) -> list[TextContent]:
    from app.extensions.bid_review import crud

    issue_id = str(arguments.get("issue_id") or "")

    async def _q(session):
        return await crud.get_issue(session, issue_id=issue_id, owner_id=MCP_OWNER)

    issue = await _run_in_db(_q)
    if issue is None:
        return _ok({"success": False, "message": f"问题不存在或不可见: {issue_id}"})
    return _ok(
        {
            "success": True,
            "id": issue.id,
            "task_id": issue.task_id,
            "rule_id": issue.rule_id,
            "layer": issue.layer,
            "severity": issue.severity,
            "verdict": issue.verdict,
            "clause_id": issue.clause_id,
            "message": issue.message,
            "fix": issue.fix,
            "evidence": issue.evidence,
            "need_human": issue.need_human,
            "confidence": issue.confidence,
            "workbench_url": WORKBENCH_URL,
        }
    )


async def _handle_feedback(arguments: dict) -> list[TextContent]:
    from app.extensions.bid_review import crud

    issue_id = str(arguments.get("issue_id") or "")
    action = str(arguments.get("action") or "")
    new_severity = arguments.get("new_severity")
    note = str(arguments.get("note") or "")
    if action not in _FEEDBACK_ACTIONS:
        return _ok({"success": False, "message": f"action 仅支持 {_FEEDBACK_ACTIONS}"})
    if action == "severity_change" and new_severity not in _SEVERITIES:
        return _ok({"success": False, "message": f"action=severity_change 需 new_severity ∈ {_SEVERITIES}"})

    async def _q(session):
        issue = await crud.get_issue(session, issue_id=issue_id, owner_id=MCP_OWNER)
        if issue is None:
            return None
        fb = await crud.record_feedback(session, issue_id=issue_id, owner_id=MCP_OWNER, action=action, new_severity=new_severity, note=note)
        if action == "false_positive":
            # Task 16:误报回流与工作台同一语义(verdict/need_human 落库 + fp+1 +
            # fp_samples 滚动),共用 routers.apply_false_positive(懒 import,stdio 启动轻量)。
            from app.extensions.bid_review.routers import apply_false_positive

            await apply_false_positive(session, issue)
        elif action == "confirm":
            await crud.add_rulepack_stats(session, RULEPACK_NAME, issue.rule_id, adopted=True)
        return fb

    fb = await _run_in_db(_q)
    if fb is None:
        return _ok({"success": False, "message": f"问题不存在或不可见: {issue_id}"})
    return _ok({"success": True, "feedback_id": fb.id, "issue_id": issue_id, "action": action})


async def _handle_baseline_get(arguments: dict) -> list[TextContent]:
    from app.extensions.bid_review import crud

    task_id = str(arguments.get("task_id") or "")

    async def _q(session):
        task = await _get_task(session, task_id)
        if task is None:
            return None
        return await crud.list_baselines(session, task_id=task_id, owner_id=MCP_OWNER)

    baselines = await _run_in_db(_q)
    if baselines is None:
        return _ok({"success": False, "message": f"任务不存在或不可见: {task_id}"})
    return _ok(
        {
            "success": True,
            "task_id": task_id,
            "baselines": [{"id": b.id, "kind": b.kind, "confirmed": b.confirmed, "payload": b.payload} for b in baselines],
            "note": "只读;确认门在工作台 UI(agent 不可代确认)。",
            "workbench_url": WORKBENCH_URL,
        }
    )


async def _handle_rulepacks(arguments: dict) -> list[TextContent]:
    from sqlalchemy import select

    from app.extensions.bid_review.engine.rule_runner import load_rulepack
    from app.extensions.bid_review.models import RulePackMeta
    from app.extensions.bid_review.worker import RULEPACK_PATH

    pack = load_rulepack(RULEPACK_PATH)

    async def _q(session):
        result = await session.execute(select(RulePackMeta).where(RulePackMeta.name == pack.name))
        return result.scalar_one_or_none()

    meta = await _run_in_db(_q)
    return _ok(
        {
            "success": True,
            "items": [
                {
                    "name": pack.name,
                    "version": pack.version,
                    "rule_count": len(pack.rules),
                    "rules": [{"id": r.id, "name": r.name, "layer": r.layer, "severity": r.severity, "type": r.type} for r in pack.rules],
                    "stats": dict(meta.stats or {}) if meta else {},
                    "enabled": bool(meta.enabled) if meta else True,
                }
            ],
        }
    )


_HANDLERS = {
    "bid_review_start": _handle_start,
    "bid_review_status": _handle_status,
    "bid_review_issues": _handle_issues,
    "bid_review_issue": _handle_issue,
    "bid_review_feedback": _handle_feedback,
    "bid_review_baseline_get": _handle_baseline_get,
    "bid_review_rulepacks": _handle_rulepacks,
}


async def handle_call(name: str, arguments: dict) -> list[TextContent]:
    """工具分发(测试直调入口;stdio call_tool 委托到这里)。"""
    if name not in TOOLS or name not in _HANDLERS:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    try:
        return await _HANDLERS[name](arguments or {})
    except Exception as exc:  # noqa: BLE001
        return _ok({"success": False, "message": f"{type(exc).__name__}: {exc}"})


# ── server ──

server = Server("bid-review")


@server.list_tools()
async def list_tools():
    return list(TOOLS.values())


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    return await handle_call(name, arguments)


async def arun():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    asyncio.run(arun())


if __name__ == "__main__":
    main()
