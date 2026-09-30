"""EIA 校验规则集——注册表加载 + 执行器 + REST（ontostudio 子项目 3）.

设计: docs/superpowers/specs/2026-09-30-eia-rules-mcp-design.md §3/§5

- 规则 = 仓库 YAML（rules_registry/coal_eia_rules.yaml），SPARQL 自包含直跑
  sigma kernel 图（pyoxigraph named graph，见 rules_registry 文件头图约定）。
- 违规 = SELECT 结果行（变量绑定 + message_template 渲染）；空图 → 全部 0 违规。
- 不建规则引擎框架、不做自动修复/写回（spec §2 非目标）。
- data_requirements 标注每条规则的数据依赖：数据未抽取的规则空转（0 违规，无害）。

鉴权与其余 ontology 路由一致（system:access）。
EAI-CUSTOM(2026-09-30, 子项目 3): 新文件，不触碰 harness/上游核心。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import CurrentUser, require_permission
from app.ontology.kernel.store import OxStore

RULES_YAML_PATH = Path(__file__).parent / "rules_registry" / "coal_eia_rules.yaml"

_SEVERITIES = ("error", "warn", "info")
_REQUIRED_FIELDS = ("id", "name", "severity", "description", "data_requirements", "sparql", "message_template")

DEFAULT_VIOLATION_LIMIT = 200


@dataclass(frozen=True)
class RuleDefinition:
    """单条校验规则（与 yaml 字段一一对应）。"""

    id: str
    name: str
    severity: str  # error | warn | info
    description: str
    data_requirements: str
    sparql: str  # 自包含 SELECT（含 PREFIX 声明）
    message_template: str  # {变量名} 占位，引用 SELECT 绑定变量


def load_rules(path: Path = RULES_YAML_PATH) -> list[RuleDefinition]:
    """规则表加载。fail-closed：缺字段 / severity 非法 / id 重复 即 ValueError。"""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(data, list):
        raise ValueError("规则表顶层须为列表")
    rules: list[RuleDefinition] = []
    seen: set[str] = set()
    for item in data:
        item = item or {}
        missing = [k for k in _REQUIRED_FIELDS if not item.get(k)]
        if missing:
            raise ValueError(f"规则缺字段 {missing}: {item!r}")
        if item["severity"] not in _SEVERITIES:
            raise ValueError(f"规则 {item['id']} severity 非法: {item['severity']!r}（须为 {_SEVERITIES}）")
        if item["id"] in seen:
            raise ValueError(f"规则 id 重复: {item['id']}")
        seen.add(item["id"])
        rules.append(RuleDefinition(**{k: item[k] for k in _REQUIRED_FIELDS}))
    return rules


class _SafeDict(dict):
    """message_template 渲染：缺变量保留占位符原样（不因模板/行不齐而抛错）。"""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render_message(template: str, row: dict[str, str | None]) -> str:
    return template.format_map(_SafeDict({k: v for k, v in row.items() if v is not None}))


def execute_rule(store: OxStore, rule: RuleDefinition, limit: int = DEFAULT_VIOLATION_LIMIT) -> dict:
    """单规则执行：违规=SELECT 结果行。violations 截断到 limit（violation_count 恒为真实总数）。"""
    t0 = time.perf_counter()
    rows = store.query(rule.sparql)
    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    violations = [dict(row) | {"message": render_message(rule.message_template, row)} for row in rows[:limit]]
    return {
        "rule_id": rule.id,
        "name": rule.name,
        "severity": rule.severity,
        "violation_count": len(rows),
        "violations": violations,
        "truncated": len(rows) > len(violations),
        "duration_ms": duration_ms,
    }


def execute_rules(store: OxStore, ids: list[str] | None = None, rules: list[RuleDefinition] | None = None, limit: int = DEFAULT_VIOLATION_LIMIT) -> dict:
    """规则集执行：ids 缺省全跑；未知 id 抛 KeyError（调用方转 4xx，fail-closed）。"""
    rules = rules if rules is not None else load_rules()
    if ids is not None:
        known = {r.id for r in rules}
        unknown = sorted(set(ids) - known)
        if unknown:
            raise KeyError(f"未知规则 id: {unknown}")
        wanted = set(ids)
        rules = [r for r in rules if r.id in wanted]
    results = [execute_rule(store, r, limit=limit) for r in rules]
    return {
        "executed_at": datetime.now(UTC).isoformat(),
        "rule_count": len(results),
        "total_violations": sum(r["violation_count"] for r in results),
        "results": results,
    }


# ---- REST（spec §5）----


router = APIRouter(prefix="/api/extensions/ontology/rules", tags=["ontology-rules"])


class RuleExecuteRequest(BaseModel):
    ids: list[str] | None = Field(None, description="缺省全跑 12 条；给了则只跑指定 id")
    limit: int = Field(DEFAULT_VIOLATION_LIMIT, ge=1, le=10000, description="每规则违规返回上限（计数不受影响）")
    refresh: bool = Field(False, description="执行前先跑 kernel 推理（rule_emission_monitoring 依赖派生图时需要）")


@router.get("")
async def list_rules(_: CurrentUser = Depends(require_permission("system:access"))):
    """规则清单（id/name/severity/data_requirements——SPARQL 本体不透出，看仓库 yaml）。"""
    rules = load_rules()
    return {
        "success": True,
        "count": len(rules),
        "rules": [{"id": r.id, "name": r.name, "severity": r.severity, "description": r.description, "data_requirements": r.data_requirements} for r in rules],
    }


@router.post("/execute")
async def execute_rules_endpoint(payload: RuleExecuteRequest, _: CurrentUser = Depends(require_permission("system:access"))):
    """对 sigma kernel 图逐条跑规则（1908 边量级毫秒级）；refresh=true 先跑推理（重算派生图）。"""
    from app.ontology.kernel.service import get_kernel

    rules = load_rules()
    if payload.refresh:
        get_kernel().refresh()
    try:
        out = execute_rules(get_kernel().store, ids=payload.ids, rules=rules, limit=payload.limit)
    except KeyError as e:
        raise HTTPException(status_code=422, detail=f"未知规则 id: {e}") from e
    return {"success": True, **out}
