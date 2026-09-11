"""doc_graph 入库集成测试——需 extensions 库且 dg_* 表已建; 否则自动 skip.

URL 解析与 connectors._ext_url 同语义: env 优先, 回退 extensions config。
但默认 DatabaseConfig 恒产出 localhost URL（容器外也不为 None）, 仅凭 URL 存在判定 skip 会在
CI(无库连接拒绝)与表未建环境(ProgrammingError)下直接报错——故以 dg_entities 表存在性探针兜底。
真库 roundtrip 验证在容器内 E2E（Task 9）。
冒烟数据用每次运行唯一的 _MARK 命名, 清理 DELETE 全部参数化圈定——失败也不误删他人数据。
"""

import asyncio
import os
from uuid import uuid4

import pytest

from app.extensions.ontology.doc_graph.schemas import BidExtraction

_MARK = "smk" + uuid4().hex[:8]  # 每次运行唯一; normalize 后仍小写, LIKE 圈定安全
_DOC = "doc-ing-" + _MARK  # mention 清理的附加闸门


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

pytestmark = pytest.mark.skipif(not _URL, reason="extensions 库未就绪(dg_entities 表不可达/未建)——真库验证在容器内 E2E")

_PROJ = f"冒烟项目{_MARK}"
_BID = f"冒烟供方{_MARK}"


def _payload() -> dict:
    return {
        "domain": "bid",
        "thread_id": "t-test",
        "entities": [
            {"etype": "project", "name": _PROJ, "mention": {"document_id": _DOC, "quote": f"{_PROJ}施工招标"}},
            {"etype": "bidder", "name": _BID, "confidence": 0.9, "mention": {"document_id": _DOC, "quote": f"投标人：{_BID}"}},
        ],
        "relations": [{"predicate": "bidder_of_project", "subject": _BID, "object": _PROJ, "mention": {"document_id": _DOC, "quote": f"{_BID}投标{_PROJ}"}}],
    }


def test_ingest_roundtrip_and_idempotent():
    """首投建行; 同 payload 重投不产生新实体（幂等）; mention 证据追加。"""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.extensions.ontology.doc_graph.ingest import ingest_extraction

    async def _entity_ids(conn):
        res = await conn.execute(text("SELECT id FROM dg_entities WHERE domain='bid' AND norm_name LIKE '%' || :mark || '%'"), {"mark": _MARK})
        return {str(r[0]) for r in res}

    async def _run():
        p = BidExtraction.model_validate(_payload())
        first = await ingest_extraction(p)

        engine = create_async_engine(_URL, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                ids_1 = await _entity_ids(conn)
        finally:
            await engine.dispose()

        again = await ingest_extraction(p)

        engine = create_async_engine(_URL, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                ids_2 = await _entity_ids(conn)
                n_ent = (await conn.execute(text("SELECT COUNT(*) FROM dg_entities WHERE domain='bid' AND norm_name LIKE '%' || :mark || '%'"), {"mark": _MARK})).scalar_one()
        finally:
            await engine.dispose()
        return first, again, ids_1, ids_2, n_ent

    async def _cleanup():
        engine = create_async_engine(_URL, poolclass=NullPool)
        try:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM dg_mentions WHERE document_id = :doc"), {"doc": _DOC})
                await conn.execute(
                    text(
                        "DELETE FROM dg_relations WHERE subject_id IN "
                        "(SELECT id FROM dg_entities WHERE domain='bid' AND norm_name LIKE '%' || :mark || '%') "
                        "OR object_id IN "
                        "(SELECT id FROM dg_entities WHERE domain='bid' AND norm_name LIKE '%' || :mark || '%')"
                    ),
                    {"mark": _MARK},
                )
                await conn.execute(text("DELETE FROM dg_entities WHERE domain='bid' AND norm_name LIKE '%' || :mark || '%'"), {"mark": _MARK})
        finally:
            await engine.dispose()

    try:
        first, again, ids_1, ids_2, n_ent = asyncio.run(_run())
        assert first["entities_upserted"] == 2 and first["relations"] == 1 and first["mentions"] == 3
        assert again["entities_upserted"] == 2  # ON CONFLICT 命中，不新建
        assert again["relations"] == 1
        assert ids_1 and ids_1 == ids_2  # 真幂等信号: id 集合逐次一致, 非仅计数不变
        assert n_ent == 2
    finally:
        asyncio.run(_cleanup())  # 断言失败也要清场（FK 顺序: mentions → relations → entities）
