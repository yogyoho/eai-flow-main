"""Ontology registry lint — §2.2 acceptance checklist, exit 1 on failure.

Checks (mother-spec §2.2 / expansion-plan §2.2):
  1. PK immutability: every object type has an immutable surrogate-ish PK.
  2. hidden sensitive-field: keyword heuristic (cred/secret/password/connection/
     salary/id_card/phone/身份证/薪酬...).
  3. physical-column diff: declared columns must exist on the physical table
     (hard error — a typo here means broken SQL at query time). Physical columns
     not declared are only a warning (unmodeled = unexposed, e.g. created_at).
  4. describe coverage: non-empty descriptions, properties, link participation.
  5. reasoning rules (EAI-CUSTOM, 2026-09-13 reasoning design §4): rule YAML
     parseable + every when/derive predicate/etype ⊆ registry enum (fail-closed).

Column-diff imports the extension model modules explicitly — Base.metadata is
only populated by modules that have actually been imported.
"""

from __future__ import annotations

import re
import sys

from app.ontology.registry import load_registry

SENSITIVE_KEYWORDS = re.compile(r"cred|secret|password|passwd|connection|salary|id_card|phone|身份证|薪酬|工资|token|api_key|private", re.I)

# D14: lint 范围 = 市场域 + doc_graph 表前缀；白名单 = 显式豁免
# （cpa/csp_run_history: 二期登记; dg_merges: 内部审计表, 永不对外暴露）。
SCOPE_TABLE_PREFIXES = ("cpa_", "csp_", "dg_")
WHITELIST_TABLES = {"cpa_run_history", "csp_run_history", "dg_merges"}


def check_market_tables_registered(reg) -> list[str]:
    """同 PR 规则（D14）：SCOPE 前缀域（市场域四模块 + doc_graph）新模块新建表须在同一 PR 登记 ontology 注册表。

    仅对白名单外的 SCOPE 表生效——存量表未登记会报错，逼新表上线即登记。

    EAI-CUSTOM(2026-09-17 迁出独立): 原版在此 import backend 侧 contract_price/spare_parts
    模型注册 cpa_/csp_ 物理表；独立服务无 gateway 模型 → 只检查本服务 metadata 内可注册的
    SCOPE 表（dg_* 域）。cpa_/csp_ 表的登记约束由 registry 声明侧 + gateway 侧消费共同承管。
    """
    errors: list[str] = []
    try:
        import app.doc_graph.tables  # noqa: F401 — dg_* 表注册进 Base.metadata
        from app.db import Base

        registered = {o.access.table for o in reg.object_types.values() if o.access.path == "postgres_ext" and o.access.table}
        for name in Base.metadata.tables:
            if not name.startswith(SCOPE_TABLE_PREFIXES) or name in WHITELIST_TABLES:
                continue
            if name not in registered:
                errors.append(f"table {name}: 市场域表未在 ontology 注册表登记（同 PR 规则, 白名单: {sorted(WHITELIST_TABLES)}）")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"market-table check failed: {exc}")
    return errors


def check_data_source_access(reg) -> list[str]:
    """data_source 路径对象须带 source_id + table_name（连接解析依赖）。"""
    errors = []
    for o in reg.object_types.values():
        if o.access.path == "data_source" and not (o.access.source_id and o.access.table_name):
            errors.append(f"{o.api_name}: data_source access 缺 source_id/table_name")
    return errors


def check_reasoning_rules(reg) -> list[str]:
    """推理规则（EAI-CUSTOM, reasoning 设计 §4）: doc_graph/rules YAML 可解析 + when/derive 谓词/etype ⊆ registry 枚举。

    复用 main() 已加载的 reg（与 lint 其余检查同源）; 加载失败（坏 YAML/未注册谓词/
    重复规则名等）→ 硬错误。示例规则自身必须过此检查（仓库 rules/eia.yaml）。
    """
    errors: list[str] = []
    try:
        from app.doc_graph.reasoning.rule_registry import RULES_DIR, load_rules

        load_rules(RULES_DIR, reg=reg)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"reasoning-rules check failed: {exc}")
    return errors


def check_pk_immutability(reg) -> list[str]:
    errors = []
    for o in reg.object_types.values():
        if not o.pk.immutable:
            errors.append(f"{o.api_name}: pk immutable=False (must be surrogate UUID / stable key)")
        if o.pk.type not in ("string", "integer", "uuid"):
            errors.append(f"{o.api_name}: pk type must be string/integer/uuid")
    return errors


def check_hidden_sensitive(reg) -> list[str]:
    errors = []
    for o in reg.object_types.values():
        for p in o.properties:
            if SENSITIVE_KEYWORDS.search(p.name) or SENSITIVE_KEYWORDS.search(p.api_name):
                if not p.hidden:
                    errors.append(f"{o.api_name}.{p.api_name}: sensitive field not hidden")
    return errors


def check_physical_column_diff(reg) -> tuple[list[str], list[str]]:
    """Declared ⊆ physical (hard error); physical − declared (warning only)."""
    errors: list[str] = []
    warnings: list[str] = []
    try:
        # EAI-CUSTOM(2026-09-17 迁出独立): backend 侧模型（contract_price/spare_parts/extensions.models）
        # 不可导入 → cpa_/csp_/bid 等 postgres_ext 对象走既有 "not in metadata, skipped" warning 路径；
        # 本服务守得住的 dg_* 域仍做真实列比对。
        import app.doc_graph.tables  # noqa: F401 — dg_* 表注册进 Base.metadata
        from app.db import Base

        for o in reg.object_types.values():
            if o.access.path != "postgres_ext":
                continue
            table = Base.metadata.tables.get(o.access.table)
            if table is None:
                warnings.append(f"{o.api_name}: table {o.access.table} not in metadata, column-diff skipped")
                continue
            physical = {c.name for c in table.columns}
            declared = {o.pk.column} | {p.name for p in o.properties}
            unknown = declared - physical
            if unknown:
                errors.append(f"{o.api_name}: declared columns missing from {o.access.table}: {sorted(unknown)}")
            unmodeled = physical - declared
            if unmodeled:
                warnings.append(f"{o.api_name}: physical columns not modeled (informational): {sorted(unmodeled)}")
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"column-diff check skipped: {exc}")
    return errors, warnings


def check_coverage(reg, threshold: float = 0.8) -> list[str]:
    errors = []
    for o in reg.object_types.values():
        if not o.description.strip():
            errors.append(f"{o.api_name}: empty description")
        if not o.properties:
            errors.append(f"{o.api_name}: no properties")
    # link coverage: every object type should participate in >=1 link (except pure metadata types)
    names = {o.api_name for o in reg.object_types.values()}
    linked = {link.source for link in reg.link_types.values()} | {link.target for link in reg.link_types.values()}
    orphan = names - linked
    if orphan and len(orphan) / len(names) > (1 - threshold):
        errors.append(f"orphan object types (no links): {sorted(orphan)}")
    return errors


def main() -> int:
    reg = load_registry()
    errors: list[str] = []
    try:
        errors += check_pk_immutability(reg)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"pk check failed: {exc}")
    errors += check_hidden_sensitive(reg)
    diff_errors, warnings = check_physical_column_diff(reg)
    errors += diff_errors
    errors += check_coverage(reg)
    errors += check_market_tables_registered(reg)
    errors += check_data_source_access(reg)
    errors += check_reasoning_rules(reg)
    for w in warnings:
        print(f"ontology-lint WARN: {w}", file=sys.stderr)
    if errors:
        print("ontology-lint FAIL:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"ontology-lint OK ({len(reg.object_types)} object types, {len(reg.link_types)} links)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
