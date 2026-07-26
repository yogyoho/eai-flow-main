# EAI-CUSTOM: document editor tools registered via config.yaml function calling.
# Replaces MCP stdio subprocess (editor_mcp.py) for lower latency.
# Tool names: read_document / edit_document / review_document (no prefix).
# Keep in sync with config.yaml tools section for these 3 tools.

"""Editor tools registered via config.yaml function calling.

Three tools: read_document, edit_document, review_document.
Each accepts thread_id + rel_path and resolves the absolute file path
via deerflow Paths (with auto user-id detection).

Registered in config.yaml:
  tools:
    - name: read_document
      group: docmgr
      use: app.extensions.docmgr.editor_tools:read_document
    ...
"""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.tools import tool


# EAI-CUSTOM: auto-detect user_id by scanning users/ directory.
# Falls back to "default" user for no-auth mode.
def _resolve_path(thread_id: str, rel_path: str) -> Path:
    """Resolve (thread_id, rel_path) -> absolute path on disk with user auto-detection."""
    from deerflow.config.paths import Paths

    paths = Paths()

    def _try(uid: str) -> Path | None:
        td = paths.thread_dir(thread_id, user_id=uid)
        p = (td / "user-data" / "outputs" / rel_path).resolve()
        if not str(p).startswith(str(td.resolve())):
            return None
        if not p.exists():
            return None
        return p

    resolved = _try("default")
    if resolved is not None:
        return resolved

    users_root = paths.base_dir / "users"
    if users_root.exists():
        for user_dir in users_root.iterdir():
            if not user_dir.is_dir():
                continue
            resolved = _try(user_dir.name)
            if resolved is not None:
                return resolved

    fallback = paths.thread_dir(thread_id, user_id="default")
    return (fallback / "user-data" / "outputs" / rel_path).resolve()


# EAI-CUSTOM: shared operation logic between old MCP server and new function calling tools.
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

    # EAI-CUSTOM: position-free append — avoids LLM offset calculation errors
    elif action == "append":
        text = op.get("text", "")
        sep = "\n" if content and not content.endswith("\n") else ""
        content = content + sep + text
        result = {"action": "append", "position": len(content) - len(text) - len(sep), "text": text, "length": len(text)}

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


# EAI-CUSTOM: eai_read_docmgr_md — read document from thread outputs/ directory.
# Registered in config.yaml as: use: app.extensions.docmgr.editor_tools:eai_read_docmgr_md
@tool
def eai_read_docmgr_md(thread_id: str, rel_path: str) -> str:
    """Read document content from a thread's outputs/ directory. Returns JSON.

    Use this tool to read the current content of a document before editing it.
    Args: thread_id (thread UUID), rel_path (path within outputs/, e.g. "doc.md")
    """
    try:
        path = _resolve_path(thread_id, rel_path)
    except ValueError as e:
        return json.dumps({"success": False, "error": "SECURITY_ERROR", "detail": str(e)})
    if not path.exists():
        return json.dumps({"success": False, "error": "FILE_NOT_FOUND", "detail": str(path)})
    if not path.is_file():
        return json.dumps({"success": False, "error": "NOT_A_FILE"})
    content = path.read_text(encoding="utf-8")
    return json.dumps({"success": True, "thread_id": thread_id, "rel_path": rel_path, "content": content, "line_count": len(content.split("\n")), "char_count": len(content)}, ensure_ascii=False)


