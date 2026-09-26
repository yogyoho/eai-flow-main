"""learnings MCP stdio server — 4 工具(surface/log_learning/stats/resolve).

EAI-CUSTOM: 自进化循环 P1(设计 docs/designs/self-improving-loop-port.md D5/D10/D14)。
身份绑定(OV2): 注册条目 cwd=null -> 平台把本子进程 cwd 锁到调用者 thread 工作区
(`{base}/users/{uid}/threads/{tid}/user-data/...`, 路径编码真实身份)。
- os.getcwd() 正则解析 (user_id, thread_id); 解析失败 fail-closed 拒绝写
- 模型传入的 thread_id 仅交叉校验, 永不信为身份来源
- `import app` 依赖 sys.path.insert(免 cwd=/app/backend, 与身份绑定互斥, bug-712)
- D14: 每个成功响应尾部带服务端拼的 [N pending | M promotion-ready] 尾注
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys

# bug-712 替代方案: cwd 被 pinned 到 thread 工作区(身份绑定前提),
# app 包导入靠显式 path(容器路径; 宿主机测试用 PYTHONPATH=. 不受影响)
_APP_BACKEND = "/app/backend"
if os.path.isdir(_APP_BACKEND) and _APP_BACKEND not in sys.path:
    sys.path.insert(0, _APP_BACKEND)

# MCP SDK 的 stdio 子进程环境是白名单制: 父进程(gateway)的 EXTENSIONS_DB_* 不会
# 自动继承。容器内 config.py 的 4 级父路径 (/app/.env) 不存在, 而 /app/backend/.env
# 存在——补一次加载(override=False, 真实 env 优先), 与 gateway 同源。
try:
    from dotenv import load_dotenv

    if os.path.isfile(f"{_APP_BACKEND}/.env"):
        load_dotenv(f"{_APP_BACKEND}/.env", override=False)
except ImportError:
    pass

from mcp.server import Server  # noqa: E402
from mcp.server.stdio import stdio_server  # noqa: E402
from mcp.types import TextContent, Tool  # noqa: E402

from app.extensions.learnings.patterns import AREAS, KINDS  # noqa: E402

_IDENTITY_RE = re.compile(r"[\\/]users[\\/]([^\\/]+)[\\/]threads[\\/]([^\\/]+)[\\/]user-data", re.IGNORECASE)

_TOOLS_SPEC = [
    (
        "surface",
        "回顾本 thread 的经验教训: 先补扫未处理的历史错误(有界), 再返回 pending 教训"
        "(按 recurrence 排序, 达晋升门槛的带 eligible_for_skill=true)。"
        "非平凡任务开工前必须先调用。",
        {
            "type": "object",
            "properties": {
                "thread_id": {"type": "string", "description": "可选交叉校验: 与运行环境身份不符将拒绝"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": [],
        },
    ),
    (
        "log_learning",
        "捕获一条教训(用户纠正/知识过时/更好做法/非显而易见的失败)。"
        "同 pattern_key 已存在时服务端自动折叠(count+1)。area/symptom 从分类法枚举选择, 服务端 canonicalize。",
        {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "maxLength": 200, "description": "一句话教训"},
                "kind": {"type": "string", "enum": list(KINDS)},
                "area": {"type": "string", "enum": list(AREAS)},
                "symptom": {"type": "string", "description": "失败形状小写连字符(如 module-not-found); 缺省用 kind 派生"},
                "details": {"type": "string", "description": "背景: 发生了什么/正确做法"},
                "suggested_action": {"type": "string", "description": "下次遇到怎么做"},
            },
            "required": ["summary", "kind", "area"],
        },
    ),
    (
        "stats",
        "教训账本统计: 按 status/kind 计数、top-pending、晋升候选(资格=recurrence>=3 且跨>=2 thread 且近30天)。",
        {"type": "object", "properties": {}, "required": []},
    ),
    (
        "resolve",
        "把教训标记为 resolved(已修复/已失效, 停止提醒)或 dismissed(误报)。",
        {
            "type": "object",
            "properties": {
                "learning_id": {"type": "string"},
                "status": {"type": "string", "enum": ["resolved", "dismissed", "pending"]},
                "note": {"type": "string"},
            },
            "required": ["learning_id"],
        },
    ),
]

TOOLS = [Tool(name=n, description=d, inputSchema=s) for n, d, s in _TOOLS_SPEC]


def _ok(payload: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))]


def _err(e: Exception) -> list[TextContent]:
    return _ok({"success": False, "error": f"{type(e).__name__}: {e}"})


def parse_identity(cwd: str | None = None) -> tuple[str, str] | None:
    """从 pinned 工作区路径解析 (user_id, thread_id); 解析失败返回 None(fail-closed)."""
    path = (cwd or os.getcwd()).replace("\\", "/")
    m = _IDENTITY_RE.search(path)
    if m is None:
        return None
    user_id, thread_id = m.group(1), m.group(2)
    if not user_id or not thread_id:
        return None
    return user_id, thread_id


async def _identity_or_error(args: dict) -> tuple[tuple[str, str] | None, dict | None]:
    identity = parse_identity()
    if identity is None:
        return None, {
            "success": False,
            "error": "identity-unavailable: 无法从运行环境推导用户身份(fail-closed), 本工具拒绝执行",
        }
    claimed = (args or {}).get("thread_id")
    if claimed and claimed != identity[1]:
        return None, {
            "success": False,
            "error": f"thread-id-mismatch: 环境身份 {identity[1]} 与传入 thread_id {claimed} 不符, 已拒绝",
        }
    return identity, None


async def _footer(user_id: str) -> str:
    from app.extensions.learnings import service

    try:
        pending, ready = await service.counts(user_id)
        return f"[{pending} pending | {ready} promotion-ready]"
    except Exception:
        return "[pending count unavailable]"


async def _surface(a: dict) -> list[TextContent]:
    identity, err = await _identity_or_error(a)
    if err:
        return _ok(err)
    user_id, thread_id = identity
    from app.extensions.learnings import service, sweeper

    sweep_note = await sweeper.catchup_thread(user_id, thread_id)
    result = await service.surface(user_id, limit=int(a.get("limit", 5)))
    return _ok({
        **result,
        "sweep": sweep_note,
        "footer": f"[{result.get('pending', 0)} pending | {result.get('promotion_ready', 0)} promotion-ready]",
    })


_KIND_DEFAULT_SYMPTOM = {
    "error": "failure",
    "correction": "correction",
    "knowledge_gap": "stale-knowledge",
    "best_practice": "better-approach",
    "feature_request": "missing-capability",
}


async def _log_learning(a: dict) -> list[TextContent]:
    identity, err = await _identity_or_error(a)
    if err:
        return _ok(err)
    user_id, thread_id = identity
    from app.extensions.learnings import service

    kind = a.get("kind", "")
    symptom = a.get("symptom") or _KIND_DEFAULT_SYMPTOM.get(kind, "failure")
    result = await service.mint_or_fold(
        user_id=user_id,
        kind=kind,
        area=a.get("area", ""),
        symptom=symptom,
        summary=a.get("summary", ""),
        details=a.get("details", ""),
        suggested_action=a.get("suggested_action", ""),
        source="agent",
        source_thread_id=thread_id,
    )
    if result.get("success"):
        result["footer"] = await _footer(user_id)
    return _ok(result)


async def _stats(a: dict) -> list[TextContent]:
    identity, err = await _identity_or_error(a)
    if err:
        return _ok(err)
    user_id, _ = identity
    from app.extensions.learnings import service

    result = await service.stats(user_id)
    result["footer"] = f"[{result.get('by_status', {}).get('pending', 0)} pending]"
    return _ok(result)


async def _resolve(a: dict) -> list[TextContent]:
    identity, err = await _identity_or_error(a)
    if err:
        return _ok(err)
    user_id, _ = identity
    from app.extensions.learnings import service

    result = await service.resolve(
        user_id,
        a["learning_id"],
        note=a.get("note", ""),
        status=a.get("status", "resolved"),
    )
    if result.get("success"):
        result["footer"] = await _footer(user_id)
    return _ok(result)


_HANDLERS = {
    "surface": _surface,
    "log_learning": _log_learning,
    "stats": _stats,
    "resolve": _resolve,
}

server = Server("learnings")


@server.list_tools()
async def list_tools():
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    handler = _HANDLERS.get(name)
    if handler is None:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    try:
        return await handler(arguments or {})
    except Exception as e:  # 结构化错误返回 agent, 不崩 server(fail-open 记日志)
        return _err(e)


async def main():
    from app.extensions.learnings import service

    try:
        await service.ensure_ready()  # 表由本子进程 create_all(gateway 不 import 本模块)
    except Exception:
        import logging

        logging.getLogger(__name__).exception("learnings: DB 初始化失败(工具调用将返回结构化错误)")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
