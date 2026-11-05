"""规则包注册表测试(spec 2026-11-05 R1 §2.6):宇宙锚定/反查/lint/拒载/投影声明。"""

import pytest
import yaml

from app.extensions.bid_review.engine import registry
from app.extensions.bid_review.engine.anchors import ANCHOR_REGISTRY, anchor_rule_paths
from app.extensions.bid_review.engine.extract import (
    FIELD_TYPE_CONTRACTS,
    LIST_PATHS,
    OCCURRENCE_PATHS,
    collect_field_paths,
)
from app.extensions.bid_review.engine.rule_runner import RulePackError, load_rulepack

# 宇宙(2026-11-05 R1 取证 71 路径 + M1 实体段 bid.attachments + M2 章节段 bid.section_tree = 73)——逐位锁定。
# 首段 prompt 路径 = EXPECTED_UNIVERSE − SECOND_STAGE_FIELDS = 71,与 R1 改造前逐位相等(M0 零翻红锚点)。
EXPECTED_UNIVERSE = [
    "bid.alternative_price_offers",
    "bid.amount_occurrences",
    "bid.appendix_references",
    "bid.attachment_index",
    "bid.attachments",
    "bid.authorization_letter_present",
    "bid.authorization_signatory",
    "bid.bid_letter_date",
    "bid.bid_letter_signatory",
    "bid.boq_items",
    "bid.boq_unit_checks",
    "bid.commitment_completion_date",
    "bid.commitment_letter_date",
    "bid.currency_occurrences",
    "bid.declaration_letter_codes",
    "bid.deposit_amount",
    "bid.detail_rows",
    "bid.device_model_mismatches",
    "bid.device_models",
    "bid.document_version",
    "bid.duration_commitment_letter",
    "bid.duration_main_text",
    "bid.duration_schedule",
    "bid.entity.business_scope",
    "bid.entity.license_name",
    "bid.entity.license_valid_until",
    "bid.entity.name_in_bid_letter",
    "bid.entity_name_occurrences",
    "bid.header_footer.project_name",
    "bid.missing_signature_pages",
    "bid.old_project_mentions",
    "bid.personnel_commercial",
    "bid.personnel_technical",
    "bid.price_includes_tax",
    "bid.qual_levels",
    "bid.schedule_end_date",
    "bid.schedule_start_date",
    "bid.section_tree",
    "bid.similar_performances",
    "bid.subtotal",
    "bid.tax_rate_occurrences",
    "bid.tenderee_name_mentions",
    "bid.toc_section_codes",
    "bid.total_price",
    "bid.total_price_words",
    "bid.validity_days",
    "bid.version_tag_occurrences",
    "bid.warranty_period",
    "deviation.items",
    "project.entity_whitelist.names",
    "tender.attachment_requirements",
    "tender.bid_deadline",
    "tender.bid_scope",
    "tender.boq_items",
    "tender.currency",
    "tender.deposit_required",
    "tender.device_models",
    "tender.max_duration",
    "tender.max_price",
    "tender.min_similar_performance_count",
    "tender.min_warranty_period",
    "tender.price_includes_tax",
    "tender.project_identity.code",
    "tender.project_identity.lot_section",
    "tender.project_identity.name",
    "tender.required_declarations",
    "tender.required_qual_level",
    "tender.required_sections",
    "tender.required_validity_days",
    "tender.scoring_items",
    "tender.substantive_clauses",
    "tender.tax_rate",
    "tender.tenderee_name",
]


def _rule(**kw):
    """duck-typed Rule 替身(registry 不 import rule_runner 防环)。"""
    from types import SimpleNamespace

    base = {"id": "X-999", "layer": "L1", "severity": "fatal", "evidence": [], "inputs": ["bid.total_price"]}
    base.update(kw)
    return SimpleNamespace(**base)


def _synthetic_rule(rid: str, layer: str, severity: str) -> dict:
    """可过既有语法校验的最小合成规则(op/lte 形态照抄 L1-009)。"""
    return {
        "id": rid,
        "name": "合成规则",
        "layer": layer,
        "type": "deterministic",
        "inputs": ["bid.total_price"],
        "check": {"op": "lte", "left": "bid.total_price", "right": "tender.max_price"},
        "severity": severity,
        "message_tpl": "x",
        "fix_tpl": "y",
    }


