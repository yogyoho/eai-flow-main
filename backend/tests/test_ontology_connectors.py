"""T4 单测：双 connector——只读守卫单一真源 / same() 判定 / 断连显式 / LIMIT 共存.

设计: docs/superpowers/specs/2026-08-14-ontology-semantic-layer-design.md §17（复用边界）
计划: docs/superpowers/plans/2026-08-15-ontology-semantic-layer-1a.md T4 Verify
"""

from __future__ import annotations

import pytest

from app.extensions.data_source.service import assert_readonly_select
from app.extensions.ontology.connectors import ConnectorError, OntologyConnectors
from app.extensions.ontology.schemas import AccessConfig


def _access(path: str, table: str | None = None, source_id: str | None = None, table_name: str | None = None) -> AccessConfig:
    return AccessConfig.model_validate({"path": path, "table": table, "source_id": source_id, "table_name": table_name})


def test_security_single_source_is_data_source_guard():
    """D9: assert_readonly_select import 自 data_source（同一函数对象，非复制）。"""
    import app.extensions.ontology.connectors as c

    assert c.assert_readonly_select is assert_readonly_select


@pytest.mark.asyncio
async def test_fetch_rejects_write_verbs_before_connecting():
    """写动词在连接前被守卫拒绝（fail-closed；含 CTE 写绕过）。"""
    con = OntologyConnectors()
    with pytest.raises(ValueError, match="仅允许"):
        await con.fetch(_access("postgres_ext", table="cpa_items"), "DELETE FROM cpa_items")
    with pytest.raises(ValueError, match="仅允许"):
        await con.fetch(_access("postgres_ext", table="cpa_items"), "UPDATE cpa_items SET x=1")
    with pytest.raises(ValueError, match="写操作"):
        await con.fetch(_access("postgres_ext", table="cpa_items"), "WITH d AS (DELETE FROM cpa_items) SELECT * FROM d")


@pytest.mark.asyncio
async def test_fetch_binds_params_and_forces_limit():
    """绑定参数透传 + LIMIT 200 追加共存（SELECT 1 无 LIMIT → 追加后可执行）。"""
    con = OntologyConnectors()
    rows = await con.fetch(_access("postgres_ext", table="cpa_documents"), "SELECT :v AS v", {"v": "x"})
    assert rows == [{"v": "x"}]
    # 引擎 SQL 自带 LIMIT 时 guard 不重复追加
    assert "LIMIT 5" in assert_readonly_select("SELECT 1 LIMIT 5")


def test_same_connector_semantics():
    con = OntologyConnectors()
    ext = _access("postgres_ext", table="cpa_items")
    assert con.same(ext, _access("postgres_ext", table="cpa_documents"))  # 扩展库单库 → 同
    ds1 = _access("data_source", source_id="bid-quote", table_name="mock_bid")
    assert con.same(ds1, _access("data_source", source_id="bid-quote", table_name="mock_bid_item"))
    assert not con.same(ds1, ext)  # 跨路径 → 分块应用侧 join
    assert not con.same(ds1, _access("data_source", source_id="other", table_name="x"))


@pytest.mark.asyncio
async def test_unregistered_data_source_explicit_error():
    """断连/未注册 → 显式 ConnectorError（绝不静默空结果）。"""
    con = OntologyConnectors()
    with pytest.raises(ConnectorError, match="未注册"):
        await con.fetch(_access("data_source", source_id="no-such-source", table_name="t"), "SELECT 1")
    out = await con.availability([_access("data_source", source_id="no-such-source", table_name="t")])
    assert out == {"data_source:no-such-source": False}


@pytest.mark.asyncio
async def test_availability_postgres_ext_ok_in_dev():
    """容器内扩展库可达 → available True（dev 集成断言）。"""
    con = OntologyConnectors()
    out = await con.availability([_access("postgres_ext", table="cpa_items")])
    assert out["postgres_ext:cpa_items"] is True
