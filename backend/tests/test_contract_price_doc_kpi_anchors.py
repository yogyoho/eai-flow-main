"""v3 规则生态(计划 docs/superpowers/plans/2026-09-19-cpa-table-recognition-three-layer.md Task 9/10):

- Task 9 NR 率 KPI: docs 列表附带 items_total/items_needs_review——一条 GROUP BY,零 N+1;
- Task 10 L4 锚词暂存: 人工修正/采纳追加 parse_meta.suggested_anchors(追加+去重,仅暂存不自动生效)。
"""

import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _literal(stmt) -> str:
    """Render a SQLAlchemy statement with bound values inlined for assertion."""
    from sqlalchemy.dialects import postgresql

    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


# --- Task 9: docs 列表 KPI 聚合 ----------------------------------------------


def _kpi_doc():
    from app.extensions.contract_price.models import CpaDocument

    return CpaDocument(
        storage_uri="s3://cpa-contracts/a.pdf",
        file_name="a.pdf",
        file_hash="h",
        file_type="pdf",
        parse_mode="ocr",
        parse_status="parsed",
    )


@pytest.mark.asyncio
async def test_list_documents_attaches_item_stats_with_single_group_by():
    """docs 列表每文档附带 items_total/items_needs_review;聚合只发一条 GROUP BY。"""
    from app.extensions.contract_price import crud

    doc = _kpi_doc()
    session = MagicMock()
    session.scalar = AsyncMock(return_value=1)  # 分页 count
    doc_result = MagicMock()
    doc_result.scalars.return_value.all.return_value = [doc]
    stats_result = MagicMock()
    stats_result.all.return_value = [(doc.id, 12, 3)]
    executed: list = []

    async def fake_execute(stmt, *a, **kw):
        executed.append(stmt)
        return doc_result if len(executed) == 1 else stats_result

    session.execute = fake_execute

    docs, total = await crud.list_documents(session, limit=20)
    assert total == 1
    assert docs[0] is doc
    assert doc.items_total == 12
    assert doc.items_needs_review == 3
    # 两条语句: 页查询 + 一条聚合(零 N+1)
    assert len(executed) == 2
    sql = _literal(executed[1])
    assert "cpa_items" in sql and "GROUP BY" in sql
    assert "needs_review" in sql  # 待核验计数走同一聚合


@pytest.mark.asyncio
async def test_list_documents_empty_page_skips_aggregation():
    """空页不发聚合查询。"""
    from app.extensions.contract_price import crud

    session = MagicMock()
    session.scalar = AsyncMock(return_value=0)
    doc_result = MagicMock()
    doc_result.scalars.return_value.all.return_value = []
    executed: list = []

    async def fake_execute(stmt, *a, **kw):
        executed.append(stmt)
        return doc_result

    session.execute = fake_execute

    docs, total = await crud.list_documents(session)
    assert docs == [] and total == 0
    assert len(executed) == 1


def test_document_out_serializes_kpi_fields():
    """DocumentOut(from_attributes) 能把 ORM 实例上的非映射属性带上线。"""
    from app.extensions.contract_price.schemas import DocumentOut

    doc = _kpi_doc()
    doc.id = uuid.uuid4()
    doc.confirm_status = "pending"  # 列默认值 flush 时才生效,序列化前手动补
    doc.created_at = datetime.now(UTC)
    doc.items_total = 7
    doc.items_needs_review = 2
    out = DocumentOut.model_validate(doc)
    assert out.items_total == 7
    assert out.items_needs_review == 2


# --- Task 10: L4 锚词暂存 -----------------------------------------------------


