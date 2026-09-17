"""现算现返编排——真库事实 + 注册规则 → 前向链派生事实+触发轨迹.

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-13-ontology-reasoning-rules-design.md §3。
fresh-per-evaluate（评审定案）: RuleFacade 每次 evaluate 新建——无 stale 规则、无并发锁
问题, run() 的 Rete 网络本就每次重建; 全程只读, 零落库。
可观测性（评审 recommendation 2）: RuleStore 热重载失败保旧快照时 last_error 非空 →
返回 stale_rules=true + stale_rules_error 摘要, 保留"旧快照偏差"的可观测闭环。
异常契约: 冷加载失败（RulesError）与规则注册失败（RuleSyntaxError ⊆ ValueError）上抛,
由 MCP 层窄捕获转结构化错误; facts 为空是合法空态（直接零派生, 不建 facade）。
"""

from __future__ import annotations

from pathlib import Path

from app.doc_graph.reasoning import rule_registry
from app.doc_graph.reasoning.facade import RuleFacade
from app.doc_graph.reasoning.facts import load_facts

# 空态 stats 与 facade.run() 同键（消费者无需区分两种返回形态）
_EMPTY_STATS = {
    "iterations": 0,
    "facts_total": 0,
    "rule_fires": 0,
    "max_iterations_reached": False,
    "max_derived_reached": False,
    "max_rule_fires_reached": False,
}


async def evaluate_rules(domain: str, rules_dir: str | None = None) -> dict:
    """真库事实 + enabled 且 domain 匹配的规则 → 前向链推理（现算现返，零落库）。

    返回 {"derived_facts", "activations", "stats", "rules_loaded", "stale_rules",
          "stale_rules_error", "truncated"}; truncated=true 表示到达推理工作预算
    （max_*_reached 任一置位, 不必然截断, 语义见 facade.run() docstring）。
    域内零注册规则时额外带 hint（命名已知域, 防止 agent 把空结果误读为"无数据"）。
    rules_dir 覆盖默认规则目录（冷 RuleStore 实例, 不入进程单例缓存; 仅 Python API/
    测试可用——MCP 面不透传, 见 mcp._evaluate_rules 评审加固注）。
    """
    store = rule_registry.get_rules_store() if rules_dir is None else rule_registry.RuleStore(Path(rules_dir))
    snapshot = store.get()
    # enabled 过滤在注册表层（snapshot.enabled_rules）, 域过滤在编排层——facade 不感知 domain
    rules = [r for r in snapshot.enabled_rules if r.domain == domain]
    stale_error = store.last_error

    if not rules:
        # 零规则短路: 不查库（零派生已定）, hint 命名已知域（同包私有表, 单一真源在 rule_registry）
        known = ", ".join(sorted(rule_registry._DOMAIN_EXTRACTIONS))
        return {
            "derived_facts": [],
            "activations": [],
            "stats": dict(_EMPTY_STATS),
            "rules_loaded": 0,
            "stale_rules": stale_error is not None,
            "stale_rules_error": stale_error,
            "truncated": False,
            "hint": f"已知域: {known}——'{domain}' 域当前无注册规则",
        }

    facts = await load_facts(domain)
    if not facts:
        return {
            "derived_facts": [],
            "activations": [],
            "stats": dict(_EMPTY_STATS),
            "rules_loaded": len(rules),
            "stale_rules": stale_error is not None,
            "stale_rules_error": stale_error,
            "truncated": False,
        }

    facade = RuleFacade()
    for f in facts:
        facade.add_fact(*f)
    for r in rules:
        facade.add_rule(r.name, list(r.when), r.derive)
    out = facade.run()

    stats = out["stats"]
    return {
        "derived_facts": out["derived"],
        "activations": out["activations"],
        "stats": stats,
        "rules_loaded": len(rules),
        "stale_rules": stale_error is not None,
        "stale_rules_error": stale_error,
        "truncated": bool(stats["max_iterations_reached"] or stats["max_derived_reached"] or stats["max_rule_fires_reached"]),
    }
