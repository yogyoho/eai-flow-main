"""doc_graph 消解 REST 集成测试——需 extensions 库且 dg_* 表已建; 否则自动 skip.

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-13-ontology-semantic-map-v2-design.md §4。
Client 装置照 test_ontology_rest.py（require_permission 打桩 → reload routers → 最小 FastAPI）;
DB 就绪探针照 test_doc_graph_ingest.py（host 无库即全 skip, 真库验证在容器内）。
冒烟数据用每次运行唯一的 _MARK 命名, 清理 DELETE 全部参数化圈定——失败也不误删他人数据。
"""

from __future__ import annotations

import asyncio
import importlib
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

import app.extensions.auth.middleware as authm
import app.extensions.ontology.doc_graph.routers as dg_routers
from app.extensions.ontology.connectors import ConnectorError
from app.extensions.ontology.doc_graph.resolver import normalize_name

_MARK = "smkres" + uuid4().hex[:8]  # 每次运行唯一; normalize 后仍小写, LIKE 圈定安全
_DOC = "doc-res-" + _MARK
_PROJ_A = f"冒烟消解实体Alpha{_MARK}"
_PROJ_B = f"冒烟消解实体Alpha有限公司{_MARK}"  # 与 A 相似度 ≈0.926 ≥ 0.92（有限责任公司 5 字会跌破阈值）


def _resolve_url() -> str | None:
    url = os.environ.get("ONTOLOGY_DB_URL")
    if url:
        return url
    try:
        from app.extensions.config import get_extensions_config

        return get_extensions_config().database.url
    except Exception:
        return None


def _tables_ready(url: str) -> bool:
    """探针: dg_entities 可查询才算"库就绪"——连接拒绝/驱动缺失/表未建一律视为不可用。"""

    async def _probe() -> bool:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        engine = create_async_engine(url, poolclass=NullPool, connect_args={"timeout": 2})
        try:
            async with engine.connect() as conn:
                return (await conn.execute(text("SELECT to_regclass('public.dg_entities')"))).scalar() is not None
        except Exception:
            return False
        finally:
            await engine.dispose()

    try:
        return asyncio.run(_probe())
    except Exception:
        return False


_raw_url = _resolve_url()
_URL = _raw_url if _raw_url and _tables_ready(_raw_url) else None

pytestmark = pytest.mark.skipif(not _URL, reason="extensions 库未就绪(dg_entities 表不可达/未建)——真库验证在容器内")


def _payload() -> dict:
    return {
        "domain": "bid",
        "thread_id": "t-rest",
        "entities": [
            {"etype": "project", "name": _PROJ_A, "confidence": 0.5, "mention": {"document_id": _DOC, "quote": f"项目：{_PROJ_A}"}},
            {"etype": "project", "name": _PROJ_B, "confidence": 0.5, "mention": {"document_id": _DOC, "quote": f"项目：{_PROJ_B}"}},
        ],
    }


@pytest.fixture()
def client(monkeypatch):
    """照 test_ontology_rest.py: 打桩 require_permission → reload routers → 最小 FastAPI。"""
    monkeypatch.setattr(authm, "require_permission", lambda perm: lambda: SimpleNamespace(id=uuid4(), username="tester"))
    module = importlib.reload(dg_routers)
    app = FastAPI()
    app.include_router(module.router)
    return TestClient(app)


def _call(fn, *args, **kwargs):
    """连接类异常（ConnectorError/裸 OSError/sqlalchemy 连接包装）= 环境不可达 → skip 不算失败。"""
    try:
        return fn(*args, **kwargs)
    except (ConnectorError, OSError, OperationalError) as e:
        pytest.skip(f"extensions 库环境不可达: {e}")


def test_unknown_ids_404(client):
    """404 态: 不存在的 entity/merge/candidate + malformed uuid（_uuid_or_404, 防 CAST DataError→500）。"""
    missing = "00000000-0000-0000-0000-0000000000ab"
    r1 = _call(client.get, "/api/extensions/doc-graph/resolution/suggestions", params={"entity_id": missing})
    assert r1.status_code == 404 and r1.json()["detail"] == f"entity {missing} 不存在"  # args[0] 原文, 无 KeyError repr 引号
    r2 = _call(client.post, "/api/extensions/doc-graph/resolution/unmerge", json={"merge_id": missing})
    assert r2.status_code == 404
    r3 = _call(client.post, "/api/extensions/doc-graph/resolution/merge", json={"candidate_id": missing, "canonical_id": missing})
    assert r3.status_code == 404  # candidate 不存在（UPDATE rowcount=0; 未到 INSERT 故自合并 CHECK 不触发）
    r4 = _call(client.get, "/api/extensions/doc-graph/resolution/suggestions", params={"entity_id": "not-a-uuid"})
    assert r4.status_code == 404