def test_merge_suggested_anchors_appends_and_dedups():
    """核心契约: 追加 + 去重(保序),入参不被原地改,空 additions 返回等价新 dict。"""
    from app.extensions.contract_price.crud import merge_suggested_anchors

    # parse_meta 为 None → 建骨架
    meta = merge_suggested_anchors(None, {"price_unit": ["含税单价", "综合单价"]})
    assert meta["suggested_anchors"] == {"price_unit": ["含税单价", "综合单价"]}

    # 追加: 既有词保留,新词排后
    meta2 = merge_suggested_anchors(meta, {"price_unit": ["含税单价", "调整后单价"]})
    assert meta2["suggested_anchors"]["price_unit"] == ["含税单价", "综合单价", "调整后单价"]

    # 去重: 重复词(含首尾空白)不再追加;新 role 单开桶;既有键不动
    meta3 = merge_suggested_anchors(meta2, {"price_unit": [" 综合单价 ", "网价"], "name": ["品名"]})
    assert meta3["suggested_anchors"]["price_unit"] == ["含税单价", "综合单价", "调整后单价", "网价"]
    assert meta3["suggested_anchors"]["name"] == ["品名"]

    # 入参不被原地改(JSONB 判脏依赖整体重赋值)
    assert meta["suggested_anchors"]["price_unit"] == ["含税单价", "综合单价"]
    # 空 additions → 内容等价但为新对象
    meta4 = merge_suggested_anchors(meta3, {})
    assert meta4["suggested_anchors"] == meta3["suggested_anchors"]
    assert meta4 is not meta3


def test_merge_suggested_anchors_tolerates_corrupt_store_and_blanks():
    from app.extensions.contract_price.crud import merge_suggested_anchors

    # 既有 suggested_anchors 形状损坏(非 dict 词表) → 不抛,重建骨架
    meta = merge_suggested_anchors({"suggested_anchors": {"price_unit": "not-a-list"}}, {"price_unit": ["含税单价"]})
    assert meta["suggested_anchors"]["price_unit"] == ["含税单价"]
    # 空串/空白/None 词丢弃
    meta2 = merge_suggested_anchors(meta, {"price_unit": ["  ", ""]})
    assert meta2["suggested_anchors"]["price_unit"] == ["含税单价"]


def test_header_word_for_price_infers_column_header():
    from app.extensions.contract_price.crud import _header_word_for_price

    rows = [
        ["钢筋供货及价格表", "", "", "", "", ""],
        ["物资名称", "材质", "计量单位", "暂定数量", "含税单价", "含税总价"],
        ["线材", "HPB300Φ8", "吨", "2.288", "6290", "14391.52"],
        ["盘圆", "HPB300 6mm", "吨", "100.000", "5037.00", "503700.00"],
    ]
    # 采纳/修正数据行的价 → 向上跳过数值数据行,命中内层表头
    assert _header_word_for_price(rows, 3, 5037.00) == "含税单价"
    assert _header_word_for_price(rows, 2, 6290) == "含税单价"
    # 千分位/单位后缀的单元格也能对上
    assert _header_word_for_price([["x", "a", "b"], ["1", "2", "76631.13"]], 1, 76631.13) == "b"
    # 人工手填价不在行内(纯手填) → 无法反推,不暂存
    assert _header_word_for_price(rows, 3, 9999.99) is None
    # 缺溯源/行号越界
    assert _header_word_for_price(rows, None, 5037.0) is None
    assert _header_word_for_price(rows, 99, 5037.0) is None
    assert _header_word_for_price([], 0, 1.0) is None


def _seed_item(doc_id):
    from app.extensions.contract_price.models import CpaItem

    return CpaItem(
        document_id=doc_id,
        goods_name="盘圆",
        unit_price=5037.0,
        source_page=2,
        source_table_idx=0,
        source_row_idx=3,
    )


_CACHE_ROWS = [
    ["钢筋供货及价格表", "", "", "", "", ""],
    ["物资名称", "材质", "计量单位", "暂定数量", "含税单价", "含税总价"],
    ["线材", "HPB300Φ8", "吨", "2.288", "6290", "14391.52"],
    ["盘圆", "HPB300 6mm", "吨", "100.000", "5037.00", "503700.00"],
]


