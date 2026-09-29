"""批量动作执行：``invoke_action_batch_core``（EAI-CUSTOM 2026-09-29 批量确认摊销）。

覆盖批量核心自己的三件事（REST 暴露面契约由 tests/test_actions_rest.py 钉住）：
① **摊销**——全批只做一次投影装载 + 一次 refresh（调用计数断言，附 50 行 ≤ 40s 的
   松计时上界；真投影路径再钉一次「refresh 恰好一次」）；
② **审计逐条留痕**——N 行成功 = N 条审计行，与单条路径同形状；
③ **行级失败隔离**——404（范围外）/ 409（前置不满足）只落入该行，不中止全批；
   投影失败全批 degraded 但业务状态照常提交；无可投影行时不触发投影。

真库路径（真 Postgres 语句 / 真前置条件），与 test_actions_executor.py 同一取向。
"""

from __future__ import annotations

import time
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.ontology.actions import projection as projection_module
from app.ontology.actions.executor import ActionError, invoke_action_batch_core
from app.ontology.connectors import _ext_url
from app.ontology.scope import FilterRule

# 本仓 asyncio_mode 是 strict（同 test_actions_executor.py 的注）：集成路径全部显式标记。
pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_BATCH_SIZE = 50  # 任务验收口径：50 行确认


async def _seed_entity(status: str = "pending_review") -> uuid.UUID:
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            row = await conn.execute(
                text(
                    """INSERT INTO dg_entities (domain, etype, canonical_name, norm_name, attrs, confidence, status)
                       VALUES ('doc_graph','mine','批量实体', :norm, '{}'::jsonb, 0.9, :status) RETURNING id"""
                ),
                {"norm": f"批量实体-{uuid.uuid4().hex[:8]}", "status": status},
            )
            return row.scalar_one()
    finally:
        await engine.dispose()


async def _get_status(pk: uuid.UUID) -> str:
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            row = await conn.execute(text("SELECT status FROM dg_entities WHERE id = :id"), {"id": pk})
            return row.scalar_one()
    finally:
        await engine.dispose()