def test_resolution_full_flow(client):
    """全链路: ingest(相近名对, conf 0.5→pending) → pending 列表 → suggestions(含对手, 无 self)
    → merge(pending 减一; 重复合并 409; 自合并 CHECK 409) → unmerge(留痕删+还原)。"""

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.extensions.ontology.doc_graph.ingest import ingest_extraction
    from app.extensions.ontology.doc_graph.schemas import BidExtraction

    async def _ingest():
        return await ingest_extraction(BidExtraction.model_validate(_payload()))

    def _query(sql, params=None, fetch="all"):
        async def _run():
            engine = create_async_engine(_URL, poolclass=NullPool)
            try:
                async with engine.connect() as conn:
                    res = await conn.execute(text(sql), params or {})
                    if fetch == "all":
                        return [dict(r) for r in res.mappings().all()]
                    if fetch == "one":
                        row = res.mappings().first()
                        return dict(row) if row else None
                    return res.scalar_one()
            finally:
                await engine.dispose()

        return asyncio.run(_run())

    def _cleanup():
        async def _run():
            engine = create_async_engine(_URL, poolclass=NullPool)
            try:
                async with engine.begin() as conn:
                    await conn.execute(text("DELETE FROM dg_mentions WHERE document_id = :doc"), {"doc": _DOC})
                    await conn.execute(
                        text("DELETE FROM dg_merges WHERE candidate_id IN (SELECT id FROM dg_entities WHERE norm_name LIKE '%' || :m || '%') OR canonical_id IN (SELECT id FROM dg_entities WHERE norm_name LIKE '%' || :m || '%')"),
                        {"m": _MARK},
                    )
                    await conn.execute(text("DELETE FROM dg_entities WHERE norm_name LIKE '%' || :m || '%'"), {"m": _MARK})
            finally:
                await engine.dispose()

        asyncio.run(_run())

    try:
        # 1. ingest 两个相近名实体（confidence=0.5 → pending_review）
        counts = _call(asyncio.run, _ingest())
        assert counts["entities_upserted"] == 2
        rows = _call(_query, "SELECT id, norm_name, status FROM dg_entities WHERE norm_name LIKE '%' || :m || '%'", {"m": _MARK})
        by_norm = {r["norm_name"]: str(r["id"]) for r in rows}
        id_a, id_b = by_norm[normalize_name(_PROJ_A)], by_norm[normalize_name(_PROJ_B)]
        assert id_a and id_b and id_a != id_b
        assert all(r["status"] == "pending_review" for r in rows)

        # 2. pending 列表含两者（成员断言——列表是全局的, 只圈自己的 _MARK 对）
        r = _call(client.get, "/api/extensions/doc-graph/resolution/pending", params={"etype": "project"})
        assert r.status_code == 200
        pending_ids = {e["id"] for e in r.json()["entities"]}
        assert {id_a, id_b} <= pending_ids

        # 3. suggestions: A 的建议含 B（similarity ≥ 0.92, action=review）且不含 A 自身（SQL 层 self 圈除）
        r = _call(client.get, "/api/extensions/doc-graph/resolution/suggestions", params={"entity_id": id_a})
        assert r.status_code == 200
        body = r.json()
        assert body["entity"]["id"] == id_a and body["entity"]["etype"] == "project"
        sug = {s["id"]: s for s in body["suggestions"]}
        assert id_a not in sug, "self 圈除由 SQL id != 目标 承担, 目标自身不得出现在建议里"
        assert id_b in sug and sug[id_b]["similarity"] >= 0.92 and sug[id_b]["action"] == "review"

        # 4. merge → 200 + 回显三字段; pending 减一（B 出列, A 仍在）
        r = _call(client.post, "/api/extensions/doc-graph/resolution/merge", json={"candidate_id": id_b, "canonical_id": id_a})
        assert r.status_code == 200
        merge_body = r.json()
        merge_id = merge_body["merge_id"]
        assert merge_body["candidate_id"] == id_b and merge_body["canonical_id"] == id_a
        r2 = _call(client.get, "/api/extensions/doc-graph/resolution/pending", params={"etype": "project"})
        pending_ids2 = {e["id"] for e in r2.json()["entities"]}
        assert id_b not in pending_ids2 and id_a in pending_ids2
        # 重复合并同 candidate → 409（MergeConflict: candidate_id 无唯一约束, 留痕防重在 service 层）
        r_dup = _call(client.post, "/api/extensions/doc-graph/resolution/merge", json={"candidate_id": id_b, "canonical_id": id_a})
        assert r_dup.status_code == 409
        # 自合并 → 409（ck_dg_merges_no_self_merge CHECK → IntegrityError; 事务回滚, A 仍 pending）
        r_self = _call(client.post, "/api/extensions/doc-graph/resolution/merge", json={"candidate_id": id_a, "canonical_id": id_a})
        assert r_self.status_code == 409
        assert id_a in {e["id"] for e in _call(client.get, "/api/extensions/doc-graph/resolution/pending").json()["entities"]}

        # 5. unmerge → 留痕行删除 + candidate 还原（service 语义: 还原为 active, 非回 pending）
        r = _call(client.post, "/api/extensions/doc-graph/resolution/unmerge", json={"merge_id": merge_id})
        assert r.status_code == 200 and r.json()["restored_candidate_id"] == id_b
        st = _call(_query, "SELECT status FROM dg_entities WHERE id = CAST(:eid AS uuid)", {"eid": id_b}, fetch="one")
        assert st["status"] == "active"
        n = _call(_query, "SELECT COUNT(*) FROM dg_merges WHERE id = CAST(:mid AS uuid)", {"mid": merge_id}, fetch="scalar")
        assert n == 0
    finally:
        _cleanup()  # 断言失败也要清场（FK 顺序: mentions → merges → entities）