class TestUniverse:
    def test_anchored_73(self):
        assert len(EXPECTED_UNIVERSE) == 73
        assert registry.universe() == EXPECTED_UNIVERSE

    def test_second_stage_fields(self):
        # M1(spec §4)+ M2(spec §5):第二段字段域——进 universe(契约一致性域)但剔除出首段 prompt
        assert set(registry.SECOND_STAGE_FIELDS) == {"bid.attachments", "bid.section_tree"}

    def test_collect_field_paths_excludes_second_stage(self):
        # 首段 prompt 71 路径逐位=R1 改造前(M0 快照零翻红锚点)
        assert collect_field_paths() == [p for p in EXPECTED_UNIVERSE if p not in registry.SECOND_STAGE_FIELDS]
        assert "bid.attachments" not in collect_field_paths()
        assert "bid.section_tree" not in collect_field_paths()

    def test_first_stage_equals_universe_minus_second_stage(self):
        assert set(collect_field_paths()) == set(registry.universe()) - set(registry.SECOND_STAGE_FIELDS)


class TestConsumedBy:
    def test_total_price(self):
        info = registry.consumed_by("bid.total_price")
        assert "L1-009" in info["rules"]
        assert {"A-PRICE-SHEET", "A-BID-LETTER"} <= set(info["anchors"])
        assert info["projections"] == []

    def test_projection_field(self):
        info = registry.consumed_by("deviation.items")
        assert info["projections"] == ["B9 偏离表投影(routers.py)"]

    def test_unknown_field(self):
        assert registry.consumed_by("nope.nothing") == {"rules": [], "anchors": [], "projections": []}


class TestAbiBIDDocRegression:
    def test_registered(self):
        assert "A-BID-DOC" in ANCHOR_REGISTRY

    def test_l2_021_evidence_resolves(self):
        # bug-3985 回归:此前未注册,anchor_rule_paths 静默返回 [] = 证据区悄悄丢
        assert anchor_rule_paths(["A-BID-DOC"], []) == ["tender.attachment_requirements", "bid.attachment_index"]


class TestLint:
    def test_real_pack_clean(self):
        pack = load_rulepack(registry.RULEPACK_DIR / "1.0.0.yaml")
        assert registry.lint_rules(pack.rules) == []

    def test_unknown_anchor(self):
        assert any("A-NOPE" in p for p in registry.lint_rules([_rule(evidence=["A-NOPE"])]))

    def test_severity_out_of_layer_whitelist(self):
        assert any("minor" in p for p in registry.lint_rules([_rule(severity="minor")]))
        assert any("fatal" in p for p in registry.lint_rules([_rule(layer="L3", severity="fatal")]))

    def test_unknown_layer(self):
        assert registry.lint_rules([_rule(layer="L9")])

    def test_bad_input(self):
        assert registry.lint_rules([_rule(inputs=["nodot"])])


class TestLoadRejection:
    def _write(self, tmp_path, rule):
        p = tmp_path / "pack.yaml"
        p.write_text(yaml.safe_dump({"rules": [rule]}, allow_unicode=True), encoding="utf-8")
        return p

    def test_unknown_anchor_rejected(self, tmp_path):
        rule = _synthetic_rule("L1-998", "L1", "fatal")
        rule["evidence"] = ["A-NOPE"]
        with pytest.raises(RulePackError, match="A-NOPE"):
            load_rulepack(self._write(tmp_path, rule))

    def test_severity_rejected(self, tmp_path):
        with pytest.raises(RulePackError, match="白名单"):
            load_rulepack(self._write(tmp_path, _synthetic_rule("L3-998", "L3", "fatal")))

    def test_bad_input_rejected(self, tmp_path):
        rule = _synthetic_rule("L1-997", "L1", "fatal")
        rule["inputs"] = ["nodot"]
        with pytest.raises(RulePackError, match="非点路径"):
            load_rulepack(self._write(tmp_path, rule))


class TestCrossSourceSubset:
    def test_contracts_subset_universe(self):
        assert set(FIELD_TYPE_CONTRACTS) <= set(registry.universe())

    def test_shape_sets_subset_universe(self):
        assert (set(OCCURRENCE_PATHS) | set(LIST_PATHS)) <= set(registry.universe())

    def test_projection_fields_declared(self):
        assert set(registry.PROJECTION_FIELDS) == {
            "deviation.items",
            "tender.scoring_items",
            "tender.project_identity.lot_section",
        }
