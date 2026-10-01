"""抽取任务 API 测试——surface（免库）+ converter 纯函数 + integration（真库门禁）.

EAI-CUSTOM(2026-10-01 B2): 设计 docs/designs/2026-10-01-ontostudio-ux-governance.md §B2。
分层照 test_actions_rest.py 惯例：暴露面/纯函数本文件直测；真库路径（闭环/409/重跑替换/
force_review/清扫）标 integration，受 ONTOSTUDIO_TEST_ALLOW_REAL_DB=1 门禁 + 可达性探针
双层控制（conftest._gate_real_db_tests）。
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.doc_graph.ingest_tasks import build_payload_from_outline, sweep_orphan_tasks
from app.main import create_app

PREFIX = "/api/extensions/ingest-tasks"

# ── converter 纯函数（无库，永远跑）───────────────────────────────────────────────

# 实体名唯一前缀——integration 跑在真库上，通用名（COD 等）会经自然键合并焊进生产数据
# （2026-10-01 实测教训：integration 夹具名必须自带 uuid 前缀，见 cerebrum 同日条目）
_IT = uuid.uuid4().hex[:8]
_E1, _E2 = f"ITCOD-{_IT}", f"IT敏感点-{_IT}"
_GOLDEN_OUTLINE = {
    "ontology": {
        "entities": [
            {"etype": "pollutant", "name": _E1, "attrs": {"src": "t"}, "confidence": 0.9},
            {"etype": "sensitive_point", "name": _E2, "attrs": {}, "confidence": 0.85},
        ],
        "relations": [
            {"predicate": "threatens", "subject": _E1, "object": _E2, "confidence": 0.88}
        ],
    }
}


def test_converter_golden_payload_valid():
    """合法 outline → EiaExtraction 通过域校验，计数正确。"""
    payload, stats = build_payload_from_outline(_GOLDEN_OUTLINE, document_id="kf-sample:x", extracted_by="t1")
    assert payload is not None
    assert payload.domain == "eia"
    assert [e.name for e in payload.entities] == [_E1, _E2]
    assert payload.entities[0].mention.document_id == "kf-sample:x"
    assert payload.entities[0].mention.quote == ""  # 无句子上下文——quote 置空
    assert len(payload.relations) == 1 and payload.relations[0].predicate == "threatens"
    assert stats["entities"] == 2 and stats["relations"] == 1


def test_converter_drops_out_of_domain_rows():
    """越域 etype/谓词/悬空引用被防御性剔除且计数——单行脏不炸整个 payload（fail-closed 前置过滤）。"""
    outline = {
        "ontology": {
            "entities": [
                {"etype": "pollutant", "name": "COD", "attrs": {}, "confidence": 0.9},
                {"etype": "nonexistent_type", "name": "幽灵", "attrs": {}, "confidence": 0.9},
            ],
            "relations": [
                {"predicate": "threatens", "subject": "COD", "object": "敏感点A", "confidence": 0.9},  # 悬空引用
                {"predicate": "made_up_pred", "subject": "COD", "object": "COD", "confidence": 0.9},  # 越域谓词
            ],
        }
    }
    payload, stats = build_payload_from_outline(outline, document_id="d", extracted_by="t")
    assert payload is not None
    assert [e.name for e in payload.entities] == ["COD"]
    assert payload.relations == []
    assert stats["dropped"] == {"entities": 1, "relations": 2}


def test_converter_empty_returns_none():
    """零实体 → (None, stats)——runner 据此落 completed_empty（D13/13A）。"""
    for outline in (None, {}, {"ontology": None}, {"ontology": {"entities": [], "relations": []}}):
        payload, stats = build_payload_from_outline(outline, document_id="d", extracted_by="t")
        assert payload is None and stats["entities"] == 0


# ── surface（免库：鉴权门 + 请求体校验）───────────────────────────────────────────


def _app():
    return create_app()


@pytest.mark.anyio
async def test_post_requires_auth():
    """无 token → 401/403（门禁生效；具体码随 auth 实现，二者皆拒）。"""
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t") as c:
        r = await c.post(PREFIX, json={"sample_id": str(uuid.uuid4())})
        assert r.status_code in (401, 403)


@pytest.mark.anyio
async def test_post_invalid_body_422(auth_headers):
    """缺 sample_id → pydantic 422（越界不 500）。"""
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t") as c:
        r = await c.post(PREFIX, json={}, headers=auth_headers)
        assert r.status_code == 422


# ── integration（真库门禁：ONTOSTUDIO_TEST_ALLOW_REAL_DB=1 且库可达）──────────────

pytestmark_integration = pytest.mark.integration


def _integration_ready() -> bool:
    from conftest import real_db_allowed

    return real_db_allowed()


async def _db():
    from app.ontology.connectors import _ext_url

    return create_async_engine(_ext_url(), poolclass=NullPool)


@pytest.fixture
def integration_skip():
    if not _integration_ready():
        pytest.skip("真库门禁未开（ONTOSTUDIO_TEST_ALLOW_REAL_DB=1）或不可达")


@pytest.mark.integration
@pytest.mark.anyio
async def test_full_loop_force_review_rerun_replace(auth_headers, integration_skip):
    """闭环（SC2 终裁版）：建任务→轮询终态→force_review 全量 pending→重跑 mention 不翻倍。"""
    engine = await _db()
    sample_id = str(uuid.uuid4())
    doc_id = f"kf-sample:{sample_id}"
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO kf_samples (id, title, source_path, file_hash, status, outline_json)
                    VALUES (CAST(:id AS uuid), 'IT-样例', 'it://x', :hash, 'parsed',
                            CAST(:outline AS jsonb))
                    """
                ),
                {"id": sample_id, "hash": uuid.uuid4().hex, "outline": __import__("json").dumps(_GOLDEN_OUTLINE)},
            )
        async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t") as c:
            r = await c.post(PREFIX, json={"sample_id": sample_id, "force_review": True}, headers=auth_headers)
            assert r.status_code == 201, r.text
            task_id = r.json()["id"]
            # 轮询终态（runner 串行，给足窗口）
            status = None
            for _ in range(60):
                g = await c.get(f"{PREFIX}/{task_id}", headers=auth_headers)
                if g.status_code == 404:
                    status = "deleted"  # 被 409 通道外任务清理——不预期，仅防御
                    break
                status = g.json()["status"]
                if status in ("done", "completed_empty", "failed", "aborted"):
                    break
                await __import__("asyncio").sleep(0.5)
            assert status == "done", f"任务终态异常: {status}, body={g.text if g.status_code != 404 else ''}"
            detail = (await c.get(f"{PREFIX}/{task_id}", headers=auth_headers)).json()
            assert detail["stats"]["entities_upserted"] == 2
            # force_review（D11/11A）：本任务打标实体（attrs.ingest_task）全量 pending_review——强断言非弱容忍
            engine2 = await _db()
            async with engine2.connect() as conn:
                n_pending = (
                    await conn.execute(
                        text(
                            "SELECT COUNT(*) FROM dg_entities "
                            "WHERE attrs->>'ingest_task' = :tid AND status = 'pending_review'"
                        ),
                        {"tid": task_id},
                    )
                ).scalar()
            await engine2.dispose()
            assert n_pending == 2, f"force_review 应使 2 个新造实体 pending_review，实际 {n_pending}"
            # 重跑=替换：再次触发并等终态，mention 数不翻倍（固定 2 实体 1 关系 → 3 条 mention）。
            # 注意：重跑会以新 tag 重写 attrs.ingest_task——此后不得再用旧 tid 断言 pending
            r2 = await c.post(PREFIX, json={"sample_id": sample_id, "force_review": True}, headers=auth_headers)
            assert r2.status_code == 409 or r2.status_code == 201  # runner 可能未启动(409)或已终态(201)
            r3 = await c.post(PREFIX, json={"sample_id": sample_id}, headers=auth_headers)
            assert r3.status_code == 201
            t3 = r3.json()["id"]
            for _ in range(60):
                g3 = await c.get(f"{PREFIX}/{t3}", headers=auth_headers)
                if g3.status_code == 404:
                    break
                if g3.json()["status"] in ("done", "completed_empty", "failed", "aborted"):
                    break
                await __import__("asyncio").sleep(0.5)
            assert g3.json().get("status") in ("done", "completed_empty")
            engine3 = await _db()
            async with engine3.connect() as conn:
                n_mentions = (
                    await conn.execute(
                        text("SELECT COUNT(*) FROM dg_mentions WHERE document_id = :doc"),
                        {"doc": doc_id},
                    )
                ).scalar()
            await engine3.dispose()
            assert n_mentions == 3, f"重跑后 mention 应=3（2 实体+1 关系），实际 {n_mentions}——替换语义失效"
    finally:
        # 清理本用例产物（mention→entities→tasks→sample）
        cleanup = await _db()
        async with cleanup.begin() as conn:
            # Python 侧先捕获 ID（mention 一删引用链即断），再按 FK 序删除——窗口启发式在残留库上不可靠
            ids = (
                await conn.execute(
                    text("SELECT entity_id, relation_id FROM dg_mentions WHERE document_id = :doc"),
                    {"doc": doc_id},
                )
            ).all()
            ent_ids = [r.entity_id for r in ids if r.entity_id]
            rel_ids = [r.relation_id for r in ids if r.relation_id]
            await conn.execute(text("DELETE FROM dg_mentions WHERE document_id = :doc"), {"doc": doc_id})
            # 残渣自洽序：凡引用我方捕获 relation/entity 的 mention（含此前失败运行的他 doc 残留）一并清，
            # 之后 relation/entity 才无引用——否则 FK 环死循环（eng-review 实测三轮）
            if rel_ids or ent_ids:
                await conn.execute(
                    text(
                        "DELETE FROM dg_mentions WHERE relation_id = ANY(CAST(:rels AS uuid[])) "
                        "OR entity_id = ANY(CAST(:ents AS uuid[]))"
                    ),
                    {"rels": rel_ids or [], "ents": ent_ids or []},
                )
                await conn.execute(
                    text(
                        "DELETE FROM dg_relations WHERE id = ANY(CAST(:rels AS uuid[])) "
                        "OR subject_id = ANY(CAST(:ents AS uuid[])) OR object_id = ANY(CAST(:ents AS uuid[]))"
                    ),
                    {"rels": rel_ids or [], "ents": ent_ids or []},
                )
            if ent_ids:
                await conn.execute(text("DELETE FROM dg_entities WHERE id = ANY(CAST(:ents AS uuid[]))"), {"ents": ent_ids})
            if ent_ids:
                await conn.execute(text("DELETE FROM dg_entities WHERE id = ANY(CAST(:ents AS uuid[]))"), {"ents": ent_ids})
            await conn.execute(text("DELETE FROM ingest_tasks WHERE sample_id = CAST(:sid AS uuid)"), {"sid": sample_id})
            await conn.execute(text("DELETE FROM kf_samples WHERE id = CAST(:sid AS uuid)"), {"sid": sample_id})
        await cleanup.dispose()


@pytest.mark.integration
@pytest.mark.anyio
async def test_sweep_orphans(auth_headers, integration_skip):
    """启动清扫：extracting 孤儿行 → failed(服务重启中断)（D4/3A）。"""
    engine = await _db()
    tid = str(uuid.uuid4())
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO ingest_tasks (id, sample_id, document_id, force_review, status) "
                    "VALUES (CAST(:tid AS uuid), CAST(:sid AS uuid), 'sweep-it', true, 'extracting')"
                ),
                {"tid": tid, "sid": str(uuid.uuid4())},
            )
        await sweep_orphan_tasks()
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT status, error FROM ingest_tasks WHERE id = CAST(:tid AS uuid)"),
                    {"tid": tid},
                )
            ).first()
        assert row.status == "failed" and "重启" in (row.error or "")
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM ingest_tasks WHERE id = CAST(:tid AS uuid)"), {"tid": tid})
        await engine.dispose()
