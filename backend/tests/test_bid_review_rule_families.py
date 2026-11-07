"""R2+ 规则族补齐测试(2026-11-05):四条 det 规则消费 M1-M5 悬空字段。

零翻红取证(plan 2026-11-05-bid-review-r2-rule-families 裁决⑤):golden 55 个案
fields 无第二段字段→新规则 inputs 缺失→need_human(verdict≠violation)→strict
只数 violation→零翻红;test_new_rules_need_human_on_legacy_baseline 是该论证的常驻回归锁。
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.extensions.bid_review.engine.eval_core import evaluate_fields, wrap_model_fn
from app.extensions.bid_review.engine.registry import consumed_by, lint_rules, universe
from app.extensions.bid_review.engine.rule_runner import load_rulepack, run_det_rule

PACK = str(Path(__file__).resolve().parent.parent / "app" / "extensions" / "bid_review" / "engine" / "rulepacks" / "bid-review-core" / "1.0.0.yaml")

NEW_IDS = {"L2-015", "L2-022", "L2-041", "L3-026"}

_QUIET = json.dumps(
    {"verdicts": [{"clause_id": "quiet", "verdict": "full", "confidence": 1.0, "reason": "安静应答", "evidence": []}]},
    ensure_ascii=False,
)


def _rules():
    return {r.id: r for r in load_rulepack(PACK).rules}


class TestL2041RequiredRowPrice:
    """L2-041 必填清单行未报价(整合版对齐 W3,原 EAI L2-022;fatal=EAI 上调 C-11;tender.required_fields+bid.boq_rows;qty 不判)。"""

    def test_required_row_missing_price_violation(self):
        rule = _rules()["L2-041"]
        fields = {
            "tender.required_fields": ["BOQ-1", "BOQ-2"],
            "bid.boq_rows": [
                {"id": "BOQ-1", "name": "设备采购", "unit": "套", "qty": 2, "price": None, "required": True},
                {"id": "BOQ-2", "name": "安装费", "unit": "项", "qty": 1, "price": 5000, "required": True},
                {"id": "X-9", "name": "自附行", "unit": "批", "qty": 1, "price": None, "required": False},
            ],
        }
        issues = run_det_rule(rule, fields)
        assert len(issues) == 1, f"必填行缺单价应恰好一条 issue(自附行不判): {issues}"
        assert issues[0]["verdict"] == "violation" and issues[0]["severity"] == "fatal"
        assert "BOQ-1" in issues[0]["message"] and "设备采购" in issues[0]["message"]

    def test_pass_and_missing_inputs(self):
        rule = _rules()["L2-041"]
        ok = {"tender.required_fields": ["B1"], "bid.boq_rows": [{"id": "B1", "name": "x", "unit": "", "qty": 1, "price": 9.9, "required": True}]}
        assert run_det_rule(rule, ok) == []
        assert run_det_rule(rule, {"tender.required_fields": ["B1"]})[0]["verdict"] == "need_human"


class TestL2022BlankAttachment:
    """L2-022 附件实体内容空白(整合版对齐 W2,原 EAI L2-023;bid.attachments;major;None 不判)。"""

    _ATT = {"no": "A", "name": "营业执照", "norm_name": "营业执照", "pages": [1, 2], "type_fingerprint": "license", "fingerprint_conf": 0.9, "is_empty_text": True, "anchor": {}}

    def test_blank_and_none_pass(self):
        rule = _rules()["L2-022"]
        fields = {"bid.attachments": [dict(self._ATT), dict(self._ATT, no="B", name="业绩合同", is_empty_text=False)]}
        issues = run_det_rule(rule, fields)
        assert len(issues) == 1 and issues[0]["verdict"] == "violation" and issues[0]["severity"] == "major"
        assert "营业执照" in issues[0]["message"]
        assert run_det_rule(rule, {"bid.attachments": [dict(self._ATT, is_empty_text=None)]}) == []

    def test_missing_input_need_human(self):
        assert run_det_rule(_rules()["L2-022"], {})[0]["verdict"] == "need_human"


class TestL3026ClusterUnsure:
    """L3-026 业绩条目聚类存疑(整合版对齐 W4 段尾扩展,原 EAI L3-019;bid.performance_groups;major;M4 UNKNOWN 的规则面)。"""

    def test_ok_false_group_violation(self):
        rule = _rules()["L3-026"]
        fields = {
            "bid.performance_groups": [
                {"group_id": "G1", "ok": False, "members": [{"name": "一期", "client": "甲"}]},
                {"group_id": "G2", "ok": True, "members": [{"name": "二期", "client": "乙"}]},
            ]
        }
        issues = run_det_rule(rule, fields)
        assert len(issues) == 1 and issues[0]["verdict"] == "violation" and issues[0]["severity"] == "major"
        assert "G1" in issues[0]["message"]

    def test_all_ok_or_missing(self):
        rule = _rules()["L3-026"]
        assert run_det_rule(rule, {"bid.performance_groups": [{"group_id": "G1", "ok": True, "members": []}]}) == []
        assert run_det_rule(rule, {})[0]["verdict"] == "need_human"


class TestL2015EmptySection:
    """L2-015 章节正文空缺(整合版对齐 W5 层归位 L3→L2,原 EAI L3-020;bid.section_tree;major;is_empty=None 不判)。"""

    def test_empty_section_violation(self):
        rule = _rules()["L2-015"]
        fields = {
            "bid.section_tree": [
                {"code": "3", "title": "施工组织设计", "toc_page": 3, "body_page": 20, "is_empty": True, "offset": 17, "offset_flag": True},
                {"code": "4", "title": "质量管理", "toc_page": 30, "body_page": 40, "is_empty": False, "offset": 10, "offset_flag": True},
                {"code": "5", "title": "安全文明", "toc_page": 50, "body_page": None, "is_empty": None, "offset": None, "offset_flag": None},
            ]
        }
        issues = run_det_rule(rule, fields)
        assert len(issues) == 1, f"仅 is_empty=True 行成 issue: {issues}"
        assert issues[0]["verdict"] == "violation" and issues[0]["severity"] == "major"
        assert "施工组织设计" in issues[0]["message"]
        assert run_det_rule(rule, {})[0]["verdict"] == "need_human"


class TestGoldenFaceInsurance:
    """裁决⑤常驻锁:首段-only 基线上新四规则零 violation 全 need_human(golden 55 零翻红机理)。"""

    @pytest.mark.asyncio
    async def test_new_rules_need_human_on_legacy_baseline(self):
        pack = load_rulepack(PACK)
        model_fn = wrap_model_fn(lambda messages: SimpleNamespace(content=_QUIET))
        fields = {"bid.total_price": 100.0, "tender.max_price": 200.0, "bid.price_includes_tax": True, "tender.price_includes_tax": True}
        issues = await evaluate_fields(pack, fields, model_fn=model_fn)
        new = [i for i in issues if i["rule_id"] in NEW_IDS]
        assert len(new) == 4 and all(i["verdict"] == "need_human" for i in new), f"新规则旧基线必须 need_human: {new}"


class TestFamilyWiring:
    def test_universe_unchanged_and_consumption_wired(self):
        # 裁决⑤修正(实施中实锤):tender.required_fields 原不在宇宙(consumed_by 空结果≠在宇宙),
        # L2-041(原 EAI L2-022)inputs 声明使其首次入宇宙 77→78(by design,顺带修复 M3 必填口径从未抽取的潜在缺口);
        # P1-β批二续 2026-11-07 文件级 L2-001/002/003 六路径入宇宙 78→84(by design);
        # P1-β批二续 T2 2026-11-07 L2-004/050/051 三路径入宇宙 84→87(by design;bid.full_text 规格名全文域首入宇宙,plan 预算 86 偏差 +1)
        assert len(universe()) == 87
        for path in ("tender.required_fields", "bid.boq_rows", "bid.attachments", "bid.performance_groups", "bid.section_tree", "tender.file_composition", "bid.volume_index", "bid.archive_files", "bid.files", "bid.full_text"):
            assert consumed_by(path)["rules"], f"{path} 仍零规则消费"
        assert not consumed_by("bid.table_cells")["rules"]  # 临时契约挂账不动(裁决⑦)

    def test_real_pack_lint_clean(self):
        pack = load_rulepack(PACK)
        assert lint_rules(pack.rules) == []
