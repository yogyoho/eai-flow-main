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


@pytest.mark.parametrize("op", ["in", "not_in"])
@pytest.mark.parametrize("bad", ["rejected", 123, {"a": 1}])
def test_in_not_in_non_sequence_value_rejected(op, bad):
    """`list("rejected")` 会拆成字符 → 「not_in rejected」放行它声明要拦的那一行（fail-open）；
    标量则漏出裸 TypeError，不是本模块的错误契约（调用方 catch WriteGuardError 会放过它）。"""
    with pytest.raises(WriteGuardError, match="must be a list"):
        build_precondition_where([Precondition(field="status", op=op, value=bad)])


def test_identifier_check_is_order_independent():
    """畸形标识符不因它与空 in 的声明顺序而被漏检。"""
    with pytest.raises(WriteGuardError, match="identifier"):
        build_precondition_where([Precondition(field="s", op="in", value=[]), Precondition(field="bad ident", op="eq", value=1)])


@pytest.mark.parametrize("op", ["eq", "ne"])
def test_eq_ne_without_value_rejected(op):
    """`col = NULL` 恒不成立且 NULL 该写 is_null——静默容忍会让前置条件永不满足、动作永不触发。"""
    with pytest.raises(WriteGuardError, match="requires a value"):
        build_precondition_where([Precondition(field="status", op=op)])


@pytest.mark.parametrize("falsy", [0, "", False])
def test_eq_falsy_but_present_value_is_legal(falsy):
    """0 / "" / False 是合法值——「漏填」的判别必须是 `is None`，不是 falsy。"""
    sql, params = build_precondition_where([Precondition(field="s", op="eq", value=falsy)])
    assert sql == '"s" = :pre_0'
    assert params == {"pre_0": falsy}


def test_unknown_operator_rejected_on_unvalidated_construct():
    """经 pydantic 校验不可达；model_construct（绕过校验的反序列化路径）仍须被守卫拒绝。"""
    bogus = Precondition.model_construct(field="status", op="bogus", value="x")
    with pytest.raises(WriteGuardError, match="unknown precondition op"):
        build_precondition_where([bogus])


def test_in_params_do_not_alias_caller_list():
    """绑定值 copy 自声明——调用方随后改动 list 不应影响已编译的 params。"""
    src = ["a"]
    _, params = build_precondition_where([Precondition(field="s", op="in", value=src)])
    assert params["pre_0"] == ["a"]
    assert params["pre_0"] is not src


def test_update_set_literal_and_now():
    sql, params = build_update_set([StateChange(field="status", set="active"), StateChange(field="updated_at", now=True)])
    assert sql == '"status" = :set_0, "updated_at" = NOW()'
    assert params == {"set_0": "active"}


def test_update_set_requires_at_least_one():
    with pytest.raises(WriteGuardError, match="no state change"):
        build_update_set([])
