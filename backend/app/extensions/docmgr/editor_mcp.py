"""Document Editor MCP Server — editor manipulation tools for docmgr agent.

Tools accept `thread_id` + `rel_path` and resolve the absolute file path
via deerflow `Paths`. Registered as stdio MCP server "docmgr-editor-tools".
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool


# ── helpers ────────────────────────────────────────────────────────────────


def _ok(payload: dict | list) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))]


def _resolve_path(thread_id: str, rel_path: str) -> Path:
    """Resolve (thread_id, rel_path) → absolute path on disk.

    Autodetects user_id by scanning user directories when the hard-coded
    ``"default"`` user does not contain the requested thread_id.
    """
    from deerflow.config.paths import Paths

    paths = Paths()

    # Find the user directory that contains this thread_id.
    def _try_resolve(uid: str) -> Path | None:
        td = paths.thread_dir(thread_id, user_id=uid)
        p = (td / "user-data" / "outputs" / rel_path).resolve()
        if not str(p).startswith(str(td.resolve())):
            return None
        if not p.exists():
            return None  # directory may get auto-created, so check file existence
        return p

    # Fast path: default user (works in no-auth mode).
    resolved = _try_resolve("default")
    if resolved is not None:
        return resolved

    # Scan all user directories for the thread.
    users_root = paths.base_dir / "users"
    if users_root.exists():
        for user_dir in users_root.iterdir():
            if not user_dir.is_dir():
                continue
            resolved = _try_resolve(user_dir.name)
            if resolved is not None:
                return resolved

    # Fall back to default for a clear error message.
    fallback = paths.thread_dir(thread_id, user_id="default")
    return (fallback / "user-data" / "outputs" / rel_path).resolve()


def _apply_operation(content: str, op: dict) -> tuple[str, dict | None]:
    """Apply one edit operation. Returns (new_content, result_dict)."""
    action = op.get("action", "")
    result: dict | None = None

    if action == "insert":
        pos = op.get("position", 0)
        text = op.get("text", "")
        if pos < 0 or pos > len(content):
            raise ValueError(f"insert position {pos} out of range [0, {len(content)}]")
        content = content[:pos] + text + content[pos:]
        result = {"action": "insert", "position": pos, "text": text, "length": len(text)}

    elif action == "delete":
        f, t = op.get("from", 0), op.get("to", 0)
        if f < 0 or t > len(content) or f >= t:
            raise ValueError(f"delete range [{f}, {t}] invalid for len {len(content)}")
        deleted = content[f:t]
        content = content[:f] + content[t:]
        result = {"action": "delete", "from": f, "to": t, "deleted_text": deleted}

    elif action == "replace":
        f, t = op.get("from", 0), op.get("to", 0)
        text = op.get("text", "")
        if f < 0 or t > len(content) or f > t:
            raise ValueError(f"replace range [{f}, {t}] invalid for len {len(content)}")
        old = content[f:t]
        content = content[:f] + text + content[t:]
        result = {"action": "replace", "from": f, "to": t, "old_text": old, "new_text": text}

    elif action == "format":
        f, t = op.get("from", 0), op.get("to", 0)
        text = op.get("text", "")
        if f < 0 or t > len(content) or f > t:
            raise ValueError(f"format range [{f}, {t}] invalid for len {len(content)}")
        old = content[f:t]
        content = content[:f] + text + content[t:]
        result = {"action": "format", "from": f, "to": t, "old_text": old, "new_text": text}

    elif action == "review":
        result = {
            "action": "review",
            "from": op.get("from", 0),
            "to": op.get("to", 0),
            "comment": op.get("comment", ""),
            "severity": op.get("severity", "info"),
            "clause_ref": op.get("clause_ref", ""),
        }

    elif action == "compute":
        result = {
            "action": "compute",
            "expression": op.get("expression", ""),
            "result": op.get("result", ""),
        }

    else:
        raise ValueError(f"Unknown action: {action}")

    return content, result


# ── tool definitions ───────────────────────────────────────────────────────

TOOLS = [
    Tool(
        name="read_document",
        description="读取指定线程 outputs/ 目录下的文档内容。thread_id: 线程ID, rel_path: outputs下的相对路径。",
        inputSchema={
            "type": "object",
            "properties": {
                "thread_id": {"type": "string", "description": "文档所在线程ID"},
                "rel_path": {"type": "string", "description": "outputs下的相对路径, 如 'doc.md'"},
            },
            "required": ["thread_id", "rel_path"],
        },
    ),
    Tool(
        name="edit_document",
        description=(
            "对文档执行批量编辑操作。operations 是一个 JSON 数组，按顺序执行。\n\n"
            "每个操作对象包含 action 字段和对应参数：\n"
            "- {\"action\":\"insert\", \"position\": 0, \"text\": \"新增内容\"}\n"
            "- {\"action\":\"delete\", \"from\": 5, \"to\": 10}\n"
            "- {\"action\":\"replace\", \"from\": 5, \"to\": 10, \"text\": \"替换后的文字\"}\n"
            "- {\"action\":\"format\", \"from\": 5, \"to\": 10, \"text\": \"格式化后的文字\"}\n"
            "- {\"action\":\"review\", \"from\": 5, \"to\": 10, \"comment\": \"审核意见\", \"severity\": \"info\"}\n"
            "- {\"action\":\"compute\", \"expression\": \"1+1\", \"result\": \"2\"}\n\n"
            "规则:\n"
            "- insert/delete/replace/format 会实际修改文件内容\n"
            "- review/compute 不会修改文件，只产生标注\n"
            "- 所有偏移量 (position/from/to) 基于当前文档内容的字符位置\n"
            "- severity 可选值: \"info\" | \"warning\" | \"error\"\n"
            "- clause_ref 为可选的规程条款引用，如 \"煤矿安全规程第135条\""
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "operations": {
                    "type": "array",
                    "description": "编辑操作列表，每个元素是一个包含 action 和对应参数的对象",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "description": "操作类型: insert | delete | replace | format | review | compute"},
                            "position": {"type": "integer", "description": "插入位置(字符偏移)，仅 insert 需要"},
                            "from": {"type": "integer", "description": "起始位置(字符偏移)，delete/replace/format/review 需要"},
                            "to": {"type": "integer", "description": "结束位置(字符偏移)，delete/replace/format/review 需要"},
                            "text": {"type": "string", "description": "文本内容，insert/replace/format 需要"},
                            "comment": {"type": "string", "description": "审核意见，仅 review 需要"},
                            "severity": {"type": "string", "enum": ["info", "warning", "error"], "description": "严重程度，仅 review 需要"},
                            "clause_ref": {"type": "string", "description": "规程条款引用，仅 review 可选"},
                            "expression": {"type": "string", "description": "计算表达式，仅 compute 需要"},
                            "result": {"type": "string", "description": "计算结果，仅 compute 需要"},
                        },
                        "required": ["action"],
                    },
                },
                "thread_id": {"type": "string", "description": "文档所在线程ID"},
                "rel_path": {"type": "string", "description": "outputs下的相对路径"},
            },
            "required": ["operations", "thread_id", "rel_path"],
        },
    ),
    Tool(
        name="review_document",
        description="批量审核批注。不修改文件。每条: {from, to, comment, severity, clause_ref}。",
        inputSchema={
            "type": "object",
            "properties": {
                "comments": {
                    "type": "array",
                    "description": "审核批注列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "from": {"type": "integer"},
                            "to": {"type": "integer"},
                            "comment": {"type": "string"},
                            "severity": {"type": "string", "default": "info"},
                            "clause_ref": {"type": "string"},
                        },
                        "required": ["from", "to", "comment"],
                    },
                },
                "thread_id": {"type": "string", "description": "文档所在线程ID"},
                "rel_path": {"type": "string", "description": "outputs下的相对路径"},
            },
            "required": ["comments", "thread_id", "rel_path"],
        },
    ),
]


# ── handlers ───────────────────────────────────────────────────────────────


async def handle_read_document(arguments: dict) -> list[TextContent]:
    thread_id = arguments["thread_id"]
    rel_path = arguments["rel_path"]
    try:
        path = _resolve_path(thread_id, rel_path)
    except ValueError as e:
        return _ok({"success": False, "error": "SECURITY_ERROR", "detail": str(e)})

    if not path.exists():
        return _ok({"success": False, "error": "FILE_NOT_FOUND", "detail": str(path)})
    if not path.is_file():
        return _ok({"success": False, "error": "NOT_A_FILE", "detail": str(path)})

    content = path.read_text(encoding="utf-8")
    return _ok({
        "success": True,
        "thread_id": thread_id,
        "rel_path": rel_path,
        "content": content,
        "line_count": len(content.split("\n")),
        "char_count": len(content),
    })


async def handle_edit_document(arguments: dict) -> list[TextContent]:
    thread_id = arguments["thread_id"]
    rel_path = arguments["rel_path"]
    raw_ops = arguments.get("operations", [])
    # Guard: some models may pass a JSON string instead of a list
    if isinstance(raw_ops, str):
        try:
            raw_ops = json.loads(raw_ops)
        except json.JSONDecodeError:
            return _ok({"success": False, "error": "INVALID_OPERATIONS", "detail": "operations must be a JSON array, not a string"})
    if not isinstance(raw_ops, list):
        return _ok({"success": False, "error": "INVALID_OPERATIONS", "detail": "operations must be a JSON array"})
    if not raw_ops:
        return _ok({"success": False, "error": "EMPTY_OPERATIONS"})
    operations: list[dict] = raw_ops

    try:
        path = _resolve_path(thread_id, rel_path)
    except ValueError as e:
        return _ok({"success": False, "error": "SECURITY_ERROR", "detail": str(e)})
    if not path.exists():
        return _ok({"success": False, "error": "FILE_NOT_FOUND"})
    if not path.is_file():
        return _ok({"success": False, "error": "NOT_A_FILE"})

    content = path.read_text(encoding="utf-8")
    results: list[dict] = []
    file_modified = False

    for i, op in enumerate(operations):
        if not isinstance(op, dict):
            return _ok({"success": False, "error": "INVALID_OPERATION", "detail": f"Operation {i} is not an object: {type(op).__name__}"})
        try:
            content, result = _apply_operation(content, op)
            if result:
                result["_index"] = i
                results.append(result)
            # EAI-CUSTOM: append also modifies the file
            if op.get("action") in ("insert", "delete", "replace", "format", "append"):
                file_modified = True
        except (ValueError, TypeError, AttributeError) as e:
            return _ok({"success": False, "error": "INVALID_OPERATION", "detail": f"Op {i}: {e}", "results": results})

    if file_modified:
        path.write_text(content, encoding="utf-8")

    return _ok({"success": True, "operations_count": len(operations), "file_updated": file_modified, "results": results})


async def handle_review_document(arguments: dict) -> list[TextContent]:
    thread_id = arguments["thread_id"]
    rel_path = arguments["rel_path"]
    comments: list[dict] = arguments.get("comments", [])
    if not comments:
        return _ok({"success": False, "error": "EMPTY_COMMENTS"})

    try:
        path = _resolve_path(thread_id, rel_path)
    except ValueError as e:
        return _ok({"success": False, "error": "SECURITY_ERROR", "detail": str(e)})
    if not path.exists():
        return _ok({"success": False, "error": "FILE_NOT_FOUND"})
    if not path.is_file():
        return _ok({"success": False, "error": "NOT_A_FILE"})

    content = path.read_text(encoding="utf-8")
    validated: list[dict] = []
    for i, c in enumerate(comments):
        f, t = c.get("from", 0), c.get("to", 0)
        if f < 0 or t > len(content) or f >= t:
            return _ok({"success": False, "error": "INVALID_OFFSET", "detail": f"Comment {i} range [{f},{t}] invalid"})
        validated.append({
            "action": "review",
            "from": f, "to": t,
            "comment": c.get("comment", ""),
            "severity": c.get("severity", "info"),
            "clause_ref": c.get("clause_ref", ""),
        })

    return _ok({"success": True, "comments_added": len(validated), "comments": validated, "file_modified": False})


# ── server ─────────────────────────────────────────────────────────────────

server = Server("docmgr-editor-tools")


@server.list_tools()
async def list_tools():
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    handlers = {
        "read_document": handle_read_document,
        "edit_document": handle_edit_document,
        "review_document": handle_review_document,
    }
    handler = handlers.get(name)
    if not handler:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    return await handler(arguments)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
