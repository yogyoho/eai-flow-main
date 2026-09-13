"""Rete facade 前向链语义测试.

EAI-CUSTOM: plan docs/superpowers/plans/2026-09-13-ontology-reasoning-rules.md Task 1 Step 1.5。
facade 语义契约的失败测试先行（TDD）; 实现在 doc_graph/reasoning/facade.py。
"""

from app.extensions.ontology.doc_graph.reasoning.facade import MAX_DERIVED, MAX_ITERATIONS, RuleFacade


def _f(f: RuleFacade) -> None:
    f.add_fact("org_a", "org_develops_project", "proj_x")
    f.add_fact("mine_m", "mine", "mine_m")  # 类型事实


def test_single_pattern_derive():
    f = RuleFacade()
    _f(f)
    f.add_rule("r1", ["org_develops_project(?ORG, ?PROJ)"], "org_involved_in(?ORG, ?PROJ)")
    out = f.run()
    assert {"subject": "org_a", "predicate": "org_involved_in", "object": "proj_x", "rule": "r1"} in out["derived"]


def test_two_pattern_join():
    f = RuleFacade()
    _f(f)
    f.add_fact("org_a", "org_involved_in", "mine_m")
    f.add_rule("r2", ["org_involved_in(?ORG, ?M)", "mine(?M)"], "org_touches_mine(?ORG, ?M)")
    out = f.run()
    assert any(d["predicate"] == "org_touches_mine" and d["subject"] == "org_a" for d in out["derived"])


def test_no_match_no_derived():
    f = RuleFacade()
    _f(f)
    f.add_rule("r", ["nonexistent_pred(?X)"], "foo(?X)")
    assert f.run()["derived"] == []


def test_fixpoint_no_infinite_loop():
    f = RuleFacade()
    _f(f)
    f.add_rule("self_feed", ["a_fact(?X)"], "a_fact(?X)")  # 自馈不动点
    f.add_fact("x1", "a_fact", "x1")
    out = f.run()
    assert out["stats"]["iterations"] <= MAX_ITERATIONS
    # 自馈不得产生重复派生
    assert [d for d in out["derived"] if d["predicate"] == "a_fact"] == []


def test_chained_rules_feed_forward():
    """派生事实回灌事实空间参与后续规则（前向链）。"""
    f = RuleFacade()
    f.add_fact("org_a", "org_develops_project", "proj_x")
    f.add_fact("proj_x", "located_in", "mine_m")
    f.add_fact("mine_m", "mine", "mine_m")
    f.add_rule("r1", ["org_develops_project(?O, ?P)"], "org_involved_in(?O, ?P)")
    f.add_rule("r2", ["org_involved_in(?O, ?P)", "located_in(?P, ?M)", "mine(?M)"], "org_touches_mine(?O, ?M)")
    out = f.run()
    assert any(d["predicate"] == "org_touches_mine" and d["subject"] == "org_a" and d["object"] == "mine_m" for d in out["derived"])
    assert out["stats"]["facts_total"] >= 5  # 3 断言 + 2 派生


def test_max_rule_fires_cap_stops_run():
    """上限真实生效: 触发数达 MAX_RULE_FIRES 即停, stats 标注, 不抛异常。"""
    from app.extensions.ontology.doc_graph.reasoning.facade import MAX_RULE_FIRES

    f = RuleFacade()
    for i in range(1100):
        f.add_fact(f"e{i}", "p", f"v{i}")
    f.add_rule("bulk", ["p(?X, ?Y)"], "q(?X, ?Y)")
    out = f.run()
    assert out["stats"]["max_rule_fires_reached"] is True
    assert len(out["derived"]) <= MAX_DERIVED
    assert len(out["derived"]) == MAX_RULE_FIRES  # 前 500 个唯一触发全部派生新事实后停止
    assert out["stats"]["iterations"] <= MAX_ITERATIONS


def test_disabled_via_yaml_not_here():
    """facade 不管 enabled——注册表层过滤（Task 2）。"""
    import inspect

    from app.extensions.ontology.doc_graph.reasoning import facade

    assert "enabled" not in inspect.getsource(facade.RuleFacade.add_rule)
