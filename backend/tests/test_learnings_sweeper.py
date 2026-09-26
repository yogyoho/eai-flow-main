"""learnings sweeper 测试 — 提取纯函数(角色过滤/cap) + 幂等(真库, 未就绪则 skip)."""

import uuid

import pytest

from app.extensions.learnings.sweeper import extract_detections, select_runs


def _tool_err(text, name="bash"):
    return {"role": "tool", "name": name, "status": "error", "content": text}


def test_extract_filters_agent_prose():
    """结构性角色过滤: agent 自己说'the build failed'绝不能生成条目(原版弱点)."""
    messages = [
        {"role": "assistant", "content": "the build failed yesterday, let me check"},
        {"role": "user", "content": "修复它, it FAILED"},
        _tool_err("ModuleNotFoundError: No module named 'yaml'"),
    ]
    dets = extract_detections(messages, [])
    assert len(dets) == 1
    assert dets[0]["pattern-like"] if False else dets[0]["area"] == "deps"


def test_extract_caps_at_five():
    messages = [_tool_err(f"Error: boom-{i}") for i in range(10)]
    dets = extract_detections(messages, [])
    assert len(dets) == 5


def test_extract_includes_run_error_events():
    dets = extract_detections([], [{"event_type": "run.error", "error": "graph recursion limit hit"}])
    assert len(dets) == 1 and dets[0]["symptom"] == "failure"


def test_select_runs_newest_first_and_cap():
    rows = [
        {"run_id": f"r{i}", "created_at": f"2026-09-{13:02d}T0{i}:00:00Z"} for i in range(1, 6)
    ]
    swept = {"r5"}
    out = select_runs(rows, swept, cap=2)
    assert [r["run_id"] for r in out] == ["r4", "r3"]


# --- 真库部分: sweep_run 幂等 + service 折叠(extensions 库未就绪则 skip, 房屋模式) --


def _agentflow_ready() -> bool:
    import os

    try:
        import asyncio

        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        host = os.getenv("EXTENSIONS_DB_HOST", "localhost")

        async def _probe() -> bool:
            engine = create_async_engine(
                f"postgresql+asyncpg://agentflow:agentflow123@{host}:5432/agentflow",
                poolclass=NullPool,
                connect_args={"timeout": 2},
            )
            try:
                async with engine.connect() as conn:
                    return (await conn.execute(text("SELECT 1"))).scalar() == 1
            except Exception:
                return False
            finally:
                await engine.dispose()

        return asyncio.run(_probe())
    except Exception:
        return False


_URL_OK = _agentflow_ready()
pytestmark = pytest.mark.skipif(not _URL_OK, reason="extensions 库不可达——真库验证在容器内 E2E")

_MARK = f"ev{uuid.uuid4().hex[:8]}"


class _FakeStore:
    """固定消息的假 store — 幂等/折叠测试不依赖 deerflow 库."""

    def __init__(self, messages):
        self._messages = messages
        self.calls = 0

    async def list_messages_by_run(self, thread_id, run_id, **kw):
        self.calls += 1
        return self._messages

    async def list_events(self, thread_id, run_id, **kw):
        return []


def _make_fake_run(thread_id: str) -> tuple[_FakeStore, str]:
    messages = [
        _tool_err(f"Traceback (most recent call last):\nKeyError: '{_MARK}'"),
    ]
    return _FakeStore(messages), f"fake-run-{_MARK}"


def test_sweep_run_idempotent_and_folds(learnings_loop):
    """同 run 重复 sweep 零重复(receipts 幂等); 相同文本折叠计数仍递增(D12)."""
    from app.extensions.learnings import service, sweeper

    async def _run():
        await service.ensure_ready()
        user_id = f"u-{_MARK}"
        thread_id = f"t-{_MARK}"
        store, run_id = _make_fake_run(thread_id)

        first = await sweeper.sweep_run(store, user_id, thread_id, run_id)
        dup = await sweeper.sweep_run(store, user_id, thread_id, run_id)

        # 相同错误第二次出现(新 run_id) -> 折叠 +1, 而非新增
        run_id2 = run_id + "-again"
        second = await sweeper.sweep_run(store, user_id, thread_id, run_id2)

        surface = await service.surface(user_id, limit=10)
        return first, dup, second, surface

    first, dup, second, surface = learnings_loop.run_until_complete(_run())
    assert first["captures"] == 1
    assert dup.get("skipped") == "already-swept"  # 幂等: 扫过的 run 永不重扫
    assert second["captures"] == 1
    entries = surface["entries"]
    assert len(entries) == 1, f"相同 pattern_key 必须折叠成一行: {entries}"
    assert entries[0]["recurrence_count"] == 2
    assert entries[0]["distinct_thread_count"] >= 1


def test_mint_or_fold_reopens_resolved(learnings_loop):
    """resolved 命中 -> 重开 pending; dismissed 命中 -> 保持(尊重人工裁决)."""
    from app.extensions.learnings import service

    async def _run():
        await service.ensure_ready()
        user_id = f"u2-{_MARK}"
        common = dict(user_id=user_id, kind="error", area="runtime", symptom="failure", summary="s")
        await service.mint_or_fold(**common, source_thread_id="tA")
        row_id = (await service.surface(user_id))["entries"][0]["id"]
        await service.resolve(user_id, row_id, status="dismissed")
        await service.mint_or_fold(**common, source_thread_id="tB")
        after_dismiss = (await service.surface(user_id))["entries"]

        # resolved 路径: 建 -> resolve -> 再命中 -> 应重开
        user_id2 = f"u3-{_MARK}"
        common2 = dict(user_id=user_id2, kind="error", area="runtime", symptom="failure", summary="s2")
        await service.mint_or_fold(**common2, source_thread_id="tA")
        row2 = (await service.surface(user_id2))["entries"][0]
        await service.resolve(user_id2, row2["id"])
        await service.mint_or_fold(**common2, source_thread_id="tB")
        after_resolved = (await service.surface(user_id2))["entries"]
        return after_dismiss, after_resolved

    after_dismiss, after_resolved = learnings_loop.run_until_complete(_run())
    assert all(e["status"] != "pending" for e in after_dismiss), "dismissed 不应被自动重开"
    assert len(after_resolved) == 1 and after_resolved[0]["status"] == "pending"
    assert after_resolved[0]["recurrence_count"] == 2
