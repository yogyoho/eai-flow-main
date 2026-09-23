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
  6. `scope_resource` 值域（EAI-CUSTOM, 动作层设计 §3 / Task 9）: 已声明的值必须是
     `config/permissions.yaml` 的模块 key——未知模块 → `DataScopeEngine` 返回 `none_allow`。
  7. 动作层可达者必须绑定 `scope_resource`（同 §3 / Task 9）: 结构性防线，见
     `check_action_reachable_objects_are_scoped` 的 docstring（含**有意的范围收窄**）。
  8. 动作前置条件 `value` 形状（同 §3 / Task 9）: `in`/`not_in` 须非空序列、`eq`/`ne` 须有
     非 None 值、`is_null`/`not_null` 不带值——加载期可查的静态错误，不该等 invoke 时的 400。

Column-diff imports the extension model modules explicitly — Base.metadata is
only populated by modules that have actually been imported.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import yaml

from app.ontology.registry import REGISTRY_DIR, load_registry
from app.ontology.schemas import DomainFile

SENSITIVE_KEYWORDS = re.compile(r"cred|secret|password|passwd|connection|salary|id_card|phone|身份证|薪酬|工资|token|api_key|private", re.I)

# D14: lint 范围 = 市场域 + doc_graph 表前缀；白名单 = 显式豁免
# （cpa/csp_run_history: 二期登记; dg_merges: 内部审计表, 永不对外暴露;
#  dg_action_audit: 动作审计表, 同 dg_merges 一类——只写不给读投影, 无 ObjectType 可登记）。
SCOPE_TABLE_PREFIXES = ("cpa_", "csp_", "dg_")
WHITELIST_TABLES = {"cpa_run_history", "csp_run_history", "dg_merges", "dg_action_audit"}


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


# ───────────────── 动作层检查（EAI-CUSTOM, 设计 §3 / Task 9）─────────────────

_SEQUENCE_OPS = ("in", "not_in")
_NULL_OPS = ("is_null", "not_null")
_PERMISSIONS_YAML_ENV = "ONTOSTUDIO_PERMISSIONS_YAML"


def check_scope_resources(domain_file: DomainFile, known_modules: set[str]) -> list[str]:
    """每个 scope_resource 必须是已知模块 key。

    EAI-CUSTOM: 设计 §3。模块 key 取自 config/permissions.yaml 的顶层 modules。
    未知模块会让 DataScopeEngine 返回 none_allow → 动作恒 404。

    **缺绑定在这里恒绿**（`test_object_without_scope_resource_is_fine` 是这条口径的显式祝福）：
    本函数只管"已声明的值合不合法"。缺绑定由
    :func:`check_action_reachable_objects_are_scoped` 按动作层可达面另行断言。
    """
    problems: list[str] = []
    for ot in domain_file.object_types:
        if ot.scope_resource and ot.scope_resource not in known_modules:
            problems.append(f"{ot.api_name}: scope_resource {ot.scope_resource!r} 不是已知权限模块（可选：{sorted(known_modules)}）")
    return problems


def check_action_reachable_objects_are_scoped(reg) -> list[str]:
    """动作层可达的对象类型必须声明 scope_resource（结构性防线）。

    EAI-CUSTOM: 设计 §3。"被推迟的项没人认领"在本计划复发了四次，其中第四次（`graph_relation`
    漏绑）正是本检查的形状：凡动作层能到达的对象类型都必须声明 scope_resource——缺绑定会让
    唯一的消费者（`app/ontology/routers.py` 的 ``_resolve_scope_rule``）静默回退 ``allow_all``，
    范围门 fail-open。

    断言口径 = **从每个 ``actions[].target`` 出发、沿 ``enabled`` 的 link_types 双向遍历得到的闭包**。
    ``enabled: false`` 是 D3 stub（遍历拒绝），故不把可达面撑到它上面。

    **范围有意收窄——勿读成"registry 里所有链接端点"**：实测（2026-09-24）全量链接端点口径在
    真实 registry 上有 11 处未绑定（contract_price / spare_parts / bid_quote 域的只读对象，
    无任何动作声明），其中 ``data_source`` / ``dataset`` 在 permissions.yaml 里**没有对应模块
    key**——该口径今日不可满足，且属市场域的独立治理决策（设计 §3 只点名 `graph_entity` /
    `graph_relation`）。可达口径在真实 registry 上全绿，同时完整覆盖本计划的动作层（doc_graph 域）。
    """
    adjacency: dict[str, set[str]] = {}
    for lt in reg.link_types.values():
        if not lt.enabled:
            continue
        adjacency.setdefault(lt.source, set()).add(lt.target)
        adjacency.setdefault(lt.target, set()).add(lt.source)

    targets = {a.target for a in reg.actions.values()}
    reachable = {t for t in targets if t in reg.object_types}
    frontier = list(reachable)
    while frontier:
        for neighbour in adjacency.get(frontier.pop(), ()):
            if neighbour in reg.object_types and neighbour not in reachable:
                reachable.add(neighbour)
                frontier.append(neighbour)

    errors: list[str] = []
    for name in sorted(reachable):
        if reg.object_types[name].scope_resource:
            continue
        role = "动作 target" if name in targets else "动作层可达的链接端点"
        errors.append(f"{name}: 被动作层引用（{role}）但未声明 scope_resource —— 缺绑定使范围判定回退 allow_all（设计 §3）")
    return errors


