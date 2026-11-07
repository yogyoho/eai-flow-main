"""P1-β批二 T1:or(check-op 层)/regex/subset_of/level_ge/col(A-β2-①:null/未知一律 KeyError→need_human,无哨兵;A-β2-②:阶梯常量保守集)。"""

import pytest

from app.extensions.bid_review.engine.expr import eval_expr
from app.extensions.bid_review.engine.rule_runner import Rule, load_rulepack, run_det_rule

PACK = "app/extensions/bid_review/engine/rulepacks/bid-review-core/1.0.0.yaml"


def test_or_check_op_branch():
    rule = Rule(
        id="T-OR",
        name="t",
        layer="L3",
        type="deterministic",
        applies_to=["*"],
        inputs=["bid.warranty_period"],
        check={"op": "or", "any": ["bid.warranty_period == null", "bid.warranty_period >= 12"]},
        severity="minor",
        evidence=[],
        message_tpl="or 未满足",
        fix_tpl="",
        confidence_gate=1.0,
        enabled=True,
    )
    assert run_det_rule(rule, {"bid.warranty_period": 24}) == []  # 任一支成立(>=12)=过
    issues = run_det_rule(rule, {"bid.warranty_period": 6})
    assert len(issues) == 1 and issues[0]["verdict"] == "violation"  # 全支不成立=violation
    assert run_det_rule(rule, {})[0]["verdict"] == "need_human"  # 字段缺失=need_human


def test_regex_operator():
    assert eval_expr('regex(bid.full_text, "草稿|内部版")', {"bid.full_text": "内部版请勿外传"}) is True
    assert eval_expr('regex(bid.full_text, "草稿|内部版")', {"bid.full_text": "正式版"}) is False
    with pytest.raises(KeyError):
        eval_expr('regex(bid.full_text, "x")', {"bid.full_text": None})  # A-β2-①


def test_subset_of_operator():
    assert eval_expr("subset_of(bid.a, bid.b)", {"bid.a": [" 营业执照 ", "授权书"], "bid.b": ["营业执照", "授权书", "业绩"]}) is True
    assert eval_expr("subset_of(bid.a, bid.b)", {"bid.a": ["营业执照"], "bid.b": ["授权书"]}) is False
    assert eval_expr("subset_of(bid.a, bid.b)", {"bid.a": [], "bid.b": ["x"]}) is True  # 空集是子集(all 空表 PASS 同款显式语义)
    with pytest.raises(KeyError):
        eval_expr("subset_of(bid.a, bid.b)", {"bid.a": None, "bid.b": ["x"]})


def test_level_ge_operator():
    assert eval_expr("level_ge(bid.lv, tender.lv)", {"bid.lv": "一级", "tender.lv": "二级"}) is True
    assert eval_expr("level_ge(bid.lv, tender.lv)", {"bid.lv": "三级", "tender.lv": "二级"}) is False
    assert eval_expr("level_ge(bid.lv, tender.lv)", {"bid.lv": "甲级", "tender.lv": "乙级"}) is True
    with pytest.raises(KeyError):
        eval_expr("level_ge(bid.lv, tender.lv)", {"bid.lv": "不限资质", "tender.lv": "二级"})  # 未知等级→need_human 通路


def test_col_operator():
    assert eval_expr('col(bid.rows, "no")', {"bid.rows": [{"no": "A1"}, {"no": "A2"}, "junk"]}) == ["A1", "A2"]


def test_pack_loads_cleanly_after_new_functions():
    pack = load_rulepack(PACK)  # 既有包继续干净加载:新 _FUNCS/_KNOWN_OPS 不破坏 lint(计数锁定在 test_golden,此处不重复)
    assert len(pack.rules) >= 40


def test_subset_of_type_guards():
    # I-1(质量轮):str 侧静默逐字迭代错判 / 非可迭代 TypeError 逃网——两道守卫统一 KeyError(A-β2-①)
    with pytest.raises(KeyError):
        eval_expr("subset_of(bid.a, bid.b)", {"bid.a": "营业执照", "bid.b": ["营业执照"]})
    with pytest.raises(KeyError):
        eval_expr("subset_of(bid.a, bid.b)", {"bid.a": 3, "bid.b": ["x"]})


def test_regex_invalid_pattern():
    # M-1:re.error(py3.12 非 ValueError 子类)须显式入 KeyError 网(det→need_human)
    with pytest.raises(KeyError):
        eval_expr('regex(bid.t, "(")', {"bid.t": "x"})


def test_or_empty_any_violation():
    # M-2a:空 any=violation(any([]) 为 False;空 all=PASS,数学标准)
    rule = Rule(
        id="T-OR-E",
        name="t",
        layer="L3",
        type="deterministic",
        applies_to=["*"],
        inputs=[],
        check={"op": "or", "any": []},
        severity="minor",
        evidence=[],
        message_tpl="or 未满足",
        fix_tpl="",
        confidence_gate=1.0,
        enabled=True,
    )
    issues = run_det_rule(rule, {})
    assert len(issues) == 1 and issues[0]["verdict"] == "violation"


def test_col_missing_key_rows():
    # M-3:缺键行产 None 条目(不静默丢行,行数守恒)
    assert eval_expr('col(bid.rows, "no")', {"bid.rows": [{"id": 1}, {"no": "A"}]}) == [None, "A"]


def test_sum_decimal_accumulation():
    # 浮点:0.1+0.2=0.30000000000000004;Decimal 累加=0.3 精确(金额加总链无漂移)
    assert eval_expr("sum(bid.vals) == 0.3", {"bid.vals": [0.1, 0.2]}) is True
    assert eval_expr("sum(bid.vals) == bid.total", {"bid.vals": [0.1] * 10, "bid.total": 1.0}) is True