# EAI-CUSTOM: eai_edit_docmgr_md — apply batch edit operations to a document.
# Registered in config.yaml as: use: app.extensions.docmgr.editor_tools:eai_edit_docmgr_md
@tool
def eai_edit_docmgr_md(operations: list[dict], thread_id: str, rel_path: str) -> str:
    """Modify a markdown document in a thread's outputs/ directory. Returns JSON.

    Each operation requires an "action" field. Supported actions:
    - {"action":"append", "text":"text to add at end"} — adds to end of document. NO position needed.
    - {"action":"insert", "position":NNN, "text":"text"} — inserts at character position
    - {"action":"replace", "from":NNN, "to":NNN, "text":"new text"} — replaces range
    - {"action":"delete", "from":NNN, "to":NNN} — deletes range
    - {"action":"format", "from":NNN, "to":NNN, "text":"formatted text"}
    - {"action":"review", "from":NNN, "to":NNN, "comment":"note", "severity":"info"}
    - {"action":"compute", "expression":"1+1", "result":"2"}

    IMPORTANT: Use "append" for adding text to the end. It needs NO from/to/position.
    All other actions require exact character offsets based on the document content.
    Args: operations (list of operation objects), thread_id (thread UUID), rel_path (path within outputs/)
    """
    import logging
    logger = logging.getLogger(__name__)
    # EAI-CUSTOM: accept both list and JSON string for operations
    if isinstance(operations, str):
        try:
            operations = json.loads(operations)
        except json.JSONDecodeError:
            return json.dumps({"success": False, "error": "INVALID_OPERATIONS"})
    if not isinstance(operations, list) or not operations:
        return json.dumps({"success": False, "error": "EMPTY_OPERATIONS"})
    try:
        path = _resolve_path(thread_id, rel_path)
    except ValueError as e:
        return json.dumps({"success": False, "error": "SECURITY_ERROR", "detail": str(e)})
    if not path.exists():
        return json.dumps({"success": False, "error": "FILE_NOT_FOUND"})
    if not path.is_file():
        return json.dumps({"success": False, "error": "NOT_A_FILE"})
    content = path.read_text(encoding="utf-8")
    results: list[dict] = []
    file_modified = False
    for i, op in enumerate(operations):
        if not isinstance(op, dict):
            return json.dumps({"success": False, "error": "INVALID_OPERATION", "detail": f"Operation {i} is not an object"})
        try:
            content, result = _apply_operation(content, op)
            if result:
                result["_index"] = i
                results.append(result)
            # EAI-CUSTOM: append also modifies the file
            if op.get("action") in ("insert", "delete", "replace", "format", "append"):
                file_modified = True
        except (ValueError, TypeError, AttributeError) as e:
            return json.dumps({"success": False, "error": "INVALID_OPERATION", "detail": f"Op {i}: {e}", "results": results})
    if file_modified:
        path.write_text(content, encoding="utf-8")
        logger.info("EAI eai_edit_docmgr_md: wrote %d chars to %s", len(content), str(path))
    return json.dumps({"success": True, "operations_count": len(operations), "file_updated": file_modified, "results": results}, ensure_ascii=False)


# EAI-CUSTOM: eai_review_docmgr_md — add review annotations without modifying file.
# Registered in config.yaml as: use: app.extensions.docmgr.editor_tools:eai_review_docmgr_md
@tool
def eai_review_docmgr_md(comments: list[dict], thread_id: str, rel_path: str) -> str:
    """Add review annotations to a document. Does NOT modify file. Returns JSON.

    Each comment: {from, to, comment, severity: "info"|"warning"|"error", clause_ref?}
    Args: comments (list of annotation objects), thread_id (thread UUID), rel_path (path within outputs/)
    """
    if isinstance(comments, str):
        try:
            comments = json.loads(comments)
        except json.JSONDecodeError:
            return json.dumps({"success": False, "error": "INVALID_COMMENTS"})
    if not isinstance(comments, list) or not comments:
        return json.dumps({"success": False, "error": "EMPTY_COMMENTS"})
    try:
        path = _resolve_path(thread_id, rel_path)
    except ValueError as e:
        return json.dumps({"success": False, "error": "SECURITY_ERROR", "detail": str(e)})
    if not path.exists():
        return json.dumps({"success": False, "error": "FILE_NOT_FOUND"})
    if not path.is_file():
        return json.dumps({"success": False, "error": "NOT_A_FILE"})
    content = path.read_text(encoding="utf-8")
    validated: list[dict] = []
    for i, c in enumerate(comments):
        if not isinstance(c, dict):
            continue
        f, t = c.get("from", 0), c.get("to", 0)
        if f < 0 or t > len(content) or f >= t:
            return json.dumps({"success": False, "error": "INVALID_OFFSET", "detail": f"Comment {i} range [{f},{t}] invalid"})
        validated.append({"action": "review", "from": f, "to": t, "comment": c.get("comment", ""), "severity": c.get("severity", "info"), "clause_ref": c.get("clause_ref", "")})
    return json.dumps({"success": True, "comments_added": len(validated), "comments": validated, "file_modified": False}, ensure_ascii=False)
