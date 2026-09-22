"""FilterRule → 参数化 WHERE 编译。安全要点：字段名走标识符白名单，值一律绑定。"""

import pytest

from app.ontology.scope import FilterRule, ScopeCompileError, rule_to_sql


def test_allow_all_compiles_to_true():
    assert rule_to_sql(FilterRule(operator="allow_all")) == ("TRUE", {})


def test_none_allow_compiles_to_false():
    assert rule_to_sql(FilterRule(operator="none_allow")) == ("FALSE", {})


def test_eq_binds_value_not_interpolates():
    sql, params = rule_to_sql(FilterRule(operator="eq", field="dept_id", value="d1"))
    assert sql == '"dept_id" = :scope_0'
    assert params == {"scope_0": "d1"}


def test_in_uses_any():
    sql, params = rule_to_sql(FilterRule(operator="in", field="id", value=["a", "b"]))
    assert sql == '"id" = ANY(:scope_0)'
    assert params == {"scope_0": ["a", "b"]}


def test_overlap_uses_array_operator():
    sql, _ = rule_to_sql(FilterRule(operator="overlap", field="dept_ids", value=["a"]))
    assert sql == '"dept_ids" && :scope_0'


def test_and_or_not_nest_with_parens():
    left = FilterRule(operator="eq", field="a", value=1)
    right = FilterRule(operator="eq", field="b", value=2)
    sql, params = rule_to_sql(FilterRule(operator="or", children=[left, right]))
    assert sql == '("a" = :scope_0 OR "b" = :scope_1)'
    assert params == {"scope_0": 1, "scope_1": 2}

    sql, _ = rule_to_sql(FilterRule(operator="not", children=[left]))
    assert sql == 'NOT ("a" = :scope_0)'


def test_bindings_override_physical_column():
    sql, _ = rule_to_sql(
        FilterRule(operator="eq", field="user_id", value="u1"),
        bindings={"user_id": "created_by"},
    )
    assert sql == '"created_by" = :scope_0'


def test_unbound_field_raises():
    with pytest.raises(ScopeCompileError, match="unbound"):
        rule_to_sql(FilterRule(operator="eq", field="user_id", value="u1"), bindings={})


@pytest.mark.parametrize("bad", ['a"; DROP TABLE x --', "a b", "1col", ""])
def test_illegal_identifier_rejected(bad):
    """注入用例：字段名不走值绑定，必须走白名单。"""
    with pytest.raises(ScopeCompileError, match="identifier"):
        rule_to_sql(FilterRule(operator="eq", field=bad, value=1))


def test_wire_roundtrip():
    rule = FilterRule(
        operator="or",
        children=[
            FilterRule(operator="eq", field="a", value=1),
            FilterRule(operator="allow_all"),
        ],
    )
    assert FilterRule.from_wire(rule.to_wire()) == rule

    # M-2: children=[] 与 children=null 都折叠为 None。这是 wire 契约的一部分（本测试名承诺
    # 普适往返，故不能只靠注释"记"着），且编译期二者等价——三种复合算子走同一分支，
    # 空 and/not 同样报错、空 or 同样 FALSE。旧形态的真正落地点是 gateway to_dict 的
    # "children": null，故归一化必须在此钉住。
    assert FilterRule(operator="or", children=[]).to_wire() == {"operator": "or", "children": []}
    assert FilterRule.from_wire({"operator": "or", "children": []}) == FilterRule(operator="or", children=None)
    assert FilterRule.from_wire({"operator": "or", "children": None}) == FilterRule(operator="or", children=None)


def test_none_allow_means_all_fields_none():
    r = FilterRule.from_wire({"operator": "none_allow"})
    assert r.operator == "none_allow" and r.field is None and r.children is None


# --- 审查裁定补丁（I-1/I-2/I-3 + M-2/M-3/M-6/M-7）--------------------------------------
# I-1：空 and/not 原本编译为 TRUE（静默放行全域），与网关参考实现 to_sqlalchemy 的
# deny 方向相反。allow_all 有独立算子表达全量，故空 and/not 无合法含义 -> 拒绝。
# 空 or 保持 FALSE（已在 deny 方向，与参考实现同向，无害）。
def test_empty_and_not_rejected_while_or_still_denies():
    with pytest.raises(ScopeCompileError, match="empty composite rule"):
        rule_to_sql(FilterRule(operator="and", children=[]))
    with pytest.raises(ScopeCompileError, match="empty composite rule"):
        rule_to_sql(FilterRule(operator="not", children=[]))
    # children=None（wire 的 "children": null）与 [] 折成同一形态，必须同样被拒。
    with pytest.raises(ScopeCompileError, match="empty composite rule"):
        rule_to_sql(FilterRule(operator="and", children=None))
    assert rule_to_sql(FilterRule(operator="or", children=[])) == ("FALSE", {})


