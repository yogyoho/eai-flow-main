import pytest

from app.extensions.bid_review.engine.expr import ExprError, eval_expr

F = {
    "bid.total_price": 1000001.0,
    "tender.max_price": 1000000.0,
    "bid.detail_rows": [{"code": "A", "amount": 500000.0}, {"code": "B", "amount": 500001.0}],
    "tender.required_signatures": ["法定代表人", "授权代表"],
    "bid.signature_slots": [{"name": "法定代表人", "signed": True, "sealed": False}],
    "bid.duration_main_text": {"value": 6, "unit": "month"},
    "bid.duration_schedule": {"value": 180, "unit": "day"},
    "bid.entity.license_name": "甲公司有限公司",
    "project.entity_whitelist.names": ["甲公司有限公司"],
    "bid.authorization.scope": "本次投标及签署",
    "tender.project_identity.name": "某煤矿工程",
}


def test_comparison_and_precondition():
    assert eval_expr("bid.total_price > tender.max_price", F) is True
    assert eval_expr("bid.total_price <= tender.max_price", F) is False


def test_quantifier_all_any():
    assert eval_expr("all(bid.detail_rows, r -> r.amount >= 500000.0)", F) is True
    assert eval_expr("all(bid.detail_rows, r -> r.amount >= 500001.0)", F) is False
    assert eval_expr("any(bid.detail_rows, r -> r.amount > 500000.5)", F) is True


def test_every_exists_where():
    assert eval_expr("every(t in tender.required_signatures, exists(s in bid.signature_slots where s.name == t))", F) is False


def test_functions():
    assert eval_expr("normalize_unit(bid.duration_main_text) == normalize_unit(bid.duration_schedule)", F) is True
    assert eval_expr("sum(bid.detail_rows[*].amount) == 1000001.0", F) is True
    assert eval_expr("count(bid.detail_rows) == 2", F) is True
    assert eval_expr("covers(bid.authorization.scope, '本次投标及签署')", F) is True
    assert eval_expr("bid.entity.license_name in project.entity_whitelist.names", F) is True


def test_unknown_field_and_func():
    with pytest.raises(KeyError):
        eval_expr("bid.nonexistent == 1", F)
    with pytest.raises(ExprError):
        eval_expr("__import__('os').system('x')", F)


def test_normalize_unit_text_typed_value_raises_keyerror():
    # fix-round 评审项(L1-014/L1-015/L3-005):*_text 命名的工期/质保字段若以原始文本回流,
    # 数值强转失败必须 raise KeyError(复用 run_det_rule 既有 need_human 通路),禁止
    # ValueError 逃逸——否则单字段类型偏差会让整条审查任务经 _infra_fail 重试后 failed。
    with pytest.raises(KeyError):
        eval_expr("normalize_unit(bid.duration_main_text) == 540", {"bid.duration_main_text": "540日历天"})
    with pytest.raises(KeyError):
        eval_expr("normalize_unit(bid.duration_main_text) == 540", {"bid.duration_main_text": {"value": "540天", "unit": "day"}})


def test_number_to_words_conventional_forms():
    # 评审修正 A11/A11a canonical 验收:非整万总价的 conventional 大写(基线零错置会对正确投标误报 fatal L1-010)
    cases = [
        (1234567.0, "壹佰贰拾叁万肆仟伍佰陆拾柒元整"),
        (1000456.0, "壹佰万零肆佰伍拾陆元整"),
        (100001.0, "壹拾万零壹元整"),
        (1004567.0, "壹佰万零肆仟伍佰陆拾柒元整"),  # junction 类防盲区(A11a:上一输出段末位为 0 亦须段间零)
    ]
    for amount, words in cases:
        f = {"bid.total_price": amount, "bid.total_price_words": words}
        assert eval_expr("number_to_words(bid.total_price) == bid.total_price_words", f) is True, f"{amount} 应得 {words}"


def test_number_to_words_negative_rejected():
    # A11:负数入参 raise(基线 while n: 对负数死循环: -1 // 10000 == -1)
    with pytest.raises(ExprError):
        eval_expr("number_to_words(-1.0) == 'x'", F)


def test_truncated_expr_raises_token_exhaustion():
    # A11:token 耗尽(tok is None)→ ExprError,禁止 str(None) 落成 None 字面量求值(截断表达式会静默翻转判定)
    with pytest.raises(ExprError):
        eval_expr("bid.total_price ==", F)


def test_wild_requires_attr_after_star():
    # A11 收紧:[*] 后非 .attr token → ExprError(勿照抄副本容忍 parse('bid.detail_rows[*]amount'))
    with pytest.raises(ExprError):
        eval_expr("bid.detail_rows[*]amount == 1.0", F)