@pytest.mark.asyncio
async def test_update_item_adopt_appends_suggested_anchor(monkeypatch):
    """采纳(ok)走 PATCH /items/{id} → crud.update_item:反推表头词追加进
    doc.parse_meta.suggested_anchors,既有 parse_meta 键保留,仅暂存。"""
    from app.extensions.contract_price import crud, storage
    from app.extensions.contract_price.models import CpaDocument, CpaItem

    doc_id = uuid.uuid4()
    item = _seed_item(doc_id)
    doc = CpaDocument(
        storage_uri="s3://cpa-contracts/k.pdf",
        file_name="k.pdf",
        file_hash="abc123",
        file_type="pdf",
        parse_mode="ocr",
        parse_status="parsed",
        parse_meta={"matched_seeds": {"钢筋供货价格表(上浦)": 1}},
    )

    session = MagicMock()

    async def fake_get(model, id_):
        if model is CpaItem:
            return item
        if model is CpaDocument:
            return doc
        return None

    session.get = AsyncMock(side_effect=fake_get)
    session.commit = AsyncMock()

    seen_keys: list[str] = []

    def fake_get_object(key: str) -> bytes:
        seen_keys.append(key)
        return json.dumps({"v": 2, "tables": [{"page_no": 2, "table_idx": 0, "rows": _CACHE_ROWS}]}).encode("utf-8")

    monkeypatch.setattr(storage, "get_object", fake_get_object)

    got = await crud.update_item(session, uuid.uuid4(), {"validation_status": "ok"})
    assert got is item
    assert seen_keys == ["ocr/abc123.json"]  # 内容寻址缓存键
    sa = doc.parse_meta["suggested_anchors"]
    assert sa["price_unit"] == ["含税单价"]
    assert doc.parse_meta["matched_seeds"] == {"钢筋供货价格表(上浦)": 1}  # 既有键保留
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_item_correction_dedups_on_repeat(monkeypatch):
    """修正路径同样追加;同词重复核验只记一次(去重)。"""
    from app.extensions.contract_price import crud, storage
    from app.extensions.contract_price.models import CpaDocument, CpaItem

    doc_id = uuid.uuid4()
    item = _seed_item(doc_id)
    doc = CpaDocument(
        storage_uri="s3://cpa-contracts/k.pdf",
        file_name="k.pdf",
        file_hash="abc123",
        file_type="pdf",
        parse_mode="ocr",
        parse_status="parsed",
        parse_meta={"suggested_anchors": {"price_unit": ["含税单价"]}},
    )

    session = MagicMock()

    async def fake_get(model, id_):
        return item if model is CpaItem else doc

    session.get = AsyncMock(side_effect=fake_get)
    session.commit = AsyncMock()
    monkeypatch.setattr(
        storage,
        "get_object",
        lambda key: json.dumps({"v": 2, "tables": [{"page_no": 2, "table_idx": 0, "rows": _CACHE_ROWS}]}).encode("utf-8"),
    )

    await crud.update_item(session, uuid.uuid4(), {"unit_price": 5037.0})
    assert doc.parse_meta["suggested_anchors"]["price_unit"] == ["含税单价"]  # 去重,不重复追加
    assert item.unit_price == 5037.0