# M-3：not 只取 children[0]，多余子节点不得静默丢弃。
def test_not_requires_exactly_one_child():
    two = [FilterRule(operator="allow_all"), FilterRule(operator="allow_all")]
    with pytest.raises(ScopeCompileError, match="exactly one child"):
        rule_to_sql(FilterRule(operator="not", children=two))


# I-2：裸字符串 = 单元素集合（与 gateway from_template 的
# "resolved if isinstance(resolved, list) else [resolved]" 同义），绝不按字符拆开。
def test_bare_string_is_single_element_set_not_char_split():
    sql, params = rule_to_sql(FilterRule(operator="in", field="c", value="abc"))
    assert sql == '"c" = ANY(:scope_0)'
    assert params == {"scope_0": ["abc"]}

    _, params = rule_to_sql(FilterRule(operator="not_in", field="c", value="abc"))
    assert params == {"scope_0": ["abc"]}

    # 非 list 的序列仍走既有 list() 归一，不得被包成 [tuple]。
    _, params = rule_to_sql(FilterRule(operator="in", field="c", value=("a", "b")))
    assert params == {"scope_0": ["a", "b"]}


# M-7：ne / not_in 目前无产出者，但属安全相关能力，钉住字面形态防回归。
def test_ne_compiles_to_inequality():
    assert rule_to_sql(FilterRule(operator="ne", field="c", value=1)) == ('"c" <> :scope_0', {"scope_0": 1})


def test_not_in_wraps_any_in_not():
    assert rule_to_sql(FilterRule(operator="not_in", field="c", value=["a"])) == ('NOT ("c" = ANY(:scope_0))', {"scope_0": ["a"]})


# M-6：敌意**值**用例。既有 4 条注入用例只打标识符；值不参与 SQL 文本拼接，
# 恶意值必须原样落进 params 且 SQL 片段字面不变。
def test_hostile_value_stays_bound_verbatim():
    hostile = "x'; DROP TABLE t --"
    sql, params = rule_to_sql(FilterRule(operator="eq", field="c", value=hostile))
    assert sql == '"c" = :scope_0'
    assert params == {"scope_0": hostile}


# I-3：from_wire 的数据源是外部 JSON，缺键/类型错一律归一为 ScopeCompileError，
# 否则 Task 5 的 executor 会把它变成 500 + 无意义堆栈（异常方向本身 fail-closed，非安全洞）。
@pytest.mark.parametrize("bad", [{"field": "a"}, {"operator": {"$ne": 1}}, {"operator": 7}, {"operator": None}])
def test_malformed_wire_raises_scope_error(bad):
    with pytest.raises(ScopeCompileError, match="malformed wire rule"):
        FilterRule.from_wire(bad)


# I-3 延伸（同类漏检：children / 非对象节点）：审查枚举的 4 例只打 operator，
# 但 children 类型错同样漏 AttributeError/TypeError，与 I-3 目的冲突
# （executor 会把它变成 500 而非 4xx）。契约既声明"所有畸形输入都归一"，就须自洽。
@pytest.mark.parametrize(
    "bad",
    [
        {"operator": "and", "children": "abc"},  # 字符串会被按字符迭代
        {"operator": "and", "children": 7},
        {"operator": "or", "children": {"a": 1}},
        {"operator": "or", "children": ["abc"]},  # 列表元素非对象
        ["not", "a", "dict"],  # 整棵规则非对象
        "not-a-dict",
    ],
)
def test_malformed_wire_children_raises_scope_error(bad):
    with pytest.raises(ScopeCompileError, match="malformed wire rule"):
        FilterRule.from_wire(bad)


def test_rule_to_sql_rejects_non_filterrule_node():
    """未经 from_wire 的裸 JSON 子节点必须报 ScopeCompileError，而非 AttributeError。"""
    with pytest.raises(ScopeCompileError, match="must be a FilterRule"):
        rule_to_sql({"operator": "eq", "field": "c", "value": 1})

    nested = FilterRule(operator="or", children=[FilterRule(operator="eq", field="a", value=1)])
    nested.children.append({"operator": "eq", "field": "b", "value": 2})
    with pytest.raises(ScopeCompileError, match="must be a FilterRule"):
        rule_to_sql(nested)


def test_non_string_binding_target_rejected():
    """scope_bindings 来自手写 YAML，{user_id: 1}（漏引号）就是 int。"""
    with pytest.raises(ScopeCompileError, match="identifier"):
        rule_to_sql(FilterRule(operator="eq", field="user_id", value="u1"), bindings={"user_id": 1})


def test_trailing_newline_is_not_a_valid_identifier():
    """M-1：`$` 锚点允许尾部换行，白名单必须用 fullmatch 严格匹配。"""
    with pytest.raises(ScopeCompileError, match="identifier"):
        rule_to_sql(FilterRule(operator="eq", field="abc\n", value=1))
    with pytest.raises(ScopeCompileError, match="identifier"):
        rule_to_sql(FilterRule(operator="eq", field="a", value=1), bindings={"a": "abc\n"})
