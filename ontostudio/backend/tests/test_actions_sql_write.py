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


def test_update_set_literal_and_now():
    sql, params = build_update_set([StateChange(field="status", set="active"), StateChange(field="updated_at", now=True)])
    assert sql == '"status" = :set_0, "updated_at" = NOW()'
    assert params == {"set_0": "active"}


def test_update_set_requires_at_least_one():
    with pytest.raises(WriteGuardError, match="no state change"):
        build_update_set([])