async def _audit_rows(pk: uuid.UUID) -> list[dict]:
    engine = create_async_engine(_ext_url(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            rows = await conn.execute(
                text("SELECT id, action_id, before, after, source FROM dg_action_audit WHERE target_pk = :id"),
                {"id": pk},
            )
            return [dict(r._mapping) for r in rows]
    finally:
        await engine.dispose()


def _identity_project():
    """投影桩：把收到的 (action_id, pks) 记进 calls，原样返回全部 pk（全部视为已入图）。"""
    calls: list = []

    def _project(action_id: str, rows: dict) -> set:
        calls.append((action_id, set(rows)))
        return set(rows)

    return _project, calls


async def _batch(pks, project_batch, *, action_id="review_entity.confirm", params=None):
    return await invoke_action_batch_core(
        action_id,
        params if params is not None else {},
        target_pks=pks,
        actor_id=uuid.uuid4(),
        actor_role="admin",
        source="api",
        scope_rule=FilterRule(operator="allow_all"),
        project_batch=project_batch,
    )


async def test_batch_confirm_amortizes_projection_single_load_and_audit_n():
    """50 行确认：投影**恰好一次**装载（摊销主判据）+ 审计 50 条 + 全部 active + ≤ 40s。

    计时是**松上界**（任务验收口径的计时侧），主判据是调用计数——计数抓得到
    "忘掉摊销、逐行投影"的回归（那样 loads 变 50），计时抓不到（50 次 refresh 在
    小图上未必超 40s，但生产千级图必超）。
    """
    pks = [await _seed_entity() for _ in range(_BATCH_SIZE)]
    project, calls = _identity_project()
    started = time.monotonic()
    result = await _batch(pks, project)
    elapsed = time.monotonic() - started

    assert len(calls) == 1, f"投影必须全批一次，实测 {len(calls)} 次"
    assert calls[0][0] == "review_entity.confirm"
    assert calls[0][1] == set(pks), "装载输入必须是全部成功行的合并行"
    assert result["projected"] is True
    assert result["failed"] == []
    assert len(result["succeeded"]) == _BATCH_SIZE
    assert result["requested"] == _BATCH_SIZE
    assert all(r["projected"] and r["ok"] for r in result["results"])
    assert result["projected_pks"] == sorted(str(p) for p in pks)
    # 审计逐条留痕：每行恰好一条，形状与单条路径一致
    total_audit = 0
    for pk in pks:
        audit = await _audit_rows(pk)
        assert len(audit) == 1
        assert audit[0]["action_id"] == "review_entity.confirm"
        assert audit[0]["source"] == "api"
        assert audit[0]["after"] == {"status": "active", "confidence": "0.700"}
        total_audit += len(audit)
    assert total_audit == _BATCH_SIZE
    for pk in pks:
        assert await _get_status(pk) == "active"
    assert elapsed < 40, f"50 行确认耗时 {elapsed:.1f}s 超出 40s 验收口径"


async def test_batch_confirm_real_projection_refresh_exactly_once(monkeypatch):
    """真投影路径（projection.project_rows + 真 kernel）：refresh **恰好一次**且全部入图。

    单条路径实测 ≈34s/条的根源是逐行 refresh；本条在真实装载+闭包重算上钉住
    「N 行共享一次重推理」——计数包在真 refresh 外，语义不替换。
    """
    from app.ontology.kernel.service import get_kernel

    pks = [await _seed_entity() for _ in range(3)]
    kernel = get_kernel()
    refresh_calls = {"n": 0}
    original_refresh = kernel.refresh

    def counting_refresh(*args, **kwargs):
        refresh_calls["n"] += 1
        return original_refresh(*args, **kwargs)

    monkeypatch.setattr(kernel, "refresh", counting_refresh)
    result = await _batch(pks, projection_module.project_rows)
    assert refresh_calls["n"] == 1, f"真投影 refresh 必须恰一次，实测 {refresh_calls['n']} 次"
    assert result["projected"] is True
    assert result["projected_pks"] == sorted(str(p) for p in pks)
    assert all(r["projected"] for r in result["results"])


async def test_batch_failure_isolation_preserves_good_rows():
    """行级隔离：409（前置不满足）与 404（范围外）只落该行，好行照常提交+入投影。

    顺序契约：results 按入参序；succeeded/failed 是其投影。失败行零审计、零状态变更。
    """
    ok1 = await _seed_entity()
    conflict = await _seed_entity(status="active")  # confirm 前置要求 pending_review → 409
    missing = uuid.uuid4()  # 不存在 → 404（ScopeDenied）
    ok2 = await _seed_entity()
    project, calls = _identity_project()
    result = await _batch([ok1, conflict, missing, ok2], project)

    assert result["succeeded"] == [str(ok1), str(ok2)], "成功列表按入参序只含成功行"
    assert [(f["pk"], f["status_code"]) for f in result["failed"]] == [
        (str(conflict), 409),
        (str(missing), 404),
    ]
    # 投影只收成功行（失败行没有合并行可投影）
    assert len(calls) == 1 and calls[0][1] == {ok1, ok2}
    # 好行：审计一条 + 状态翻转
    assert len(await _audit_rows(ok1)) == 1
    assert len(await _audit_rows(ok2)) == 1
    assert await _get_status(ok1) == "active"
    assert await _get_status(ok2) == "active"
    # 失败行：零审计、状态原状
    assert await _audit_rows(conflict) == []
    assert await _get_status(conflict) == "active"  # 本就是 active，未被动过
    assert await _audit_rows(missing) == []  # 不存在的行零审计


async def test_batch_projection_failure_degrades_all_but_commits():
    """投影抛异常 = 全批 degraded（errors 留痕），业务状态与审计**照常提交**。

    与单条 test_projection_failure_does_not_rollback 同一取向的批量版：投影失败
    不回滚业务状态，重跑全量装载自愈。
    """
    pk1 = await _seed_entity()
    pk2 = await _seed_entity()

    def boom(action_id: str, rows: dict) -> set:
        raise RuntimeError("projection boom")

    result = await _batch([pk1, pk2], boom)
    assert result["projected"] is False
    assert result["errors"] and "projection boom" in result["errors"][0]
    assert result["projected_pks"] == []
    assert len(result["succeeded"]) == 2  # 行级写全部成功
    assert all((not r["projected"]) and r["errors"] for r in result["results"]), "degraded 必须逐行可见"
    assert await _get_status(pk1) == "active"
    assert await _get_status(pk2) == "active"
    assert len(await _audit_rows(pk1)) == 1 and len(await _audit_rows(pk2)) == 1


async def test_batch_all_rows_failed_skips_projection_entirely():
    """全批行级失败 → 不触发投影（无可投影行，refresh 是纯浪费），projected 恒 True。"""
    triggered = {"n": 0}

    def must_not_project(action_id: str, rows: dict) -> set:
        triggered["n"] += 1
        return set(rows)

    result = await _batch([uuid.uuid4(), uuid.uuid4()], must_not_project)
    assert triggered["n"] == 0, "无可投影行时不应调用投影"
    assert result["succeeded"] == []
    assert len(result["failed"]) == 2
    assert result["projected"] is True  # 没有已提交行，断言图与 DB 天然一致


async def test_batch_unknown_action_rejected():
    """未知动作 fail-closed（与单条同判），在鉴权之后、任何行执行之前短路。"""
    with pytest.raises(ActionError, match="unknown action"):
        await _batch([uuid.uuid4()], lambda a, r: set(r), action_id="nope.nope")


async def test_batch_reject_action_writes_rejected_status():
    """驳回批量与确认共用同一管线（动作不同、语义不同）：rejected 翻转 + 审计。"""
    pk = await _seed_entity()
    project, calls = _identity_project()
    result = await _batch([pk], project, action_id="review_entity.reject")
    assert result["succeeded"] == [str(pk)]
    assert result["failed"] == []
    assert await _get_status(pk) == "rejected"
    audit = await _audit_rows(pk)
    assert len(audit) == 1 and audit[0]["after"]["status"] == "rejected"
