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


def test_none_allow_means_all_fields_none():
    r = FilterRule.from_wire({"operator": "none_allow"})
    assert r.operator == "none_allow" and r.field is None and r.children is None
