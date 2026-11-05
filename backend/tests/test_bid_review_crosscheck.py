"""B立项 M5 交叉自检纯函数测试(spec 2026-11-04 §5 M5 行,2026-11-05)。

三检+指标四件:声明↔实体双向(§八1)/页码偏移>5 降置信(§八2,消费 M2
offset_flag)/正副本一致性(candidates 跨文档多值,§八语义自定)/核心字段
成功率(§十,CORE_FIELDS 自定清单)。全部纯服务端零 LLM。
"""

from app.extensions.bid_review.engine.crosscheck import CORE_FIELDS, annotate_page_offset, run_crosscheck


class TestDeclarations:
    def test_missing_and_extra_bidirectional(self):
        cc = run_crosscheck(
            {"tender.required_declarations": ["A-DECL-1", "A-DECL-2"], "bid.declaration_letter_codes": ["A-DECL-1", "A-DECL-X"]},
        )
        assert cc["declarations"]["missing"] == ["A-DECL-2"]  # 声明有实体无→强 MISSING 方向
        assert cc["declarations"]["extra"] == ["A-DECL-X"]  # 实体有清单无→提示补清单,不判 MISSING

    def test_both_empty(self):
        assert run_crosscheck({})["declarations"] == {"missing": [], "extra": []}


class TestPageOffset:
    def test_flag_from_section_tree(self):
        rows = [{"code": "1", "offset": 7, "offset_flag": True}, {"code": "2", "offset": -2, "offset_flag": False}]
        cc = run_crosscheck({"bid.section_tree": rows})
        assert cc["page_offset"] == {"flag": True, "max_abs_offset": 7, "affected_codes": ["1"]}

    def test_no_offset(self):
        assert run_crosscheck({"bid.section_tree": [{"code": "1", "offset": None, "offset_flag": None}]})["page_offset"]["flag"] is False
        assert run_crosscheck({})["page_offset"]["max_abs_offset"] is None


class TestCopyConflicts:
    def test_cross_doc_distinct_values(self):
        cands = {"bid.total_price": [{"value": "1000", "doc_id": "a.pdf"}, {"value": "1200", "doc_id": "b.pdf"}]}
        cc = run_crosscheck({}, cands)
        assert cc["copy_conflicts"] == [{"path": "bid.total_price", "values": ["1000", "1200"], "doc_ids": ["a.pdf", "b.pdf"]}]

    def test_same_value_or_single_doc_no_conflict(self):
        same = {"p": [{"value": "1000", "doc_id": "a"}, {"value": "1000", "doc_id": "b"}]}
        one_doc = {"p": [{"value": "1", "doc_id": "a"}, {"value": "2", "doc_id": "a"}]}
        assert run_crosscheck({}, same)["copy_conflicts"] == []
        assert run_crosscheck({}, one_doc)["copy_conflicts"] == []


class TestCoreSuccessRate:
    def test_ratio_and_empty(self):
        fields = {p: ("x" if i < 6 else None) for i, p in enumerate(CORE_FIELDS)}
        assert run_crosscheck(fields)["core_success_rate"] == 0.75
        assert run_crosscheck({})["core_success_rate"] == 0.0
        assert len(CORE_FIELDS) == 8


class TestAnnotatePageOffset:
    def test_annotates_page_bearing_paths_only_when_flag(self):
        fc = {"a": {"conf": 0.9, "verified": True}, "b": {"conf": None, "verified": False}}
        prov = {"a": {"page": 3}, "b": {"page": None}}
        off = {"flag": True, "max_abs_offset": 7, "affected_codes": ["1"]}
        out = annotate_page_offset(fc, prov, off)
        assert out["a"] == {"conf": 0.9, "verified": True, "page_offset": True}
        assert "page_offset" not in out["b"]  # page null 不注记

    def test_no_flag_no_mutation(self):
        fc = {"a": {"conf": 0.9, "verified": True}}
        assert annotate_page_offset(fc, {"a": {"page": 3}}, {"flag": False}) == fc
        assert annotate_page_offset(None, None, None) in (None, {})
