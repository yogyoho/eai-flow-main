"""B立项 M3 表格/清单行抽取单测(spec §5,2026-11-05):boq_rows 行级归一闸(required 服务端回填)+ table_cells 临时契约闸 + prompt/baseline。"""

from app.extensions.bid_review.engine.extract import (
    FIELD_TYPE_CONTRACTS,
    build_tables_baseline,
    build_tables_prompt,
    normalize_boq_rows,
    normalize_table_cells,
)


class TestContracts:
    def test_m3_paths_have_contracts(self):
        assert "bid.boq_rows" in FIELD_TYPE_CONTRACTS
        assert "bid.table_cells" in FIELD_TYPE_CONTRACTS


class TestNormalizeBoqRows:
    def test_backfills_required_from_tender_codes(self):
        rows = normalize_boq_rows(
            [
                {"id": "1.1", "name": "挖土方", "unit": "m3", "qty": 100, "price": 50},
                {"id": "9.9", "name": "自附项", "unit": "项", "qty": 1, "price": 0},
            ],
            ["1.1", "1.2"],
        )
        assert rows[0]["required"] is True
        assert rows[1]["required"] is False

    def test_drops_and_clamps(self):
        rows = normalize_boq_rows(
            [
                {"id": " ", "name": " "},
                "junk",
                {"id": " 2 ", "name": "钢 筋", "qty": True, "price": "3", "unit": 1, "required": True},
            ],
            [],
        )
        assert len(rows) == 1
        r = rows[0]
        # 模型偷报 required 被闸丢弃重算(设计 §4.5:必填口径唯一来自招标侧)
        assert r["required"] is False
        assert r["qty"] is None and r["price"] is None and r["unit"] == ""
        assert r["id"] == "2" and r["name"] == "钢 筋"  # id/unit strip,name 保内部空格

    def test_qty_price_nonnegative_only(self):
        assert normalize_boq_rows([{"id": "1", "name": "A", "price": -5}], [])[0]["price"] is None
        assert normalize_boq_rows([{"id": "1", "name": "A", "qty": 0}], [])[0]["qty"] == 0  # 0 合法
        assert normalize_boq_rows([{"id": "1", "name": "A", "qty": 3.5}], [])[0]["qty"] == 3.5
        assert normalize_boq_rows([{"id": "1", "name": "A", "qty": None}], [])[0]["qty"] is None

    def test_amount_numericization_gate(self):
        # P1-β Task 2:amount 与 qty/price 同 _num 闸(bool/负数→None),另收 float() 可解析数字串(L3-019 operand)
        assert normalize_boq_rows([{"id": "1", "name": "A", "amount": True}], [])[0]["amount"] is None
        assert normalize_boq_rows([{"id": "1", "name": "A", "amount": -0.01}], [])[0]["amount"] is None
        assert normalize_boq_rows([{"id": "1", "name": "A", "amount": "abc"}], [])[0]["amount"] is None
        assert normalize_boq_rows([{"id": "1", "name": "A", "amount": 300}], [])[0]["amount"] == 300  # 数值直收
        # isfinite 负证据门禁(M5 惯例):json.loads 默认接受 NaN/Infinity 字面量,此处是
        # NaN 不入 L3-019 乘法比较的唯一防线
        assert normalize_boq_rows([{"id": "1", "name": "A", "amount": "nan"}], [])[0]["amount"] is None
        assert normalize_boq_rows([{"id": "1", "name": "A", "amount": float("inf")}], [])[0]["amount"] is None

    def test_id_or_name_alone_survives(self):
        rows = normalize_boq_rows([{"id": "1.1"}, {"name": "只有名"}], [])
        assert len(rows) == 2
        assert rows[0] == {"id": "1.1", "name": "", "unit": "", "qty": None, "price": None, "amount": None, "required": False}

    def test_non_list_returns_empty(self):
        assert normalize_boq_rows(None, ["1"]) == []
        assert normalize_boq_rows("junk", ["1"]) == []
        # tender_codes=None(招标侧无信号)→ 行保留,required 全 False
        assert normalize_boq_rows([{"id": "1", "name": "A"}], None) == [{"id": "1", "name": "A", "unit": "", "qty": None, "price": None, "amount": None, "required": False}]


class TestNormalizeTableCells:
    def test_drops_blank_value_and_bad_page(self):
        cells = normalize_table_cells(
            [
                {"table_no": "表3 ", "page": 12, "row_label": "总价", "col_label": "金额", "value": "100万"},
                {"value": "  "},
                {"value": "x", "page": True},
            ]
        )
        # value 空白丢行;坏 page→None 不丢行(M2 同款语义)
        assert len(cells) == 2
        assert cells[0]["table_no"] == "表3" and cells[0]["page"] == 12
        assert cells[1] == {"table_no": "", "page": None, "row_label": "", "col_label": "", "value": "x"}

    def test_non_list_returns_empty(self):
        assert normalize_table_cells(None) == []
        assert normalize_table_cells("junk") == []
        assert normalize_table_cells([{"value": "v"}, 42]) == [{"table_no": "", "page": None, "row_label": "", "col_label": "", "value": "v"}]


class TestPromptAndBaseline:
    def test_prompt_contains_both_contracts_and_tender_boq(self):
        docs = [{"doc_id": "b.pdf", "role": "bid", "text": "x"}]
        prompt = build_tables_prompt(
            docs,
            [{"code": "1.1", "name": "挖土方"}, {"code": "1.2"}],
        )
        assert "表格定位器" in prompt
        assert "逐单元格" in prompt
        assert "1.1" in prompt and "1.2" in prompt  # 招标 BOQ codes(必填口径)
        assert "[[p." in prompt
        assert "禁止编造" in prompt
        assert "required 字段禁止输出" in prompt

    def test_baseline_two_paths(self):
        def fake_fn(docs, tender_rows):
            return {"boq_rows": [{"id": "1.1", "name": "A"}], "table_cells": [{"value": "v"}]}

        out = build_tables_baseline(
            [{"doc_id": "b.pdf", "role": "bid", "text": "x"}],
            fake_fn,
            [{"code": "1.1"}, {"code": "1.2"}],
        )
        assert out["boq_rows"][0]["required"] is True
        assert out["table_cells"][0]["value"] == "v"

    def test_baseline_none_signal_both_empty(self):
        assert build_tables_baseline([], lambda *a: None, None) == {"boq_rows": [], "table_cells": []}

    def test_baseline_partial_failure_keeps_other_path(self):
        def half_fn(docs, tender_rows):
            return {"boq_rows": [{"id": "2", "name": "B"}]}  # table_cells 键缺席

        out = build_tables_baseline([], half_fn, [{"code": "1.1"}])
        assert out["boq_rows"][0]["required"] is False
        assert out["table_cells"] == []
