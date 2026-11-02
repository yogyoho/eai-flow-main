"""L2 P2 跨层实体去重(spec 2026-11-02 §7 挂账行):entity_keys 落库链 +
list_task_issues 投影归并(_cross_layer_group 纯函数直验,先例=checklist 现算不落库)。

归并规则(D7):同实体键 + 跨 ≥2 层 + 双方 violation(非 need_human)才归并;
keep = severity 升序 → 层序 L1>L2>L3 → created_at 稳定;need_human 永不隐藏。
条目不删:grouped 行标 grouped_into=keep.id(items 全量返回),keep 行带 related_issues。
"""

from types import SimpleNamespace

from app.extensions.bid_review.routers import _cross_layer_group


def _iss(id, rule_id, layer, severity, *, verdict="violation", need_human=False, keys=None, created_at="2026-11-02T00:00:00Z", message="m"):
    return SimpleNamespace(
        id=id, rule_id=rule_id, layer=layer, severity=severity, verdict=verdict,
        need_human=need_human, entity_keys=keys or [], created_at=created_at, message=message,
    )


def test_cross_layer_group_keeps_most_severe():
    """L2 fatal 与 L3 minor 同实体 → keep L2;L3 行 grouped_into,keep 带 related。"""
    a = _iss("a", "L2-020", "L2", "fatal", keys=["attachment:A-2"])
    b = _iss("b", "L3-005", "L3", "minor", keys=["attachment:A-2"])
    info = _cross_layer_group([a, b])
    assert info["b"]["grouped_into"] == "a"
    assert info["a"]["grouped_into"] is None
    assert info["a"]["related"] == [
        {"id": "b", "rule_id": "L3-005", "layer": "L3", "severity": "minor", "message": "m"},
    ]
    assert info["b"]["related"] == []


def test_cross_layer_severity_tie_prefers_layer_order():
    """同 severity → L1>L2>L3 层序定 keep(spec:跨层去重 L1>L2>L3)。"""
    l3 = _iss("x", "L3-010", "L3", "major", keys=["attachment:A-1"])
    l2 = _iss("y", "L2-024", "L2", "major", keys=["attachment:A-1"])
    info = _cross_layer_group([l3, l2])
    assert info["x"]["grouped_into"] == "y"  # L2 胜出
    assert info["y"]["grouped_into"] is None


def test_need_human_and_single_layer_never_group():
    """need_human 不参与归并(待人工必须可见);同层/无共享键/单实体不归并。"""
    nh = _iss("n", "L2-020", "L2", "fatal", verdict="need_human", need_human=True, keys=["attachment:A-1"])
    v_same_layer = _iss("s", "L2-024", "L2", "major", keys=["attachment:A-1"])
    v_other_key = _iss("o", "L3-010", "L3", "minor", keys=["attachment:B-1"])
    v_no_keys = _iss("k", "L1-001", "L1", "fatal", keys=[])
    info = _cross_layer_group([nh, v_same_layer, v_other_key, v_no_keys])
    assert info == {}