def check_action_preconditions(reg) -> list[str]:
    """动作前置条件的 ``value`` 形状（加载期静态校验）。

    EAI-CUSTOM: 设计 §1.1 / Task 9。``sql_write`` 的守卫会在 invoke 时把这些笔误拒成 400，
    但它们全是**加载期就能查出来的静态错误**，故提前到 lint：

    - ``in`` / ``not_in``：value 必须是非空 list/tuple/set（空集恒真/恒假；漏引号会让 YAML 给字符串）
    - ``eq`` / ``ne``：必须有 value 且非 None（判空请用 ``is_null``）
    - ``is_null`` / ``not_null``：不应带 value

    够不到的一条（记录在案，不在此处解决）：``in``/``not_in`` 的**目标列是否为数组型**需要
    schema 层拿到 PG 列类型，registry 只交叉校验字段存在——属另一议题。
    """
    errors: list[str] = []
    for a in reg.actions.values():
        for cond in a.preconditions:
            where = f"{a.id}: 前置条件 {cond.field} op={cond.op}"
            if cond.op in _SEQUENCE_OPS:
                if not isinstance(cond.value, (list, tuple, set)):
                    errors.append(f"{where} 的 value 必须是非空 list/tuple/set，得到 {type(cond.value).__name__}={cond.value!r}（YAML 漏引号会落到这里）")
                elif not cond.value:
                    errors.append(f"{where} 的 value 是空 {type(cond.value).__name__} —— 空集谓词无意义（sql_write 守卫会在 invoke 时拒成 400）")
            elif cond.op in ("eq", "ne") and cond.value is None:
                errors.append(f"{where} 缺 value（或显式为 null）—— eq/ne 必须有值，判空请用 is_null/not_null")
            elif cond.op in _NULL_OPS and cond.value is not None:
                errors.append(f"{where} 不应带 value（得到 {cond.value!r}）—— is_null/not_null 只有一个谓词")
    return errors


def _resolve_permissions_yaml() -> Path | None:
    """定位 gateway 侧 permissions.yaml（模块 key 真相源）。

    顺序：env ``ONTOSTUDIO_PERMISSIONS_YAML`` 覆盖 → 从本文件向上逐级找 ``config/permissions.yaml``
    → 回落 ``deploy/offline/config/permissions.yaml``（离线部署无仓根时）。找不到的处置见
    :func:`_permissions_modules`。
    """
    override = os.environ.get(_PERMISSIONS_YAML_ENV)
    if override:
        path = Path(override)
        return path if path.exists() else None
    for parent in Path(__file__).resolve().parents:
        for rel in ("config/permissions.yaml", "deploy/offline/config/permissions.yaml"):
            candidate = parent / rel
            if candidate.exists():
                return candidate
    return None


def _permissions_modules() -> tuple[set[str], list[str], list[str]]:
    """(模块 key 集合, errors, warnings)。

    **定位不到 permissions.yaml → warning 而非 error**：那是"环境里没有这份真相源"，
    不是注册表缺陷（本仓既有先例：column-diff 在拿不到 metadata 时同样降级为 warning）。
    文件**在**但内容坏（YAML 坏 / 没有 ``modules``）→ error：那是真相源本身有问题，fail-closed。
    两条路径都不会静默——warning 由 main() 打到 stderr。
    """
    path = _resolve_permissions_yaml()
    if path is None:
        return set(), [], [f"未找到 permissions.yaml（env {_PERMISSIONS_YAML_ENV} 或仓根 config/）—— scope_resource 值域校验已跳过"]
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        return set(), [f"{path}: 解析失败: {exc}"], []
    modules = data.get("modules")
    if not isinstance(modules, dict) or not modules:
        return set(), [f"{path}: modules 段缺失或非 mapping"], []
    return set(modules), [], []


def _iter_domain_files():
    """按清单逐文件产出 (文件名, DomainFile)。

    Registry 只保留 object_types/link_types/actions 三张扁平表、不留 per-domain DomainFile
    （见 `app/ontology/registry.py` 的 Registry 注释），故这里按同一份清单重解析一次。
    文件已由 load_registry 全量校验过，此处不再重复错误处理。
    """
    manifest = yaml.safe_load((REGISTRY_DIR / "_manifest.yaml").read_text(encoding="utf-8")) or {}
    for entry in manifest.get("files", []):
        name = entry["file"]
        data = yaml.safe_load((REGISTRY_DIR / name).read_text(encoding="utf-8")) or {}
        yield name, DomainFile.model_validate(data)


def check_scope_resources_on_disk() -> tuple[list[str], list[str]]:
    """把 :func:`check_scope_resources` 接到真实清单 + 真实 permissions.yaml 上。

    返回 (errors, warnings)——warnings 只在"环境里没有 permissions.yaml"时非空。
    """
    known_modules, errors, warnings = _permissions_modules()
    if errors or warnings:
        return errors, warnings
    for name, domain_file in _iter_domain_files():
        errors += [f"{name}: {p}" for p in check_scope_resources(domain_file, known_modules=known_modules)]
    return errors, warnings


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
    # 动作层（EAI-CUSTOM, 设计 §3 / Task 9）：可达者必须绑 scope_resource + 前置条件 value 形状
    # + 已声明 scope_resource 的值域（值域那条要读 gateway 的 permissions.yaml，故单独走盘上路径）。
    errors += check_action_reachable_objects_are_scoped(reg)
    errors += check_action_preconditions(reg)
    scope_errors, scope_warnings = check_scope_resources_on_disk()
    errors += scope_errors
    warnings += scope_warnings
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
