"""learnings service 测试 — 资格门槛边界 + 状态机(真库, 未就绪则 skip; 房屋模式)."""

import asyncio
import uuid

import pytest


def _agentflow_ready() -> bool:
    import os

    try:
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


pytestmark = pytest.mark.skipif(not _agentflow_ready(), reason="extensions 库不可达——真库验证在容器内 E2E")

_MARK = f"ev{uuid.uuid4().hex[:8]}"


def _fold(user_id, thread_id="tA", key_area="runtime", key_symptom="failure"):
    from app.extensions.learnings import service

    return service.mint_or_fold(
        user_id=user_id,
        kind="error",
        area=key_area,
        symptom=key_symptom,
        summary="boundary probe",
        source_thread_id=thread_id,
    )


def test_eligibility_threshold_boundaries(learnings_loop):
    """资格 = recurrence>=3 且 跨>=2 thread 且 pending: 3x1线程 不够, 3x2线程 才够."""

    async def _run():
        from app.extensions.learnings import service

        await service.ensure_ready()
        user_id = f"u1-{_MARK}"
        # 3 次, 全在同一线程 -> 不可晋升
        for _ in range(3):
            await _fold(user_id, thread_id="t-same")
        one_thread = await service.surface(user_id, limit=10)

        # 第 4 次跨到第二个线程 -> 可晋升
        await _fold(user_id, thread_id="t-other")
        two_threads = await service.surface(user_id, limit=10)
        return one_thread, two_threads

    one_thread, two_threads = learnings_loop.run_until_complete(_run())
    assert all(e["eligible_for_skill"] is False for e in one_thread["entries"])
    target = [e for e in two_threads["entries"] if e["pattern_key"] == "runtime.failure"]
    assert target and target[0]["eligible_for_skill"] is True
    assert target[0]["recurrence_count"] == 4 and target[0]["distinct_thread_count"] == 2
    assert two_threads["promotion_ready"] >= 1


def test_status_machine_rejects_illegal_transition(learnings_loop):
    """promoted_to_skill 不可经 resolve 伪造(D7); resolved->pending 重开合法."""

    async def _run():
        from app.extensions.learnings import service

        await service.ensure_ready()
        user_id = f"u2-{_MARK}"
        await _fold(user_id)
        row = (await service.surface(user_id))["entries"][0]
        forge = await service.resolve(user_id, row["id"], status="promoted_to_skill")
        legal = await service.resolve(user_id, row["id"], status="resolved")
        reopen = await service.resolve(user_id, row["id"], status="pending")
        fake = await service.resolve(user_id, "no-such-id")
        return forge, legal, reopen, fake

    forge, legal, reopen, fake = learnings_loop.run_until_complete(_run())
    assert forge["success"] is False  # D7: 终态不可经 resolve 伪造(只能由晋升流程写入)
    assert legal["success"] is True
    assert reopen["success"] is True
    assert fake["success"] is False


def test_summary_required_and_kind_validated(learnings_loop):
    async def _run():
        from app.extensions.learnings import service

        await service.ensure_ready()
        user_id = f"u3-{_MARK}"
        no_summary = await service.mint_or_fold(user_id=user_id, kind="error", area="runtime", symptom="failure", summary="")
        bad_kind = await service.mint_or_fold(user_id=user_id, kind="rant", area="runtime", symptom="failure", summary="s")
        bad_area = await service.mint_or_fold(user_id=user_id, kind="error", area="galaxy", symptom="failure", summary="s")
        return no_summary, bad_kind, bad_area

    no_summary, bad_kind, bad_area = learnings_loop.run_until_complete(_run())
    assert no_summary["success"] is False
    assert bad_kind["success"] is False
    assert bad_area["success"] is False