@pytest.mark.asyncio
async def test_update_item_survives_missing_ocr_cache(monkeypatch):
    """缓存读失败(从未 OCR/MinIO 异常) → 修正照常落库,parse_meta 不被写坏。"""
    from app.extensions.contract_price import crud, storage
    from app.extensions.contract_price.models import CpaDocument, CpaItem

    doc_id = uuid.uuid4()
    item = _seed_item(doc_id)
    doc = CpaDocument(
        storage_uri="s3://cpa-contracts/k.pdf",
        file_name="k.pdf",
        file_hash="abc123",
        file_type="pdf",
        parse_mode="ocr",
        parse_status="parsed",
        parse_meta=None,
    )

    session = MagicMock()

    async def fake_get(model, id_):
        return item if model is CpaItem else doc

    session.get = AsyncMock(side_effect=fake_get)
    session.commit = AsyncMock()

    def boom(key: str) -> bytes:
        raise RuntimeError("minio down")

    monkeypatch.setattr(storage, "get_object", boom)

    got = await crud.update_item(session, uuid.uuid4(), {"unit_price": 12.34})
    assert got is item and got.unit_price == 12.34
    assert doc.parse_meta is None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_item_without_source_info_skips_harvest(monkeypatch):
    """缺溯源(source_page=None)不发缓存读。"""
    from app.extensions.contract_price import crud, storage
    from app.extensions.contract_price.models import CpaDocument, CpaItem

    doc_id = uuid.uuid4()
    item = _seed_item(doc_id)
    item.source_page = None
    doc = CpaDocument(
        storage_uri="s3://cpa-contracts/k.pdf",
        file_name="k.pdf",
        file_hash="abc123",
        file_type="pdf",
        parse_mode="ocr",
        parse_status="parsed",
        parse_meta=None,
    )

    session = MagicMock()

    async def fake_get(model, id_):
        return item if model is CpaItem else doc

    session.get = AsyncMock(side_effect=fake_get)
    session.commit = AsyncMock()

    def fail(key: str) -> bytes:
        raise AssertionError("缺溯源不应读缓存")

    monkeypatch.setattr(storage, "get_object", fail)

    got = await crud.update_item(session, uuid.uuid4(), {"validation_status": "ok"})
    assert got is item
    assert doc.parse_meta is None


@pytest.mark.asyncio
async def test_batch_validate_harvests_anchors_grouped_by_doc(monkeypatch):
    """批量采纳:同样收割锚词;同文档多 item 共享一次缓存读。"""
    from app.extensions.contract_price import crud, storage
    from app.extensions.contract_price.models import CpaDocument

    doc_id = uuid.uuid4()
    i1 = _seed_item(doc_id)
    i2 = _seed_item(doc_id)
    i2.source_row_idx = 2
    doc = CpaDocument(
        storage_uri="s3://cpa-contracts/k.pdf",
        file_name="k.pdf",
        file_hash="abc123",
        file_type="pdf",
        parse_mode="ocr",
        parse_status="parsed",
        parse_meta=None,
    )

    session = MagicMock()
    item_rows = MagicMock()
    item_rows.scalars.return_value.all.return_value = [i1, i2]
    upd_result = MagicMock()
    upd_result.rowcount = 2
    executed: list = []

    async def fake_execute(stmt, *a, **kw):
        executed.append(stmt)
        return upd_result if len(executed) == 1 else item_rows

    session.execute = fake_execute

    async def fake_get(model, id_):
        return doc if model is CpaDocument else None

    session.get = AsyncMock(side_effect=fake_get)
    session.commit = AsyncMock()

    reads = {"n": 0}

    def fake_get_object(key: str) -> bytes:
        reads["n"] += 1
        return json.dumps({"v": 2, "tables": [{"page_no": 2, "table_idx": 0, "rows": _CACHE_ROWS}]}).encode("utf-8")

    monkeypatch.setattr(storage, "get_object", fake_get_object)

    n = await crud.batch_validate_items(session, [uuid.uuid4(), uuid.uuid4()])
    assert n == 2
    assert reads["n"] == 1  # 同文档一次缓存读
    assert doc.parse_meta["suggested_anchors"]["price_unit"] == ["含税单价"]
    session.commit.assert_awaited_once()


def test_orm_base_picks_up_unmapped_kpi_attrs():
    """DocumentOut 的 KPI 字段来自非映射属性——缺省为 0(旧行为不破)。"""
    from app.extensions.contract_price.schemas import DocumentOut

    out = DocumentOut.model_validate(
        SimpleNamespace(
            id=uuid.uuid4(),
            file_name="a.pdf",
            storage_uri="s3://b/a.pdf",
            file_hash="h",
            file_type="pdf",
            parse_mode="ocr",
            parse_status="parsed",
            created_at=datetime.now(UTC),
        )
    )
    assert out.items_total == 0
    assert out.items_needs_review == 0


# --- review fix 2026-09-20: 收割的阻塞 IO 卸载出事件循环 ----------------------


