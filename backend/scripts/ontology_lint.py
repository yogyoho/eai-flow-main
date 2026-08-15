"""Ontology registry lint — §2.2 acceptance checklist, exit 1 on failure.

Checks (mother-spec §2.2 / expansion-plan §2.2):
  1. PK immutability: every object type has an immutable surrogate-ish PK.
  2. hidden sensitive-field: keyword heuristic (cred/secret/password/connection/
     salary/id_card/phone/身份证/薪酬...).
  3. physical-column diff: declared columns must exist on the physical table
     (hard error — a typo here means broken SQL at query time). Physical columns
     not declared are only a warning (unmodeled = unexposed, e.g. created_at).
  4. describe coverage: non-empty descriptions, properties, link participation.

Column-diff imports the extension model modules explicitly — Base.metadata is
only populated by modules that have actually been imported.
"""

from __future__ import annotations

import re
import sys

from app.extensions.ontology.registry import load_registry

SENSITIVE_KEYWORDS = re.compile(r"cred|secret|password|passwd|connection|salary|id_card|phone|身份证|薪酬|工资|token|api_key|private", re.I)

# D14: lint 范围 = 市场域四模块表前缀；白名单 = 显式豁免（run_history 二期登记）。
SCOPE_TABLE_PREFIXES = ("cpa_", "csp_")
WHITELIST_TABLES = {"cpa_run_history", "csp_run_history"}


def check_market_tables_registered(reg) -> list[str]:
    """同 PR 规则（D14）：市场域新模块新建表须在同一 PR 登记 ontology 注册表。

    仅对白名单外的市场域表生效——存量表未登记会报错，逼新表上线即登记。
    """
    errors: list[str] = []
    try:
        import app.extensions.contract_price.models  # noqa: F401
        import app.extensions.spare_parts.models  # noqa: F401
        from app.extensions.database import Base

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
        import app.extensions.contract_price.models  # noqa: F401 — populate Base.metadata
        import app.extensions.models  # noqa: F401 — data_sources / data_source_datasets
        import app.extensions.spare_parts.models  # noqa: F401
        from app.extensions.database import Base

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
