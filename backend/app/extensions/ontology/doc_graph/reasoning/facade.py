"""规则推理 facade——三元组事实 + Datalog 式规则 → 前向链派生事实+触发轨迹.

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-13-ontology-reasoning-rules-design.md §3。
现算现返: 零落库; 上限硬编码（迭代≤10 / 派生≤1000 / 触发≤500）, 达限即停并在 stats 打旗（不抛异常）。

实现路线: 适配 vendored ReteEngine（./rete_engine.py, Semantica MIT @7057387）——
匹配/alpha-beta join 全部走上游网络; 本模块只做三件事:
1. 事实空间适配: 事实是三元组 (subject, predicate, object), Rete 匹配是字符串化的
   ``pred(arg, ...)``。模式按参数个数对三元组投影——单参模式 ``p(?X)`` 绑定 subject
   （类型事实 predicate=etype, 如 ``mine(?M)``）, 双参模式 ``p(?X, ?Y)`` 绑定
   (subject, object)。谓词可能同时被两种 arity 引用, 投影视图按需各生成一份。
2. 派生回灌: 结论模板 token 级 ``?var`` 替换（借上游 reasoner._substitute_variables
   语义）→ 解析回三元组 → 未见过则回灌事实空间参与下一轮; 重复派生不重复计入,
   同一激活（规则+绑定+前提, 按上游 _make_activation_key 身份）跨轮不重复触发。
3. 不动点循环: 每轮 reset 网络记忆后重灌全部事实视图 → 收集激活 → 派生新事实;
   一轮无新事实即不动点。上限任一触发即停, stats 打旗。

已知上游限制（字符串化匹配）: 实体值含 ``", "`` 或 ``")"`` 会破坏模式匹配——
域内实体名/IRI 不含这些字符; Task 2 规则 lint 会收敛谓词枚举。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.extensions.ontology.doc_graph.reasoning.rete_engine import (
    Fact,
    ReteEngine,
    Rule,
    _make_activation_key,
)

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 10
MAX_DERIVED = 1000
MAX_RULE_FIRES = 500

_VAR_TOKEN = re.compile(r"\?(\w+)")
_FACT_SHAPE = re.compile(r"^\s*([^()\s]+)\s*\((.*)\)\s*$")

Triple = tuple[str, str, str]


def _substitute_variables(template: str, bindings: dict[str, str]) -> str:
    """Token 级 ``?var`` 替换; 未绑定占位符原样保留（上游 reasoner 同语义）."""
    if not bindings:
        return template

    def _replace(m: re.Match[str]) -> str:
        return bindings.get(m.group(1), m.group(0))

    return _VAR_TOKEN.sub(_replace, template)


def _parse_shape(text: str) -> tuple[str, list[str]] | None:
    """``pred(a, b)`` → ("pred", ["a", "b"]); 非规范形 → None."""
    m = _FACT_SHAPE.match(text)
    if not m:
        return None
    inner = m.group(2).strip()
    args = [a.strip() for a in inner.split(",")] if inner else []
    return m.group(1), args


@dataclass
class _RuleEntry:
    name: str
    when: list[str]
    derive: str


@dataclass
class _Pattern:
    """编译后的 when 模式: 谓词 + 变量名列表（arity = len(vars) ∈ {1, 2}）."""

    predicate: str
    variables: list[str] = field(default_factory=list)


def _compile_pattern(pattern: str) -> _Pattern:
    """模式语法 ``"<predicate>(?var, ?var)"``; arity 限 1/2; 变元必须 ``?`` 开头.

    注册期 fail-closed: 语法坏的模式在这里拒绝, 而不是静默永不匹配。
    """
    parsed = _parse_shape(pattern)
    if parsed is None:
        raise ValueError(f'malformed rule pattern {pattern!r}: expected "pred(?A, ?B)"')
    predicate, args = parsed
    if len(args) not in (1, 2):
        raise ValueError(f"rule pattern {pattern!r}: arity must be 1 or 2, got {len(args)}")
    bad = [a for a in args if not a.startswith("?")]
    if bad:
        raise ValueError(f"rule pattern {pattern!r}: variables must start with '?', got {bad}")
    return _Pattern(predicate=predicate, variables=[a[1:] for a in args])


class RuleFacade:
    """三元组事实 + 规则 → 前向链派生。注册（add_fact/add_rule）与求值（run）分离."""

    def __init__(self) -> None:
        # triple -> 来源规则名（asserted 为 None）; 首次断言者胜（不去重报错）
        self._facts: dict[Triple, str | None] = {}
        self._rules: list[_RuleEntry] = []
        self._patterns: list[list[_Pattern]] = []

    def add_fact(
        self,
        subject: str,
        predicate: str,
        obj: str,
        *,
        inferred: bool = False,
        rule: str | None = None,
    ) -> None:
        """断言三元组事实。inferred/rule 仅作来源标注, 不影响匹配."""
        key = (str(subject), str(predicate), str(obj))
        self._facts.setdefault(key, rule if inferred else None)

    def add_rule(self, name: str, when_patterns: list[str], derive: str) -> None:
        """注册规则: when 模式全满足 → derive 结论模板派生新事实.

        结论模板 arity 限 1/2（三元组空间）; 变元须 ``?`` 开头。开关过滤在
        注册表层（Task 2）, 此处不做。
        """
        compiled = [_compile_pattern(p) for p in when_patterns]
        derived_shape = _parse_shape(derive)
        if derived_shape is None:
            raise ValueError(f'malformed rule conclusion {derive!r}: expected "pred(?A, ?B)"')
        d_pred, d_args = derived_shape
        if len(d_args) not in (1, 2):
            raise ValueError(f"rule conclusion {derive!r}: arity must be 1 or 2, got {len(d_args)}")
        bad = [a for a in d_args if not (a.startswith("?") or _VAR_TOKEN.fullmatch(a))]
        if bad:
            raise ValueError(f"rule conclusion {derive!r}: arguments must be '?vars', got {bad}")
        self._rules.append(_RuleEntry(name=str(name), when=list(when_patterns), derive=derive))
        self._patterns.append(compiled)

    # -- internals ----------------------------------------------------------

    def _materialize(self, working: dict[Triple, str | None], arity_by_pred: dict[str, set[int]]) -> list[Fact]:
        """三元组 → Rete 字符串化匹配用的 Fact 投影视图（每注册 arity 一份）."""
        views: list[Fact] = []
        for s, p, o in working:
            for arity in sorted(arity_by_pred.get(p, ())):
                args = [s] if arity == 1 else [s, o]
                views.append(Fact(fact_id=f"{p}({', '.join(args)})", predicate=p, arguments=args))
        return views

    def _derive_triples(self, rule_name: str, conclusion: str, bindings: dict[str, str]) -> list[Triple]:
        concrete = _substitute_variables(conclusion, bindings)
        parsed = _parse_shape(concrete)
        if parsed is None:
            logger.warning("rule %r produced unparseable conclusion %r", rule_name, concrete)
            return []
        predicate, args = parsed
        if len(args) == 1:
            return [(args[0], predicate, args[0])]
        if len(args) == 2:
            return [(args[0], predicate, args[1])]
        return []  # 注册期已限 1/2; 防御分支

    def run(self) -> dict:
        """前向链至不动点（或上限）。返回派生事实 + 触发轨迹 + 统计.

        run() 不改写 facade 的注册状态（事实/规则保持原样）, 可重复调用。
        stats: iterations / facts_total / rule_fires + 三个达限旗标。
        """
        arity_by_pred: dict[str, set[int]] = {}
        for patterns in self._patterns:
            for pat in patterns:
                arity_by_pred.setdefault(pat.predicate, set()).add(len(pat.variables))

        engine = ReteEngine()
        engine.build_network([Rule(rule_id=e.name, name=e.name, conditions=list(e.when), conclusion=e.derive) for e in self._rules])

        working: dict[Triple, str | None] = dict(self._facts)
        derived: list[dict] = []
        activations: list[dict] = []
        seen_activations: set[tuple] = set()
        stats: dict = {
            "iterations": 0,
            "facts_total": len(working),
            "rule_fires": 0,
            "max_iterations_reached": False,
            "max_derived_reached": False,
            "max_rule_fires_reached": False,
        }

        for iteration in range(1, MAX_ITERATIONS + 1):
            stats["iterations"] = iteration
            engine.reset()
            views = self._materialize(working, arity_by_pred)
            for fact_view in views:
                engine.add_fact(fact_view)
            matches = engine.match_patterns()

            any_new = False
            stop = False
            for match in matches:
                akey = _make_activation_key(
                    match.rule.rule_id,
                    match.bindings,
                    [(f.fact_id, f.predicate, tuple(f.arguments)) for f in match.facts],
                )
                if akey in seen_activations:
                    continue
                seen_activations.add(akey)
                stats["rule_fires"] += 1
                if stats["rule_fires"] >= MAX_RULE_FIRES:
                    stats["max_rule_fires_reached"] = True
                    stop = True

                fresh = [triple for triple in self._derive_triples(match.rule.rule_id, str(match.rule.conclusion), match.bindings) if triple not in working]
                if fresh:
                    activations.append({"rule": match.rule.rule_id, "facts": [str(f) for f in match.facts]})
                    for triple in fresh:
                        if len(derived) >= MAX_DERIVED:
                            stats["max_derived_reached"] = True
                            stop = True
                            break
                        s, p, o = triple
                        derived.append({"subject": s, "predicate": p, "object": o, "rule": match.rule.rule_id})
                        working[triple] = match.rule.rule_id
                        any_new = True
                        stats["facts_total"] = len(working)
                if stop:
                    break
            if stop or not any_new:
                break
        else:
            # MAX_ITERATIONS 轮耗尽仍每轮有新派生
            stats["max_iterations_reached"] = True

        return {"derived": derived, "activations": activations, "stats": stats}
