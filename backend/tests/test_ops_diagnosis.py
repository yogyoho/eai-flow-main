"""Tests for the ops-diagnosis extension (service queries, MCP handlers, skill scripts).

EAI-CUSTOM (route-D): covers server-side filtering / truncation / empty-state of the
ops_list_thread_runs + ops_get_run_events tools, plus the deterministic crunch
scripts shipped with skills/public/ops-diagnosis (classification truth table —
including the "Exit Code 3 is success" bid contract — sequence folding, and
per-run metrics). Fixture shapes mirror the real bfa917ce incident thread.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.extensions.ops_diagnosis import service
from app.extensions.ops_diagnosis.mcp import _handle_get_run_events, _handle_list_thread_runs
from deerflow.persistence.base import Base
from deerflow.persistence.models.run_event import RunEventRow
from deerflow.persistence.run.model import RunRow

ASYNCIO = pytest.mark.asyncio  # applied per-test: the script tests below are sync (subprocess)

T1 = "11111111-1111-1111-1111-111111111111"
T2 = "22222222-2222-2222-2222-222222222222"
R1 = "aaaaaaaa-0000-0000-0000-000000000001"
R2 = "aaaaaaaa-0000-0000-0000-000000000002"

SKILL_SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "public" / "ops-diagnosis" / "scripts"


def _tool_result(seq: int, run_id: str, text: str) -> RunEventRow:
    return RunEventRow(
        thread_id=T1,
        run_id=run_id,
        user_id="u1",
        event_type="llm.tool.result",
        category="message",
        content=json.dumps({"content": text}),
        event_metadata={},
        seq=seq,
    )


async def _make_db(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s, s.begin():
        s.add(RunRow(run_id=R1, thread_id=T1, assistant_id=None, status="success", multitask_strategy="reject", user_id="u1", model_name="m1", total_tokens=100, llm_call_count=2, message_count=3))
        s.add(RunRow(run_id=R2, thread_id=T1, assistant_id=None, status="error", multitask_strategy="reject", user_id="u1", error="boom", stop_reason=None, total_tokens=900, llm_call_count=9, message_count=10))
        # T2 run has no events at all
        s.add(RunRow(run_id="bbbbbbbb-0000-0000-0000-000000000001", thread_id=T2, assistant_id=None, status="success", multitask_strategy="reject", user_id="u2"))
        rows = [
            RunEventRow(thread_id=T1, run_id=R1, user_id="u1", event_type="run.start", category="trace", content='{"chain":"unknown"}', event_metadata={}, seq=1),
            RunEventRow(thread_id=T1, run_id=R1, user_id="u1", event_type="llm.ai.response", category="message", content='{"tool_calls":[{"name":"bash","args":{"command":"ls"}}]}', event_metadata={}, seq=2),
            _tool_result(3, R1, "total 0\nnothing here"),
            _tool_result(4, R1, "python: can't open file '/x/check.py': [Errno 2] No such file or directory"),
            RunEventRow(thread_id=T1, run_id=R2, user_id="u1", event_type="llm.ai.response", category="message", content='{"tool_calls":[]}', event_metadata={}, seq=5),
            _tool_result(6, R2, 'Exit Code: 3\n{"sections": 12}'),
            _tool_result(7, R2, "x" * 5000),  # long output -> truncation flag
            RunEventRow(thread_id=T1, run_id=R2, user_id="u1", event_type="run.error", category="trace", content='{"error":"kaboom"}', event_metadata={}, seq=8),
        ]
        s.add_all(rows)
    return engine, sf


@ASYNCIO
async def test_list_thread_runs_fields_and_event_counts(tmp_path):
    engine, sf = await _make_db(tmp_path)
    try:
        async with sf() as s:
            runs = await service.list_thread_runs(s, T1)
        assert [r["run8"] for r in runs] == [R1[:8], R2[:8]]
        by_run = {r["run_id"]: r for r in runs}
        assert by_run[R1]["status"] == "success" and by_run[R1]["event_count"] == 4
        assert by_run[R2]["status"] == "error" and by_run[R2]["error"] == "boom"
        assert by_run[R2]["event_count"] == 4 and by_run[R2]["total_tokens"] == 900
    finally:
        await engine.dispose()


@ASYNCIO
async def test_get_run_events_filters_text_match_and_truncation(tmp_path):
    engine, sf = await _make_db(tmp_path)
    try:
        async with sf() as s:
            all_t1 = await service.get_run_events(s, T1)
            assert all_t1["total_matching"] == 8 and all_t1["returned"] == 8

            only_r2 = await service.get_run_events(s, T1, run_id=R2)
            assert only_r2["total_matching"] == 4 and {e["seq"] for e in only_r2["events"]} == {5, 6, 7, 8}

            hits = await service.get_run_events(s, T1, text_match="can't open file")
            assert hits["total_matching"] == 1 and hits["events"][0]["seq"] == 4
            assert "check.py" in hits["events"][0]["content"]

            tool_results = await service.get_run_events(s, T1, event_type="llm.tool.result")
            assert tool_results["total_matching"] == 4

            limited = await service.get_run_events(s, T1, limit=3)
            assert limited["returned"] == 3 and limited["total_matching"] == 8

            clipped = await service.get_run_events(s, T1, max_content_chars=100)
            long_ev = [e for e in clipped["events"] if e["seq"] == 7][0]
            assert long_ev["truncated"] is True and len(long_ev["content"]) <= 100

            empty = await service.get_run_events(s, "no-such-thread")
            assert empty == {"total_matching": 0, "returned": 0, "events": []}
    finally:
        await engine.dispose()


@ASYNCIO
async def test_mcp_handlers_end_to_end(tmp_path, monkeypatch):
    engine, sf = await _make_db(tmp_path)
    await engine.dispose()
    monkeypatch.setenv("OPS_DIAG_DB_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")

    runs_payload = json.loads((await _handle_list_thread_runs({"thread_id": T1}))[0].text)
    assert runs_payload["success"] and runs_payload["run_count"] == 2

    missing = json.loads((await _handle_list_thread_runs({"thread_id": "nope"}))[0].text)
    assert missing["success"] and missing["runs"] == [] and "无" in missing["note"]

    ev_payload = json.loads((await _handle_get_run_events({"thread_id": T1, "run_id": R2, "text_match": "Exit Code"}))[0].text)
    assert ev_payload["success"] and ev_payload["total_matching"] == 1 and ev_payload["events"][0]["seq"] == 6


def _run_script(name: str, *args: str) -> dict:
    proc = subprocess.run([sys.executable, str(SKILL_SCRIPTS / name), *args], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _write_skill_fixture(tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    evs = [
        {"seq": 1, "run_id": R1, "event_type": "run.start", "category": "trace", "content": "{}", "created_at": "2026-08-17T12:00:00+00:00"},
        {"seq": 2, "run_id": R1, "event_type": "llm.ai.response", "category": "message", "content": '{"tool_calls":[{"name":"bash","args":{"command":"python3 check.py"}}]}', "created_at": "2026-08-17T12:00:01+00:00"},
        {"seq": 3, "run_id": R1, "event_type": "llm.tool.result", "category": "message", "content": '{"content": "python: can\'t open file \'check.py\': [Errno 2] No such file or directory"}', "created_at": "2026-08-17T12:00:02+00:00"},
        {"seq": 4, "run_id": R1, "event_type": "llm.ai.response", "category": "message", "content": '{"tool_calls":[{"name":"bash","args":{"command":"python3 check.py"}}]}', "created_at": "2026-08-17T12:00:03+00:00"},
        {"seq": 5, "run_id": R1, "event_type": "llm.tool.result", "category": "message", "content": '{"content": "python: can\'t open file \'check.py\': [Errno 2] No such file or directory"}', "created_at": "2026-08-17T12:00:04+00:00"},
        {"seq": 6, "run_id": R1, "event_type": "llm.tool.result", "category": "message", "content": '{"content": "Exit Code: 3\\n{\\"ok\\": true}"}', "created_at": "2026-08-17T12:00:05+00:00"},
        {"seq": 7, "run_id": R1, "event_type": "llm.tool.result", "category": "message", "content": '{"content": "Exit Code: 1"}', "created_at": "2026-08-17T12:00:06+00:00"},
        {"seq": 8, "run_id": R1, "event_type": "llm.ai.response", "category": "message", "content": '{"tool_calls":[{"name":"read_file","args":{"path":"/a.md"}}]}', "created_at": "2026-08-17T12:00:07+00:00"},
        {"seq": 9, "run_id": R1, "event_type": "llm.tool.result", "category": "message", "content": '{"content": "fine", "status": "error"}', "created_at": "2026-08-17T12:00:08+00:00"},
    ]
    (events_dir / f"{R1[:8]}.jsonl").write_text(json.dumps({"events": evs}, ensure_ascii=False), encoding="utf-8")
    runs_row = {"run_id": R1, "status": "success", "stop_reason": None, "total_tokens": 123, "llm_call_count": 3, "message_count": 4, "event_count": len(evs), "created_at": "2026-08-17T12:00:00+00:00"}
    (tmp_path / "runs.json").write_text(json.dumps({"runs": [runs_row]}), encoding="utf-8")


def test_skill_scripts_classification_and_folding(tmp_path):
    _write_skill_fixture(tmp_path)
    failures = _run_script("extract_failures.py", "--events-dir", str(tmp_path / "events"))
    sigs = {c["signature"]: c["count"] for c in failures["clusters"]}
    assert sigs.get("can't open file") == 2  # hallucinated-script retries counted
    assert sigs.get("tool status=error") == 1
    assert "Exit Code" not in json.dumps(sigs)  # Exit Code 1 (grep) and 3 (bid contract) NOT failures
    top = failures["clusters"][0]
    assert top["first"]["seq"] == 3 and top["samples"]

    summary = _run_script("summarize_runs.py", "--runs", str(tmp_path / "runs.json"), "--events-dir", str(tmp_path / "events"))
    run = summary["runs"][0]
    assert run["failure_count"] == 3 and run["tool_calls"] == 3 and run["loaded_events"] == 9
    assert summary["totals"]["failures"] == 3

    seqs = _run_script("extract_sequences.py", "--events-dir", str(tmp_path / "events"))
    folded = seqs["runs"][0]["sequence"]
    assert folded[0] == {"tool": "bash", "sig": "python3 check.py", "x": 2}  # consecutive identical calls fold to x2
    assert any(f["tool"] == "read_file" and f["sig"] == "/a.md" for f in folded)
