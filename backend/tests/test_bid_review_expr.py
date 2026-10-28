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
