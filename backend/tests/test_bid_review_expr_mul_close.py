"""`*` 乘法算子 + close 容差内建(P1-β批一 Task 1;裁决 A-β1-①②:空值 KeyError→need_human 通路,无三值哨兵)。"""

import pytest

from app.extensions.bid_review.engine.expr import eval_expr, validate_expr


def test_mul_basic_and_precedence():
    assert eval_expr("2 * 3 == 6") is True
    assert eval_expr("2 * 3 == 7") is False
    # * 优先级高于比较:a * b == c 解析为 (a*b)==c,不是 a==(b*c)
    assert eval_expr("close(100 * 3, 300, 0.01)") is True


def test_mul_left_assoc_chain():
    assert eval_expr("2 * 3 * 4 == 24") is True


def test_mul_close_tolerance_band():
    assert eval_expr("close(0.1 * 3, 0.3, 0.01)") is True  # float 误差 ~5.5e-17 << 0.01
    assert eval_expr("close(100.0, 100.5, 0.01)") is False


def test_wildcard_path_unaffected():
    # [*] 通配走 _atom 内部括号消费,不受 _term 层影响(回归面)
    fields = {"bid.rows": [{"amount": 1}, {"amount": 2}]}
    assert eval_expr("count(bid.rows[*].amount)", fields) == 2


def test_mul_none_coercion_keyerror():
    # A-β1-①:None/非数值 → KeyError(上层 run_det_rule 转 need_human),禁 TypeError 逃逸
    with pytest.raises(KeyError):
        eval_expr("null * 2")
    with pytest.raises(KeyError):
        eval_expr("'abc' * 2")


def test_close_bad_input_keyerror():
    with pytest.raises(KeyError):
        eval_expr("close('abc', 1, 0.01)")
    with pytest.raises(KeyError):
        eval_expr("close(1, null, 0.01)")


def test_load_time_validation_accepts_new_syntax():
    validate_expr("close(r.price * r.qty, r.amount, 0.01)")  # 不抛即过
