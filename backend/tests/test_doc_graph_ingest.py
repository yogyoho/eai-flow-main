"""doc_graph 入库集成测试——需 extensions 库且 dg_* 表已建; 否则自动 skip.

URL 解析与 connectors._ext_url 同语义: env 优先, 回退 extensions config。
但默认 DatabaseConfig 恒产出 localhost URL（容器外也不为 None）, 仅凭 URL 存在判定 skip 会在
CI(无库连接拒绝)与表未建环境(ProgrammingError)下直接报错——故以 dg_entities 表存在性探针兜底。
真库 roundtrip 验证在容器内 E2E（Task 9）。
"""

import asyncio
import os

import pytest

from app.extensions.ontology.doc_graph.schemas import BidExtraction


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

        engine = create_async_engine(url, poolclass=NullPool)
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


def _payload() -> dict:
    return {
        "domain": "bid",
        "thread_id": "t-test",
        "entities": [
            {"etype": "project", "name": "横城煤矿东翼回风大巷工程", "mention": {"document_id": "doc-ing-1", "quote": "横城煤矿东翼回风大巷工程施工招标"}},
            {"etype": "bidder", "name": "山西煤机集团", "confidence": 0.9, "mention": {"document_id": "doc-ing-1", "quote": "投标人：山西煤机集团"}},
        ],
        "relations": [{"predicate": "bidder_of_project", "subject": "山西煤机集团", "object": "横城煤矿东翼回风大巷工程", "mention": {"document_id": "doc-ing-1", "quote": "山西煤机集团投标横城煤矿项目"}}],
    }


def test_ingest_roundtrip_and_idempotent():
    """首投建行; 同 payload 重投不产生新实体（幂等）; mention 证据追加。"""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.extensions.ontology.doc_graph.ingest import ingest_extraction

    async def _run():
        p = BidExtraction.model_validate(_payload())
        first = await ingest_extraction(p)
        again = await ingest_extraction(p)

        engine = create_async_engine(_URL, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                n_a = (await conn.execute(text("SELECT COUNT(*) FROM dg_entities WHERE domain='bid' AND norm_name LIKE '%横城%'"))).scalar_one()
                n_b = (await conn.execute(text("SELECT COUNT(*) FROM dg_entities WHERE domain='bid' AND norm_name LIKE '%山西煤机%'"))).scalar_one()
        finally:
            await engine.dispose()
        return first, again, n_a, n_b

    first, again, n_a, n_b = asyncio.run(_run())
    assert first["entities_upserted"] == 2 and first["relations"] == 1 and first["mentions"] == 3
    assert again["entities_upserted"] == 2  # ON CONFLICT 命中，不新建
    assert again["relations"] == 1
    assert n_a == 1 and n_b == 1

    # 清理（FK 顺序: mentions → relations → entities; 按本测试的冒烟实体名精确圈定, 不误删他人数据）
    async def _cleanup():
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        engine = create_async_engine(_URL, poolclass=NullPool)
        try:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM dg_mentions WHERE document_id = 'doc-ing-1'"))
                await conn.execute(
                    text(
                        "DELETE FROM dg_relations WHERE subject_id IN "
                        "(SELECT id FROM dg_entities WHERE domain='bid' AND (norm_name LIKE '%横城%' OR norm_name LIKE '%山西煤机%')) "
                        "OR object_id IN "
                        "(SELECT id FROM dg_entities WHERE domain='bid' AND (norm_name LIKE '%横城%' OR norm_name LIKE '%山西煤机%'))"
                    )
                )
                await conn.execute(text("DELETE FROM dg_entities WHERE domain='bid' AND (norm_name LIKE '%横城%' OR norm_name LIKE '%山西煤机%')"))
        finally:
            await engine.dispose()

    asyncio.run(_cleanup())
