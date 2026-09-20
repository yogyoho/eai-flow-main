"""EAI-CUSTOM F3a 离群语义分层 — 后端簇统计透传测试。

覆盖 crud._attach_cluster_stats(list_items / get_cluster_with_items /
goods_analysis 三条查询链路的一条 JOIN 聚合预取)与 ItemOut 新字段默认值。
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.extensions.contract_price import crud
from app.extensions.contract_price.models import CpaCluster, CpaDocument, CpaItem


def _item(
    *,
    unit_price=None,
    cluster_id=None,
    is_outlier=False,
    goods_name="螺纹钢",
    validation_status="ok",
    doc_id=None,
):
    it = CpaItem(
        id=uuid.uuid4(),
        document_id=doc_id or uuid.uuid4(),
        goods_name=goods_name,
        unit_price=unit_price,
        cluster_id=cluster_id,
        is_outlier=is_outlier,
        validation_status=validation_status,
        source_contract_no="2GS-TEST",
        created_at=datetime.now(UTC),
    )
    return it


def _items_result(items):
    """mock session.execute 返回 scalars().all() 形态(ORM 列表)。"""
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    return result


def _rows_result(rows):
    """mock session.execute 返回 .all() 元组行形态(聚合/联表)。"""
    result = MagicMock()
    result.all.return_value = rows
    return result


def test_item_out_cluster_stat_fields_default_none():
    """ItemOut 新增簇统计字段默认 None;裸 ORM 实例(未挂属性)经
    from_attributes 校验也不报错(pydantic 回退默认值)——PATCH /items/{id}
    等未走预取的响应依赖此行为。"""
    from app.extensions.contract_price.schemas import ItemOut

    out = ItemOut(id=uuid.uuid4(), document_id=uuid.uuid4(), goods_name="x", created_at=datetime.now(UTC))
    assert out.cluster_median is None
    assert out.deviation_pct is None
    assert out.cluster_doc_count is None

    bare = _item(unit_price=110.0)  # 未经过 _attach_cluster_stats 的 ORM 实例
    out2 = ItemOut.model_validate(bare)
    assert out2.cluster_median is None
    assert out2.deviation_pct is None
    assert out2.cluster_doc_count is None
    assert out2.unit_price == 110.0


@pytest.mark.asyncio
async def test_attach_cluster_stats_fills_fields():
    """有簇行挂 cluster_median/deviation_pct/cluster_doc_count;无簇行保持 None。"""
    cid = uuid.uuid4()
    it1 = _item(unit_price=110.0, cluster_id=cid)
    it2 = _item(unit_price=90.0, cluster_id=cid)
    it3 = _item(unit_price=50.0, cluster_id=None)  # 无簇
    session = MagicMock()
    session.execute = AsyncMock(return_value=_rows_result([(cid, {"median": 100.0, "count": 5}, 2)]))

    await crud._attach_cluster_stats(session, [it1, it2, it3])

    assert it1.cluster_median == 100.0
    assert it1.deviation_pct == pytest.approx(0.10)  # (110-100)/100
    assert it1.cluster_doc_count == 2
    assert it2.deviation_pct == pytest.approx(-0.10)
    # 无簇行: 三个字段都不该被赋值
    assert it3.cluster_median is None
    assert it3.deviation_pct is None
    assert it3.cluster_doc_count is None


@pytest.mark.asyncio
async def test_attach_cluster_stats_edge_cases():
    """中位为 0 / 行无价 / stats 缺 median / 簇不在聚合结果 → 各字段优雅降级。"""
    cid_zero = uuid.uuid4()
    cid_nomedian = uuid.uuid4()
    cid_missing = uuid.uuid4()
    it_zero = _item(unit_price=80.0, cluster_id=cid_zero)
    it_no_price = _item(unit_price=None, cluster_id=cid_zero)
    it_nomedian = _item(unit_price=80.0, cluster_id=cid_nomedian)
    it_missing = _item(unit_price=80.0, cluster_id=cid_missing)
    rows = [
        (cid_zero, {"median": 0, "count": 3}, 1),
        (cid_nomedian, {"count": 3}, 1),  # stats 里没有 median 键
    ]
    session = MagicMock()
    session.execute = AsyncMock(return_value=_rows_result(rows))

    await crud._attach_cluster_stats(session, [it_zero, it_no_price, it_nomedian, it_missing])

    assert it_zero.cluster_median == 0.0
    assert it_zero.deviation_pct is None  # 中位为 0 → 偏离无定义
    assert it_no_price.cluster_median == 0.0
    assert it_no_price.deviation_pct is None  # 行无价
    assert it_nomedian.cluster_median is None
    assert it_nomedian.deviation_pct is None
    # 簇不在结果里(理论上不会发生): 统计缺省为 None/0,不抛错
    assert it_missing.cluster_median is None
    assert it_missing.cluster_doc_count == 0


@pytest.mark.asyncio
async def test_attach_cluster_stats_empty_and_clusterless():
    """空列表 / 全无簇 → 不发查询直接返回。"""
    session = MagicMock()
    session.execute = AsyncMock()
    await crud._attach_cluster_stats(session, [])
    session.execute.assert_not_awaited()

    no_cluster = [_item(unit_price=1.0), _item(unit_price=2.0)]
    await crud._attach_cluster_stats(session, no_cluster)
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_items_attaches_cluster_stats():
    """GET /items 查询链路: 取页 + 一次聚合预取(共 2 次 execute),行上带簇统计。"""
    cid = uuid.uuid4()
    it1 = _item(unit_price=110.0, cluster_id=cid, is_outlier=True)
    session = MagicMock()
    session.scalar = AsyncMock(return_value=7)
    session.execute = AsyncMock(
        side_effect=[
            _items_result([it1]),
            _rows_result([(cid, {"median": 100.0, "count": 9}, 4)]),
        ]
    )

    items, total = await crud.list_items(session, only_outliers=True, limit=10)

    assert total == 7
    assert len(items) == 1
    assert items[0].cluster_median == 100.0
    assert items[0].deviation_pct == pytest.approx(0.10)
    assert items[0].cluster_doc_count == 4
    assert session.execute.await_count == 2  # 页查询 + 聚合预取,零 N+1


@pytest.mark.asyncio
async def test_get_cluster_with_items_attaches_cluster_stats():
    """GET /clusters/{id} 明细行同样附带簇统计。"""
    cid = uuid.uuid4()
    cluster = CpaCluster(id=cid, category="未分类", representative_name="螺纹钢", status="pending", item_count=2)
    it1 = _item(unit_price=120.0, cluster_id=cid, is_outlier=True)
    it2 = _item(unit_price=98.0, cluster_id=cid)
    session = MagicMock()
    session.get = AsyncMock(return_value=cluster)
    session.execute = AsyncMock(
        side_effect=[
            _items_result([it1, it2]),
            _rows_result([(cid, {"median": 100.0, "count": 9}, 3)]),
        ]
    )

    got = await crud.get_cluster_with_items(session, cid)

    assert got is cluster
    assert got.items[0].cluster_median == 100.0
    assert got.items[0].deviation_pct == pytest.approx(0.20)
    assert got.items[0].cluster_doc_count == 3
    assert got.items[1].deviation_pct == pytest.approx(-0.02)


@pytest.mark.asyncio
async def test_goods_analysis_detail_includes_cluster_stats():
    """跨合同货物分析明细行带 cluster_id/cluster_median/deviation_pct/cluster_doc_count。"""
    cid = uuid.uuid4()
    doc = CpaDocument(
        id=uuid.uuid4(),
        storage_uri="s3://cpa-contracts/a.pdf",
        file_name="a.pdf",
        file_hash="h",
        file_type="pdf",
        supplier="某供应商",
    )
    it1 = _item(unit_price=110.0, cluster_id=cid, is_outlier=True, doc_id=doc.id)
    it2 = _item(unit_price=100.0, cluster_id=cid, doc_id=doc.id)
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=[
            _rows_result([(it1, doc), (it2, doc)]),
            _rows_result([(cid, {"median": 100.0, "count": 2}, 1)]),
        ]
    )

    out = await crud.goods_analysis(session, name="螺纹钢", skip=0, limit=50)

    assert out["total"] == 2
    row1 = next(r for r in out["items"] if r["unit_price"] == 110.0)
    row2 = next(r for r in out["items"] if r["unit_price"] == 100.0)
    assert row1["cluster_id"] == str(cid)
    assert row1["cluster_median"] == 100.0
    assert row1["deviation_pct"] == pytest.approx(0.10)
    assert row1["cluster_doc_count"] == 1
    assert row2["cluster_id"] == str(cid)
