"""Shared loaders for ops-diagnosis crunch scripts. Pure stdlib, no LLM calls.

Event files are whatever the agent saved from ops_get_run_events MCP responses:
a JSON object {"events": [...]}, a bare JSON list, or JSONL (one event per line).
All loaders normalize to a list of event dicts with run8 (run_id[:8]) attached.
"""

from __future__ import annotations

import json
import os
import re
import sys

# ── failure signature table (single source of truth for this skill; the
# FailureStreakMiddleware classifier config points here too — keep in sync
# with references/failure-signatures.md) ──
FAILURE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("python traceback", re.compile(r"Traceback \(most recent call last\)")),
    ("can't open file", re.compile(r"can't open file")),
    ("no such file or directory", re.compile(r"No such file or directory")),
    ("argparse misuse", re.compile(r"error: (unrecognized arguments|invalid choice|the following arguments are required)")),
    ("unsafe absolute path (sandbox guard)", re.compile(r"Error: Unsafe absolute paths")),
    ("file not found (read_file)", re.compile(r"Error: File not found")),
    ("present_files path violation", re.compile(r"Error: Only files in /mnt/user-data/outputs can be presented")),
]

# Explicitly NOT failures (see references/failure-signatures.md):
#   bare "Exit Code: 1"/"Exit Code: 2" — grep no-match / probing is normal work
#   "Exit Code: 3"                     — bid-proposal-writing: completed-with-anomalies
#   "appears to be a binary file"      — informational notice
NOT_FAILURE_PATTERNS = [
    re.compile(r"appears to be a binary file"),
]


def load_events(path: str) -> list[dict]:
    """Load one events file ({"events":[...]} | [...] | JSONL) into event dicts."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    events: list | None = None
    try:
        parsed = json.loads(text)
        events = parsed.get("events") if isinstance(parsed, dict) else parsed
    except (ValueError, TypeError):
        events = None
    if events is None:
        try:
            events = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
        except ValueError as e:
            raise SystemExit(f"error: {path} is not valid JSON ({e}) — 重新用 MCP 工具原始输出整体覆写该文件,不要手工转写") from e
    for ev in events:
        rid = ev.get("run_id") or ""
        ev["run8"] = rid[:8] if rid else "?"
    return events


def iter_event_files(events_dir: str):
    """Yield (filename, events) for every .json/.jsonl under events_dir, sorted by name."""
    if not os.path.isdir(events_dir):
        print(f"error: events dir not found: {events_dir}", file=sys.stderr)
        sys.exit(2)
    for fname in sorted(os.listdir(events_dir)):
        if fname.endswith((".json", ".jsonl")):
            yield fname, load_events(os.path.join(events_dir, fname))


def tool_result_text(ev: dict) -> str:
    """Extract the tool output text from an llm.tool.result event's content."""
    content = ev.get("content", "")
    if not isinstance(content, str):
        return json.dumps(content, ensure_ascii=False)
    try:
        parsed = json.loads(content)
    except (ValueError, TypeError):
        return content
    if isinstance(parsed, dict):
        if parsed.get("status") == "error":
            return "[status=error] " + str(parsed.get("content", ""))
        return str(parsed.get("content", content))
    return content


def classify_failure(ev: dict) -> str | None:
    """Return the failure signature for an event, or None if not a failure.

    Counted: run.error events; tool results with status=error or a hard-error
    signature. Not counted: bare Exit Code 1/2, Exit Code 3 (bid contract:
    completed-with-anomalies), informational notices.
    """
    et = ev.get("event_type", "")
    if et == "run.error":
        return "run.error"
    if et != "llm.tool.result":
        return None
    text = tool_result_text(ev)
    if any(p.search(text) for p in NOT_FAILURE_PATTERNS) and "[status=error]" not in text:
        # informational notice text — not a failure by itself
        if not any(p.search(text) for _, p in FAILURE_PATTERNS):
            return None
    if text.startswith("[status=error]"):
        return "tool status=error"
    for sig, pattern in FAILURE_PATTERNS:
        if pattern.search(text):
            return sig
    return None


def tool_calls_of(ev: dict) -> list[dict]:
    """Extract tool_calls [{name,args}] from an llm.ai.response event."""
    content = ev.get("content", "")
    try:
        parsed = json.loads(content) if isinstance(content, str) else content
    except (ValueError, TypeError):
        return []
    if isinstance(parsed, dict):
        return parsed.get("tool_calls") or []
    return []


def call_signature(name: str, args: dict) -> str:
    """One-line signature of a tool call for sequence folding (first line of command, path, or query)."""
    if name == "bash":
        cmd = str(args.get("command", ""))
        lines = [l for l in cmd.splitlines() if l.strip()]
        return (lines[0][:110] if lines else cmd[:110]) or "(empty)"
    for field in ("path", "pattern", "glob", "query", "url", "cmd"):
        if args.get(field):
            return str(args[field])[:110]
    return "(no key arg)"
