"""SPARQL CONSTRUCT 派生规则（kernel P3）——Rete 在 OntoStudio 的替代.

- 每条规则结果写独立 named graph：graph:derived:<name>（named graph 归属即触发轨迹，
  刷新 = 清空重算；千级规模无预算问题，bug-2188 语境消失）。
- 规则可见域 = graph:asserted ∪ graph:alignment（sameAs 候选参与派生，spec §3）；
  不读 entailment（保持 OWL 层与业务派生层单向、无环）。
- 规则来源：YAML（load_rules）或内置 BUILTIN_RULES；查询须自带 PREFIX 声明（自包含）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pyoxigraph import NamedNode, Quad

from app.ontology.kernel.store import OxStore

RULES_DIR = Path(__file__).parent
DEFAULT_RULES_PATH = RULES_DIR / "rules.yaml"


@dataclass
class DeriveRule:
    name: str
    construct: str  # 自包含 CONSTRUCT 查询（含 PREFIX 声明）


# 内置规则：sameAs 候选传播（等价/对齐推理的派生面——结论只进 derived 图，
# 永不改写断言图；业务合并永远人工确认，spec §3 sameAs 纪律）
BUILTIN_SAMEAS_PROPAGATION = DeriveRule(
    name="sameas_propagation",
    construct="""PREFIX owl: <http://www.w3.org/2002/07/owl#>
CONSTRUCT { ?alias ?p ?o }
WHERE {
  GRAPH <graph:alignment> {
    { ?alias owl:sameAs ?canonical } UNION { ?canonical owl:sameAs ?alias }
  }
  GRAPH <graph:asserted> { ?canonical ?p ?o }
}""",
)


def load_rules(path: Path = DEFAULT_RULES_PATH) -> list[DeriveRule]:
    """YAML 规则表 → DeriveRule 列表（fail-closed：缺字段抛 ValueError）。"""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules: list[DeriveRule] = []
    for item in data.get("rules", []):
        name = (item or {}).get("name")
        construct = (item or {}).get("construct")
        if not name or not construct:
            raise ValueError(f"规则缺 name/construct: {item!r}")
        rules.append(DeriveRule(name=name, construct=construct))
    return rules


def run_rule(store: OxStore, rule: DeriveRule) -> int:
    """单规则重算：清 graph:derived:<name> → CONSTRUCT 结果落图。返回派生三元组数。"""
    target = f"graph:derived:{rule.name}"
    store.clear_graph(target)
    count = 0
    for triple in store._store.query(rule.construct):
        store._store.add(Quad(triple.subject, triple.predicate, triple.object, NamedNode(target)))
        count += 1
    return count


def run_all_rules(store: OxStore, rules: list[DeriveRule]) -> dict[str, int]:
    """按序全量重算。失败 fail-closed：单规则异常 → 该图保持空并抛出（调用方决定降级）。"""
    return {rule.name: run_rule(store, rule) for rule in rules}
