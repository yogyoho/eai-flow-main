"""Targeted unit tests for editor_mcp.py fixes — validates input schema, string parsing, and defensive guards."""
import asyncio
import hashlib
import json
import os
import tempfile
from pathlib import Path

from app.extensions.docmgr.editor_mcp import _apply_operation, handle_edit_document

PASSED = 0
FAILED = 0


async def test(name: str, args: dict, expected_error: str | None = None) -> None:
    global PASSED, FAILED
    result = await handle_edit_document(args)
    text = result[0].text
    data = json.loads(text)

    if expected_error:
        if data.get("error") == expected_error:
            PASSED += 1
            print(f"  PASS: {name}")
        else:
            FAILED += 1
            print(f"  FAIL: {name} — expected error {expected_error}, got {data.get('error')}: {data.get('detail', '')}")
    elif data.get("success"):
        PASSED += 1
        print(f"  PASS: {name}")
    else:
        FAILED += 1
        print(f"  FAIL: {name} — unexpected error: {data.get('error')}: {data.get('detail', '')}")


def _make_test_file() -> Path:
    """Create a temp file with known content and monkey-patch _resolve_path to use it."""
    import app.extensions.docmgr.editor_mcp as mcp_module
    content = "Hello World! This is a test document."
    fd, path = tempfile.mkstemp(suffix=".md", prefix="test-editor-mcp-")
    os.close(fd)
    p = Path(path)
    p.write_text(content, encoding="utf-8")
    mcp_module._resolve_path = lambda tid, rp: p
    return p


async def run() -> bool:
    print("=== editor_mcp.py targeted tests ===\n")

    _make_test_file()

    # 1 — Proper operations list (happy path)
    await test("proper operations list", {
        "operations": [{"action": "replace", "from": 0, "to": 5, "text": "Hi"}],
        "thread_id": "t1", "rel_path": "test.md",
    })

    # 2 — JSON string operations (AI wrongly serializes array as string)
    await test("JSON string operations", {
        "operations": json.dumps([{"action": "replace", "from": 0, "to": 5, "text": "Hi"}]),
        "thread_id": "t1", "rel_path": "test.md",
    })

    # 3 — Empty list → EMPTY_OPERATIONS
    await test("empty operations list", {
        "operations": [], "thread_id": "t1", "rel_path": "test.md",
    }, expected_error="EMPTY_OPERATIONS")

    # 4 — Empty string → INVALID_OPERATIONS
    await test("empty string operations", {
        "operations": "", "thread_id": "t1", "rel_path": "test.md",
    }, expected_error="INVALID_OPERATIONS")

    # 5 — Integer → INVALID_OPERATIONS
    await test("integer operations", {
        "operations": 42, "thread_id": "t1", "rel_path": "test.md",
    }, expected_error="INVALID_OPERATIONS")

    # 6 — Malformed JSON string → INVALID_OPERATIONS
    await test("malformed JSON string", {
        "operations": "[not json]", "thread_id": "t1", "rel_path": "test.md",
    }, expected_error="INVALID_OPERATIONS")

    # 7 — Mixed list with non-dict item → INVALID_OPERATION
    await test("non-dict operation item", {
        "operations": [{"action": "insert", "position": 0, "text": "ok"}, "not-a-dict"],
        "thread_id": "t1", "rel_path": "test.md",
    }, expected_error="INVALID_OPERATION")

    # 8 — Insert operation
    await test("insert operation", {
        "operations": [{"action": "insert", "position": 5, "text": "XXX"}],
        "thread_id": "t1", "rel_path": "test.md",
    })

    # 9 — Delete operation with valid range
    await test("delete operation", {
        "operations": [{"action": "delete", "from": 0, "to": 5}],
        "thread_id": "t1", "rel_path": "test.md",
    })

    # 10 — Review operation (does not modify file)
    await test("review operation", {
        "operations": [{"action": "review", "from": 0, "to": 10, "comment": "good", "severity": "info"}],
        "thread_id": "t1", "rel_path": "test.md",
    })

    print(f"\n=== Results: {PASSED} passed, {FAILED} failed ===")
    return FAILED == 0


if __name__ == "__main__":
    exit(0 if asyncio.run(run()) else 1)
