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


def test_years_text_extract_primitive():
    # A-β8-②(P1-β批八T1,2026-11-08):years() 年数文本提取原语三钉。中文数字年数
    # (「三年」「三年以上」→3)与阿拉伯数字(「近3 年」容忍数字与「年」间空白→3);
    # 解析失败/无年份语义 → None(bug-4227 律:null=不在场,上层走 unclear/UNKNOWN
    # 通路,禁 raise)。日历年形态(「2024年」)非年数 → 保守 None(负向后顾防中段截取)。
    assert eval_expr("years(bid.qual_text) == 3", {"bid.qual_text": "三年"}) is True
    assert eval_expr("years(bid.qual_text) == 3", {"bid.qual_text": "三年以上"}) is True
    assert eval_expr("years(bid.qual_text) == 3", {"bid.qual_text": "近3 年"}) is True
    assert eval_expr("years(bid.qual_text) == null", {"bid.qual_text": "业绩优良,无违约记录"}) is True
    assert eval_expr("years(bid.qual_text) == null", {"bid.qual_text": "2024年通过复审"}) is True
    assert eval_expr("years(bid.qual_text) == null", {"bid.qual_text": None}) is True


def test_num_normalization_primitive():
    # 批十四(W-real-1/2,2026-11-11):num() 数值归一原语——容器键 {value,unit} dict 递归解包
    # (真实件 tender.max_price 形态)、文本形态(「6%」/千分位「1,000,001」/元缀「225000元」)
    # → float;int/float 直通;bool 拒(钱/税语义,禁 True=1);不可解析 → KeyError
    # (run_det_rule 只捕 KeyError→need_human,禁 TypeError 逃网);双表注册(_FUNCS 白名单+
    # _BUILTIN 分发,批八 years() 律)。
    assert eval_expr("num(bid.tax_rate) == 6", {"bid.tax_rate": "6%"}) is True
    assert eval_expr("num(bid.total_price) == 225000", {"bid.total_price": "225000元"}) is True
    assert eval_expr("num(bid.total_price) == 1000001", {"bid.total_price": "1,000,001"}) is True
    assert eval_expr("num(tender.max_price) == 230000", {"tender.max_price": {"value": 230000, "unit": "元"}}) is True
    assert eval_expr("num(bid.x) == 6.5", {"bid.x": 6.5}) is True
    with pytest.raises(KeyError):
        eval_expr("num(bid.x) == 1", {"bid.x": True})
    with pytest.raises(KeyError):
        eval_expr("num(bid.x) == 1", {"bid.x": "贰拾万元"})
    with pytest.raises(KeyError):
        eval_expr("num(bid.x) == 1", {"bid.x": {"amount": 1}})


def test_codes_filters_falsy():
    # 批十四(W-real-3,2026-11-11):codes() falsy 过滤——None/'' 码入集使 set_eq message
    # 渲染「漏项 ,增项 None」垃圾;真实件投标 boq 行缺 code 键即此形态。
    rows = [{"code": "BM-001"}, {"code": None}, {"name": "无码行"}, {"code": ""}, {"code": "BM-002"}]
    # DSL 无列表字面量 → 期望集走字段
    assert eval_expr("codes(bid.boq_items) == bid.want", {"bid.boq_items": rows, "bid.want": ["BM-001", "BM-002"]}) is True
    assert eval_expr("codes(bid.boq_items) == bid.want", {"bid.boq_items": None, "bid.want": []}) is True
