"""T7 单测：registry lint 检查器（无 DB，纯模型元数据 + 注册表）.

计划: docs/superpowers/plans/2026-08-15-ontology-semantic-layer-1a.md T7（D7/D14）
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ontology_lint import check_coverage, check_data_source_access, check_hidden_sensitive, check_market_tables_registered, check_pk_immutability, main  # noqa: E402

from app.extensions.ontology.registry import load_registry  # noqa: E402


def test_all_checks_pass_on_real_registry():
    reg = load_registry()
    assert check_pk_immutability(reg) == []
    assert check_hidden_sensitive(reg) == []
    assert check_coverage(reg) == []
    assert check_market_tables_registered(reg) == []  # D14: cpa_/csp_ 全登记(run_history 白名单)
    assert check_data_source_access(reg) == []
    # 敏感 connection_config 已声明 hidden
    ds = reg.object_types["data_source"]
    cc = next(p for p in ds.properties if p.name == "connection_config")
    assert cc.hidden is True


def test_main_exit_zero():
    assert main() == 0


def test_market_table_rule_flags_unregistered():
    """同 PR 规则负向：白名单外的市场域表未登记 → 报错。"""

    class FakeReg:
        object_types = {o.api_name: o for o in load_registry().object_types.values() if o.access.path != "postgres_ext" or o.access.table not in ("cpa_documents", "cpa_items", "cpa_clusters")}

    errs = check_market_tables_registered(FakeReg())
    assert any("cpa_documents" in e for e in errs)
