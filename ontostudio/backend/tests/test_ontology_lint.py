"""T7 单测：registry lint 检查器（无 DB，纯模型元数据 + 注册表）.

计划: docs/superpowers/plans/2026-08-15-ontology-semantic-layer-1a.md T7（D7/D14）
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ontology_lint import check_coverage, check_data_source_access, check_hidden_sensitive, check_market_tables_registered, check_pk_immutability, main  # noqa: E402

from app.ontology.registry import load_registry  # noqa: E402


def test_all_checks_pass_on_real_registry():
    reg = load_registry()
    assert check_pk_immutability(reg) == []
    assert check_hidden_sensitive(reg) == []
    assert check_coverage(reg) == []
    # D14: 本服务 metadata 内的 SCOPE 表(dg_*)全登记(run_history/dg_merges 白名单)。
    # EAI-CUSTOM(迁出独立): cpa_/csp_ 模型属 gateway, 不入独立服务 metadata——其登记约束
    # 由 registry 声明侧 + gateway 侧承管, 此处只守本服务可见域。
    assert check_market_tables_registered(reg) == []
    assert check_data_source_access(reg) == []
    # 敏感 connection_config 已声明 hidden
    ds = reg.object_types["data_source"]
    cc = next(p for p in ds.properties if p.name == "connection_config")
    assert cc.hidden is True


def test_main_exit_zero():
    assert main() == 0


def test_market_table_rule_flags_unregistered():
    """同 PR 规则负向：白名单外的市场域表未登记 → 报错。

    EAI-CUSTOM(2026-09-17 迁出独立): 原版依赖 backend 侧 contract_price.models 把
    cpa_documents 注册进 Base.metadata; 独立服务无 gateway 模型 → 测试自注册同形元数据表
    （finally 移除, 不污染其他用例）, 规则本体不变。
    """
    from sqlalchemy import Column, Integer, Table

    from app.db import Base

    tbl = Table("cpa_documents", Base.metadata, Column("id", Integer, primary_key=True))
    try:

        class FakeReg:
            object_types = {o.api_name: o for o in load_registry().object_types.values() if o.access.path != "postgres_ext" or o.access.table not in ("cpa_documents", "cpa_items", "cpa_clusters")}

        errs = check_market_tables_registered(FakeReg())
        assert any("cpa_documents" in e for e in errs)
    finally:
        Base.metadata.remove(tbl)


def test_doc_graph_tables_registered():
    """doc_graph 域上线即登记（同 PR 规则）: 对外 dg_* 表全部登记; dg_merges 内部审计表白名单豁免。"""
    import app.doc_graph.tables  # noqa: F401
    from app.db import Base
    from app.ontology.registry import load_registry

    reg = load_registry()
    registered = {o.access.table for o in reg.object_types.values() if o.access.path == "postgres_ext" and o.access.table}
    dg_scoped = {n for n in Base.metadata.tables if n.startswith("dg_")} - {"dg_merges"}
    assert dg_scoped <= registered
    assert "dg_merges" not in registered  # 内部审计表, 白名单豁免不登记
