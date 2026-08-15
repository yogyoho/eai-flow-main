# EAI-CUSTOM: 备品备件价格体系分析扩展测试(forked from test_contract_price_extension.py)。
"""Tests for the spare_parts extension (④ 备品备件价格体系分析).

只测"存在 + 高风险"部分:模型注册、MCP 5 工具注册与分发、客户归一(_resolve_customer_id)、
跨客户比价偏离阈值与排序(compare_by_customer,④ 特色)、分项聚合与 needs_review 排除、
总览/异常结构、扩展↔技能模型 parity。管理层 CRUD(routers/service/crud)延后 T7,此处不测。

MCP 聚合逻辑用 monkeypatch 假 _run_in_db 喂入 canned CspItem 行,隔离并精确测"能算错数字"
的分组/偏离/过滤数学。客户归一直接 mock session。无需活库。
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── 1. 模型注册 ──


def test_csp_models_registered_on_shared_base():
    """导入 spare_parts 包应把 csp_ 5 表注册到共享 Base.metadata(gateway init_db 建表前提)。"""
    import app.extensions.spare_parts  # noqa: F401
    from app.extensions.database import Base

    assert {
        "csp_documents",
        "csp_items",
        "csp_clusters",
        "csp_customers",
        "csp_run_history",
    } <= set(Base.metadata.tables)


# ── 2. MCP 工具注册与分发 ──


def test_mcp_registers_five_tools_and_dispatch_covers_all():
    import inspect

    from app.extensions.spare_parts import mcp

    names = {t.name for t in mcp.TOOLS}
    assert names == {
        "spare_part_summary",
        "query_part_price",
        "compare_part_price_by_customer",
        "list_part_price_outliers",
        "customer_parts_contracts",
    }
    # dispatch 字典在 call_tool 闭包内;unwrap 后核对每个工具名都有 handler。
    inner = inspect.unwrap(mcp.call_tool)
    src = inspect.getsource(inner)
    for n in names:
        assert n in src, f"tool {n} 未在 dispatch 字典中"


@pytest.mark.asyncio
async def test_call_tool_unknown_returns_unknown_message():
    from app.extensions.spare_parts import mcp

    out = await mcp.call_tool("nope", {})
    assert "Unknown tool" in out[0].text


# ── 3. 客户归一 _resolve_customer_id (D3) ──


def _mock_session_returning_customers(rows):
    """session.execute(select(CspCustomer)) → .scalars().all() = rows。"""
    session = MagicMock()
    result = MagicMock()
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=rows)))
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_resolve_customer_id_hits_canonical():
    from app.extensions.spare_parts import mcp
    from app.extensions.spare_parts.models import CspCustomer

    c = CspCustomer(canonical_name="桂北矿业集团", aliases=["桂北矿业"], status="active")
    cid, canonical, pending = await mcp._resolve_customer_id(_mock_session_returning_customers([c]), "桂北矿业集团")
    assert canonical == "桂北矿业集团"
    assert pending is False


@pytest.mark.asyncio
async def test_resolve_customer_id_hits_alias():
    from app.extensions.spare_parts import mcp
    from app.extensions.spare_parts.models import CspCustomer

    c = CspCustomer(canonical_name="桂北矿业集团", aliases=["桂北矿业", "GBKY"], status="active")
    _, canonical, _ = await mcp._resolve_customer_id(_mock_session_returning_customers([c]), "桂北矿业")
    assert canonical == "桂北矿业集团"  # 别名命中 → 规范名


@pytest.mark.asyncio
async def test_resolve_customer_id_miss_returns_none():
    from app.extensions.spare_parts import mcp
    from app.extensions.spare_parts.models import CspCustomer

    c = CspCustomer(canonical_name="另一家", aliases=[], status="active")
    cid, canonical, pending = await mcp._resolve_customer_id(_mock_session_returning_customers([c]), "查无此客户")
    assert cid is None and canonical is None  # 只读,未命中不新建(与 normalizer 区别)


# ── helpers: canned CspItem 行 ──


def _item(part_name, customer_id, customer_name, price, status="ok", outlier=False, contract="C-001"):
    from app.extensions.spare_parts.models import CspItem

    it = CspItem(
        part_name=part_name,
        customer_id=customer_id,
        customer_name=customer_name,
        unit_price=price,
        validation_status=status,
        is_outlier=outlier,
        source_contract_no=contract,
        spec=None,
    )
    it.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    return it


def _fake_run_in_db_returning(rows):
    """返回一个 async 假 _run_in_db,丢弃 qfunc 的 session 查询,直接喂 rows。"""

    async def _fake(qfunc):
        return rows

    return _fake


# ── 4. compare_part_price_by_customer(④ 特色:偏离阈值 + 排序)──


@pytest.mark.asyncio
async def test_compare_by_customer_deviation_thresholds_and_sort(monkeypatch):
    """A 均价 105 / 整体中位 155 = 0.68 → 低于均值;B 均价 205 / 155 = 1.32 → 高于均值;
    按均价降序:B 在前。"""
    from app.extensions.spare_parts import mcp

    cid_a, cid_b = uuid.uuid4(), uuid.uuid4()
    rows = [
        _item("闸阀DN100", cid_a, "客户A", 100, contract="CA"),
        _item("闸阀DN100", cid_a, "客户A", 110, contract="CA"),
        _item("闸阀DN100", cid_b, "客户B", 200, contract="CB"),
        _item("闸阀DN100", cid_b, "客户B", 210, contract="CB"),
    ]
    monkeypatch.setattr(mcp, "_run_in_db", _fake_run_in_db_returning(rows))

    out = await mcp._handle_compare_by_customer({"part_name": "闸阀"})
    d = json.loads(out[0].text)
    assert d["matched_items"] == 4
    assert d["customer_count"] == 2
    by = d["by_customer"]
    assert by[0]["customer_name"] == "客户B"  # 均价高在前
    assert by[0]["deviation_vs_overall"] == "高于均值"
    assert by[1]["customer_name"] == "客户A"
    assert by[1]["deviation_vs_overall"] == "低于均值"
    assert d["overall_stats"]["median"] == 155


@pytest.mark.asyncio
async def test_compare_by_customer_no_match_message(monkeypatch):
    from app.extensions.spare_parts import mcp

    monkeypatch.setattr(mcp, "_run_in_db", _fake_run_in_db_returning([]))
    out = await mcp._handle_compare_by_customer({"part_name": "不存在"})
    d = json.loads(out[0].text)
    assert d["matched"] == 0


@pytest.mark.asyncio
async def test_compare_by_customer_excludes_needs_review_from_stats(monkeypatch):
    """needs_review 价格不计入统计(同聚类规则),但项仍计入 item_count。"""
    from app.extensions.spare_parts import mcp

    cid = uuid.uuid4()
    rows = [
        _item("轴承", cid, "客户A", 100, status="ok"),
        _item("轴承", cid, "客户A", 9999, status="needs_review"),  # 排除
    ]
    monkeypatch.setattr(mcp, "_run_in_db", _fake_run_in_db_returning(rows))
    out = await mcp._handle_compare_by_customer({"part_name": "轴承"})
    d = json.loads(out[0].text)
    g = d["by_customer"][0]
    assert g["item_count"] == 2  # 两项都在
    assert g["priced_count"] == 1  # 但只 1 项入统计
    assert g["price_stats"]["mean"] == 100


# ── 5. query_part_price(分组 + needs_review 排除 + 置信提示)──


@pytest.mark.asyncio
async def test_query_part_groups_by_name_and_flags_low_confidence(monkeypatch):
    from app.extensions.spare_parts import mcp

    rows = [
        _item("闸阀DN100", None, None, 100, status="ok"),
        _item("闸阀DN100", None, None, 999, status="needs_review"),
        _item("闸阀DN200", None, None, 200, status="ok"),
    ]
    monkeypatch.setattr(mcp, "_run_in_db", _fake_run_in_db_returning(rows))
    out = await mcp._handle_query_part({"part_name": "闸阀"})
    d = json.loads(out[0].text)
    assert d["matched_items"] == 3
    assert d["matched_names"] == 2
    groups = {g["part_name"]: g for g in d["groups"]}
    # DN100: nr(1) >= ok+corr(1) → 仅供参考;priced 只含 100
    assert groups["闸阀DN100"]["price_stats"]["mean"] == 100
    assert groups["闸阀DN100"]["confidence_note"] is not None
    assert groups["闸阀DN200"]["confidence_note"] is None


@pytest.mark.asyncio
async def test_query_part_no_match(monkeypatch):
    from app.extensions.spare_parts import mcp

    monkeypatch.setattr(mcp, "_run_in_db", _fake_run_in_db_returning([]))
    out = await mcp._handle_query_part({"part_name": "zzz"})
    assert json.loads(out[0].text)["matched"] == 0


# ── 6. summary / outliers 结构 ──


@pytest.mark.asyncio
async def test_handle_summary_payload_shape(monkeypatch):
    from app.extensions.spare_parts import mcp

    async def fake(qfunc):
        return {"docs": 3, "items": 10, "clusters": 2, "customers": 2, "pending_clusters": 1, "pending_customers": 0, "needs_review": 1, "price_min": 5.0, "price_max": 500.0, "price_avg": 120.5}

    monkeypatch.setattr(mcp, "_run_in_db", fake)
    out = await mcp._handle_summary({})
    d = json.loads(out[0].text)
    assert d["success"] is True
    assert d["docs"] == 3 and d["customers"] == 2
    assert d["price_avg"] == 120.5


@pytest.mark.asyncio
async def test_handle_outliers_count_and_desc_sort(monkeypatch):
    """假 _run_in_db 跳过了 handler 的 WHERE is_outlier 查询,故这里喂"真实查询会返回的"
    纯离群行,验证 count 与 ORDER BY unit_price DESC。is_outlier 过滤本身是平凡单 WHERE,
    在活库验证(T5)已覆盖。"""
    from app.extensions.spare_parts import mcp

    # 喂入真实查询会返回的顺序(ORDER BY unit_price DESC);handler 不在 Python 层重排。
    rows = [
        _item("阀C", None, None, 300, outlier=True),
        _item("阀A", None, None, 100, outlier=True),
    ]
    monkeypatch.setattr(mcp, "_run_in_db", _fake_run_in_db_returning(rows))
    out = await mcp._handle_outliers({})
    d = json.loads(out[0].text)
    assert d["count"] == 2
    prices = [o["unit_price"] for o in d["outliers"]]
    assert prices == [300.0, 100.0]  # handler float() + 保留查询 desc 顺序


# ── 7. customer_parts_contracts ──


@pytest.mark.asyncio
async def test_customer_parts_resolves_then_groups(monkeypatch):
    """_q 内先 _resolve_customer_id 命中,再按 part 分组。整体用真实 _q + mock session 跑通。"""
    from app.extensions.spare_parts import mcp
    from app.extensions.spare_parts.models import CspCustomer

    cust = CspCustomer(canonical_name="客户A", aliases=[], status="active")
    cust.id = uuid.uuid4()
    items = [
        _item("轴承", cust.id, "客户A", 100),
        _item("轴承", cust.id, "客户A", 120),
        _item("阀门", cust.id, "客户A", 200),
    ]

    def session_with(rows):
        s = MagicMock()
        # 第一次 execute: select(CspCustomer) → resolve
        # 第二次 execute: select(CspItem).where(customer_id==) → items
        cust_res = MagicMock()
        cust_res.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[cust])))
        item_res = MagicMock()
        item_res.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=rows)))
        s.execute = AsyncMock(side_effect=[cust_res, item_res])
        return s

    async def fake_run_in_db(qfunc):
        return await qfunc(session_with(items))

    monkeypatch.setattr(mcp, "_run_in_db", fake_run_in_db)
    out = await mcp._handle_customer_parts({"customer_name": "客户A"})
    d = json.loads(out[0].text)
    assert d["success"] is True
    assert d["customer_name"] == "客户A"
    assert d["matched_items"] == 3
    assert d["part_count"] == 2
    parts = {p["part_name"]: p for p in d["parts"]}
    assert parts["轴承"]["price_stats"]["mean"] == 110


@pytest.mark.asyncio
async def test_customer_parts_not_found(monkeypatch):
    from app.extensions.spare_parts import mcp

    def session_empty():
        s = MagicMock()
        res = MagicMock()
        res.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        s.execute = AsyncMock(return_value=res)
        return s

    async def fake_run_in_db(qfunc):
        return await qfunc(session_empty())

    monkeypatch.setattr(mcp, "_run_in_db", fake_run_in_db)
    out = await mcp._handle_customer_parts({"customer_name": "查无"})
    d = json.loads(out[0].text)
    assert d["matched"] == 0


# ── 8. 模型 parity(扩展 canonical ↔ 技能 mirror,同物理表)──

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILL_MODELS = _REPO_ROOT / "skills" / "public" / "spare-parts-analysis" / "scripts" / "models.py"

_TABLES: dict[str, str] = {
    "csp_documents": "CspDocument",
    "csp_items": "CspItem",
    "csp_clusters": "CspCluster",
    "csp_customers": "CspCustomer",
    "csp_run_history": "CspRunHistory",
}


def _load_skill_models():
    spec = importlib.util.spec_from_file_location("csp_skill_models", _SKILL_MODELS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _columns(module, class_name):
    return sorted((col.name, str(col.type)) for col in getattr(module, class_name).__table__.columns)


def test_csp_models_in_sync_with_skill_mirror():
    """扩展(canonical)与技能(mirror)csp_ 表必须逐列一致,否则读写静默错位。"""
    from app.extensions.spare_parts import models as ext_models

    skill_models = _load_skill_models()
    drift = []
    for table_name, class_name in _TABLES.items():
        ext_cols = _columns(ext_models, class_name)
        skill_cols = _columns(skill_models, class_name)
        if ext_cols != skill_cols:
            ext_only = sorted(set(ext_cols) - set(skill_cols))
            skill_only = sorted(set(skill_cols) - set(ext_cols))
            drift.append(f"\n  [{table_name}]\n    extension-only: {ext_only}\n    skill-only: {skill_only}")
    assert not drift, "csp_ 模型在扩展(backend/app/extensions/spare_parts/models.py)与技能 mirror(skills/public/spare-parts-analysis/scripts/models.py)间漂移,二者描述同一组物理表,请对齐:" + "".join(drift)