def test_harvest_source_offloads_ocr_read_via_to_thread():
    """静态锚(与 service._resolve_llm_args 测试同型): OCR 缓存读必须经
    asyncio.to_thread 卸载——storage.get_object 是阻塞 MinIO 网络 read +
    整份大 JSON 解析,禁止跑在 gateway 事件循环上。"""
    import inspect

    from app.extensions.contract_price import crud

    src = inspect.getsource(crud._harvest_price_anchor)
    assert "asyncio.to_thread(_load_ocr_tables" in src
    assert inspect.iscoroutinefunction(crud._harvest_price_anchor)


@pytest.mark.asyncio
async def test_update_item_harvest_reads_cache_off_event_loop_thread(monkeypatch):
    """行为锚: update_item 触发的 OCR 缓存读在工作线程执行,不占调用方
    (事件循环)线程——人工核验点击不得阻塞 loop 上的流式 agent run。"""
    import threading

    from app.extensions.contract_price import crud, storage
    from app.extensions.contract_price.models import CpaDocument, CpaItem

    doc_id = uuid.uuid4()
    item = _seed_item(doc_id)
    doc = CpaDocument(
        storage_uri="s3://cpa-contracts/k.pdf",
        file_name="k.pdf",
        file_hash="abc123",
        file_type="pdf",
        parse_mode="ocr",
        parse_status="parsed",
        parse_meta=None,
    )

    session = MagicMock()

    async def fake_get(model, id_):
        return item if model is CpaItem else doc

    session.get = AsyncMock(side_effect=fake_get)
    session.commit = AsyncMock()

    caller_thread = threading.get_ident()
    read_threads: list[int] = []

    def fake_get_object(key: str) -> bytes:
        read_threads.append(threading.get_ident())
        return json.dumps({"v": 2, "tables": [{"page_no": 2, "table_idx": 0, "rows": _CACHE_ROWS}]}).encode("utf-8")

    monkeypatch.setattr(storage, "get_object", fake_get_object)

    await crud.update_item(session, uuid.uuid4(), {"validation_status": "ok"})
    assert read_threads == [read_threads[0]]  # 恰好一次缓存读
    assert read_threads[0] != caller_thread  # 卸载出事件循环线程


@pytest.mark.asyncio
async def test_batch_validate_harvest_reads_cache_off_event_loop_thread(monkeypatch):
    """批量采纳路径同样卸载: 缓存读不发生在事件循环线程。"""
    import threading

    from app.extensions.contract_price import crud, storage
    from app.extensions.contract_price.models import CpaDocument

    doc_id = uuid.uuid4()
    item = _seed_item(doc_id)
    doc = CpaDocument(
        storage_uri="s3://cpa-contracts/k.pdf",
        file_name="k.pdf",
        file_hash="abc123",
        file_type="pdf",
        parse_mode="ocr",
        parse_status="parsed",
        parse_meta=None,
    )

    session = MagicMock()
    item_rows = MagicMock()
    item_rows.scalars.return_value.all.return_value = [item]
    upd_result = MagicMock()
    upd_result.rowcount = 1
    executed: list = []

    async def fake_execute(stmt, *a, **kw):
        executed.append(stmt)
        return upd_result if len(executed) == 1 else item_rows

    session.execute = fake_execute

    async def fake_get(model, id_):
        return doc if model is CpaDocument else None

    session.get = AsyncMock(side_effect=fake_get)
    session.commit = AsyncMock()

    caller_thread = threading.get_ident()
    read_threads: list[int] = []

    def fake_get_object(key: str) -> bytes:
        read_threads.append(threading.get_ident())
        return json.dumps({"v": 2, "tables": [{"page_no": 2, "table_idx": 0, "rows": _CACHE_ROWS}]}).encode("utf-8")

    monkeypatch.setattr(storage, "get_object", fake_get_object)

    await crud.batch_validate_items(session, [uuid.uuid4()])
    assert read_threads == [read_threads[0]]
    assert read_threads[0] != caller_thread
