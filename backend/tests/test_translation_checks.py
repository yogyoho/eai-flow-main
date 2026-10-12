"""Machine-gate unit tests (pure functions, T4)."""

from app.extensions.translation import checks


class TestPlaceholders:
    def test_roundtrip_preserves_numbers(self):
        reg = checks.Registry()
        text = "产量为 3,200 tonnes，占比 45.6%。"
        ph = checks.extract_placeholders(text, reg)
        assert "3,200" not in ph and "45.6" not in ph
        assert "⟦#0⟧" in ph and "⟦#1⟧" in ph
        assert checks.reinject_placeholders(ph, reg) == text

    def test_token_collision_proof(self):
        # 正文本身含 ⟦#0⟧ 字样时不会与占位符混淆（围栏 token 唯一性，C-2）
        reg = checks.Registry()
        text = "标记 ⟦#0⟧ 与数量 42"
        ph = checks.extract_placeholders(text, reg)
        back = checks.reinject_placeholders(ph, reg)
        assert back == text  # 原文 token 原样往返

    def test_reinject_out_of_range_keeps_token(self):
        reg = checks.Registry()
        reg.register("42")
        assert checks.reinject_placeholders("x ⟦#7⟧ y", reg) == "x ⟦#7⟧ y"


class TestNormalization:
    def test_fr_thousands_and_decimal(self):
        assert checks.normalized_number_multiset("1 234,56", "fr") == ["1234.56"]
        assert checks.normalized_number_multiset("1.234,56", "fr") == ["1234.56"]

    def test_en_thousands(self):
        assert checks.normalized_number_multiset("1,234.56", "en") == ["1234.56"]

    def test_currency_stripped(self):
        assert checks.normalized_number_multiset("$1,234", "en") == ["1234"]
        assert checks.normalized_number_multiset("EUR 2.500", "fr") == ["2500"]

    def test_paren_negative(self):
        assert checks.normalized_number_multiset("(1,234)", "en") == ["-1234"]

    def test_fullwidth(self):
        assert checks.normalized_number_multiset("１２３４", "zh") == ["1234"]


class TestNumericAxis:
    def test_zero_change_passes(self):
        src = "产量 3,200 吨，占比 45.6%"
        dst = "产量 3200 吨，占比 45.6%"
        assert checks.numeric_multiset_violations(src, dst, "zh") == []

    def test_dropped_number_fails(self):
        src = "产量 3,200 吨和库存 500 吨"
        dst = "产量 3200 吨"
        violations = checks.numeric_multiset_violations(src, dst, "zh")
        assert any("500" in v for v in violations)

    def test_hallucinated_number_fails(self):
        src = "产量 3200 吨"
        dst = "产量 3200 吨，增长 12%"
        assert checks.numeric_multiset_violations(src, dst, "zh")

    def test_fr_source_norm_matches_zh_render(self):
        src = "1 234,56 tonnes"
        dst = "1234.56 吨"
        assert checks.numeric_multiset_violations(src, dst, "fr") == []

    def test_cjk_numerals_out_of_scope(self):
        # R7/SC-6: CJK 数字 v1 出闸——三千 不参与比对
        assert checks.normalized_number_multiset("三千吨", "zh") == []


class TestStructureAxis:
    def test_parity_pass(self):
        assert checks.structure_parity_violations(["paragraph", "table"], ["paragraph", "table"]) == []

    def test_count_drift_fails(self):
        assert checks.structure_parity_violations(["paragraph"], [])

    def test_type_drift_fails(self):
        assert checks.structure_parity_violations(["table"], ["paragraph"])


class TestTerminologyAxis:
    def test_force_term_missing_fails(self):
        v = checks.terminology_violations("iron ore concentrate price", "铁矿石价格", {"iron ore concentrate": "铁精矿"}, set())
        assert any("iron ore concentrate" in x for x in v)

    def test_force_term_present_passes(self):
        v = checks.terminology_violations("iron ore concentrate", "铁精矿价格", {"iron ore concentrate": "铁精矿"}, set())
        assert v == []

    def test_dont_translate_altered_fails(self):
        v = checks.terminology_violations("ArcelorMittal signed", "安赛乐米塔尔签署", {}, {"ArcelorMittal"})
        assert any("ArcelorMittal" in x for x in v)

    def test_dont_translate_preserved_passes(self):
        v = checks.terminology_violations("ArcelorMittal signed", "ArcelorMittal 签署", {}, {"ArcelorMittal"})
        assert v == []


class TestNumericAxisComposite:
    def test_run_numeric_axis_placeholder_drift(self):
        # 占位符计数漂移（源 2 个 → 译 1 个）→ 注册表对账报警
        v = checks.run_numeric_axis(
            "数量 42 单价 7",
            "数量 ⟦#0⟧",
            "zh",
            placeholder_source_text="数量 ⟦#0⟧ 单价 ⟦#1⟧",
        )
        assert any("placeholder" in x for x in v)
