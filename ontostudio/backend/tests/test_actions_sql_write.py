"""动作写路径的 SQL 构造与守卫。安全要点：标识符走白名单+加引号，值一律绑定。"""

import pytest

from app.ontology.actions.sql_write import (
    WriteGuardError,
    build_precondition_where,
    build_update_set,
    quote_ident,
)
from app.ontology.schemas import Precondition, StateChange


def test_quote_ident_ok():
    assert quote_ident("status") == '"status"'


@pytest.mark.parametrize("bad", ['a"; DROP TABLE t --', "a b", "1a", "", "abc\n", None, 123])
def test_quote_ident_rejects(bad):
    """含 `"abc\\n"`（`$` 锚点容许尾部换行）、None 与非 str —— 白名单是本模块唯一的注入防线。"""
    with pytest.raises(WriteGuardError, match="identifier"):
        quote_ident(bad)


def test_precondition_eq():
    sql, params = build_precondition_where([Precondition(field="status", op="eq", value="pending_review")])
    assert sql == '"status" = :pre_0'
    assert params == {"pre_0": "pending_review"}


def test_precondition_is_null():
    sql, params = build_precondition_where([Precondition(field="valid_to", op="is_null")])
    assert sql == '"valid_to" IS NULL'
    assert params == {}


def test_precondition_in():
    sql, params = build_precondition_where([Precondition(field="status", op="in", value=["a", "b"])])
    assert sql == '"status" = ANY(:pre_0)'
    assert params == {"pre_0": ["a", "b"]}


def test_empty_preconditions_is_true():
    assert build_precondition_where([]) == ("TRUE", {})


@pytest.mark.parametrize(
    ("op", "value", "expect_sql", "expect_params"),
    [
        ("eq", "a", '"f" = :pre_0', {"pre_0": "a"}),
        ("ne", "a", '"f" <> :pre_0', {"pre_0": "a"}),
        ("in", ["a"], '"f" = ANY(:pre_0)', {"pre_0": ["a"]}),
        ("not_in", ["a"], 'NOT ("f" = ANY(:pre_0))', {"pre_0": ["a"]}),
        ("is_null", None, '"f" IS NULL', {}),
        ("not_null", None, '"f" IS NOT NULL', {}),
    ],
)
def test_all_six_operators_render_expected_sql(op, value, expect_sql, expect_params):
    """6 算子逐个钉住 SQL 文本与绑定形态——not_in 掉 NOT 即 fail-open（守卫放行本不该放的行）。"""
    assert build_precondition_where([Precondition(field="f", op=op, value=value)]) == (expect_sql, expect_params)


def test_preconditions_are_conjoined_with_and():
    """合取，不是析取——OR 会让复合前置条件"任一成立即放行"，是未授权状态迁移。"""
    sql, params = build_precondition_where([Precondition(field="status", op="eq", value="pending_review"), Precondition(field="tenant", op="ne", value="x")])
    assert sql == '"status" = :pre_0 AND "tenant" <> :pre_1'
    assert params == {"pre_0": "pending_review", "pre_1": "x"}


@pytest.mark.parametrize("empty", [None, []])
def test_in_empty_value_is_false(empty):
    """空集的「属于」没有行匹配 → 恒假（fail-closed），绝不产出恒真式。"""
    assert build_precondition_where([Precondition(field="status", op="in", value=empty)]) == ("FALSE", {})


@pytest.mark.parametrize("empty", [None, []])
def test_not_in_empty_value_is_rejected(empty):
    """「不在空集里」字面等于「全部」——漏填 value 若静默放行，前置条件形同不存在（fail-open）。"""
    with pytest.raises(WriteGuardError, match="empty value set for not_in"):
        build_precondition_where([Precondition(field="status", op="not_in", value=empty)])


def test_update_set_literal_and_now():
    sql, params = build_update_set([StateChange(field="status", set="active"), StateChange(field="updated_at", now=True)])
    assert sql == '"status" = :set_0, "updated_at" = NOW()'
    assert params == {"set_0": "active"}


def test_update_set_requires_at_least_one():
    with pytest.raises(WriteGuardError, match="no state change"):
        build_update_set([])
