"""规则包注册表测试(spec 2026-11-05 R1 §2.6):宇宙锚定/反查/lint/拒载/投影声明。"""

import pytest
import yaml

from app.extensions.bid_review.engine import registry
from app.extensions.bid_review.engine.anchors import ANCHOR_REGISTRY, anchor_rule_paths
from app.extensions.bid_review.engine.extract import (
    FIELD_TYPE_CONTRACTS,
    LIST_PATHS,
    OCCURRENCE_PATHS,
    SERVER_DERIVED_PATHS,
    collect_field_paths,
)
from app.extensions.bid_review.engine.labels import FIELD_LABELS
from app.extensions.bid_review.engine.rule_runner import RulePackError, load_rulepack

# 宇宙(2026-11-05 R1 取证 71 路径 + M1 实体段 bid.attachments + M2 章节段 bid.section_tree + M3 表格段
# bid.boq_rows/bid.table_cells + M4 业绩聚类 bid.performance_entries/bid.performance_groups = 77
# + R2+ 规则族 L2-041 inputs 声明 tender.required_fields = 78
# + P1-β批二续 文件级 L2-001/002/003 六路径 = 84
# + P1-β批二续 T2 文件级完好性 L2-004/050/051 三路径(archive_files/files/full_text;full_text 规格名全文域首入宇宙,plan 预算 86 偏差 +1)= 87
# + P1-β批二续 T3 要件级 L2-030/032/033 五路径(signature_slots×2+三 presence 派生布尔;T2 实测 bid.full_text
#   入宇宙后基线 87,plan 预算 91 系 86 旧基线,勘误 87+5=92)= 92
# + P1-β批六 T1-T5 tender/bid 字段实补 13 路径(tender 8+bid 4 模型抽取契约经 T3 五规则+T4 L1-003/L1-006 inputs
#   入宇宙;bid.tables 表格骨架服务端派生经 L2-040 inputs)= 105——逐位锁定。
# + P1-β批七 §6.1 ❌4 消费面 21 路径(L1-004 hyb 6+L1-020 sem 3+L1-022 op:and 合规式 10+L1-026 det 1+L1-007 富化 1
#   五规则 inputs 声明入包,T2 四规则+T3 富化兑付;A-β7-② 修订:容器契约→21 叶平键)= 126——逐位锁定。
# 首段 prompt 路径 = EXPECTED_UNIVERSE − SECOND_STAGE_FIELDS − SERVER_DERIVED_PATHS = 114(126−6−6;批七 21 路径全模型首段契约;前值 93=105−6−6)。
EXPECTED_UNIVERSE = [
    "bid.alternative_price_offers",
    "bid.amount_occurrences",
    "bid.appendix_references",
    "bid.archive_files",  # P1-β批二续 T2 L2-004 压缩包内文件(2026-11-07)
    "bid.attachment_index",
    "bid.attachments",
    "bid.authorization_letter_present",
    "bid.authorization_signatory",
    "bid.bid_letter_date",
    "bid.bid_letter_signatory",
    "bid.boq_items",
    "bid.boq_rows",
    "bid.boq_unit_checks",
    "bid.commitment_completion_date",
    "bid.commitment_letter_date",
    "bid.consortium",  # P1-β批六 T1 联合体协议书实体(L1-017 inputs,2026-11-08)
    "bid.currency_occurrences",
    "bid.declaration_letter_codes",
    "bid.deposit_amount",
    "bid.deposit_forms",  # P1-β批六 T1 保证金实际缴纳形式(L1-006 inputs,2026-11-08)
    "bid.deposit_receipt_present",  # P1-β批二续 T3 L2-033 保证金凭证存在性(服务端派生,2026-11-07)
    "bid.detail_rows",
    "bid.device_model_mismatches",
    "bid.device_models",
    "bid.document_version",
    "bid.duration_commitment_letter",
    "bid.duration_main_text",
    "bid.duration_schedule",
    "bid.electronic_files",  # P1-β批二续 L2-003 电子标书文件(2026-11-07)
    "bid.entity.business_scope",
    "bid.entity.license_name",
    "bid.entity.license_valid_until",
    "bid.entity.name_in_bid_letter",
    "bid.entity_name_occurrences",
    "bid.figures",  # P1-β批六 T1 图纸/图表清单(L2-012 inputs,2026-11-08)
    "bid.file_index",  # P1-β批二续 L2-001 投标文件索引(2026-11-07)
    "bid.files",  # P1-β批二续 T2 L2-050 全量文件(2026-11-07)
    "bid.format.copies",  # P1-β批七 投标文件份数实际(L1-022 inputs,2026-11-08)
    "bid.format.font",  # P1-β批七 投标文件字体实际(L1-022 inputs,2026-11-08)
    "bid.format.page_numbering",  # P1-β批七 投标文件页码实际(L1-022 inputs,2026-11-08)
    "bid.format.sealing_label",  # P1-β批七 密封标识实际(L1-022 inputs,2026-11-08)
    "bid.format.toc",  # P1-β批七 投标文件目录实际(L1-022 inputs,2026-11-08)
    "bid.full_text",  # P1-β批二续 T2 L2-051 规格名全文域,入 SERVER_DERIVED_PATHS 禁模型抽取(2026-11-07)
    "bid.header_footer.project_name",
    "bid.id_copy_present",  # P1-β批二续 T3 L2-032 身份证复印件存在性(服务端派生,2026-11-07)
    "bid.is_consortium",  # P1-β批六 T1 联合体投标布尔(L1-017 inputs,2026-11-08)
    "bid.legal_id_proof_present",  # P1-β批二续 T3 L2-032 法人身份证明存在性(服务端派生,2026-11-07)
    "bid.missing_signature_pages",
    "bid.old_project_mentions",
    "bid.performance_entries",
    "bid.performance_groups",
    "bid.personnel_commercial",
    "bid.personnel_technical",
    "bid.pm.certs",  # P1-β批七 拟任项目负责人持证(L1-004 inputs,2026-11-08)
    "bid.pm.on_other_project",  # P1-β批七 拟任项目负责人在建任职(L1-004 inputs,2026-11-08)
    "bid.pm.social_months",  # P1-β批七 拟任项目负责人社保月数(L1-004 inputs,2026-11-08)
    "bid.price_includes_tax",
    "bid.qual_levels",
    "bid.schedule_end_date",
    "bid.schedule_start_date",
    "bid.section_tree",
    "bid.service_commitments",  # P1-β批七 分包相关服务承诺(L1-020 inputs,2026-11-08)
    "bid.signature_slots",  # P1-β批二续 T3 L2-030 投标实际签署位(2026-11-07)
    "bid.similar_performances",
    "bid.submit_time",  # P1-β批七 投标文件递交时间(L1-026 inputs,2026-11-08)
    "bid.subtotal",
    "bid.table_cells",
    "bid.tables",  # P1-β批六 T2 表格骨架(服务端派生,L2-040 inputs,2026-11-08)
    "bid.tax_rate_occurrences",
    "bid.tenderee_name_mentions",
    "bid.toc_section_codes",
    "bid.total_price",
    "bid.total_price_words",
    "bid.validity_days",
    "bid.version_tag_occurrences",
    "bid.volume_index",  # P1-β批二续 L2-002 投标分册索引(2026-11-07)
    "bid.warranty_period",
    "deviation.items",
    "project.entity_whitelist.names",
    "tender.attachment_requirements",
    "tender.bid_deadline",
    "tender.bid_scope",
    "tender.boq_items",
    "tender.commitment_sections",  # P1-β批六 T1 承诺类章节要求(L2-013 inputs,2026-11-08)
    "tender.consortium_allowed",  # P1-β批六 T1 联合体允许布尔(L1-017 inputs,2026-11-08)
    "tender.currency",
    "tender.deposit_forms",  # P1-β批六 T1 保证金缴纳形式要求(L1-006 inputs,2026-11-08)
    "tender.deposit_required",
    "tender.device_models",
    "tender.electronic_files",  # P1-β批二续 L2-003 电子标书要求(2026-11-07)
    "tender.file_composition",  # P1-β批二续 L2-001 投标文件组成要求(2026-11-07)
    "tender.format_requirements.copies",  # P1-β批七 招标格式要求份数(L1-022 inputs,2026-11-08)
    "tender.format_requirements.font",  # P1-β批七 招标格式要求字体(L1-022 inputs,2026-11-08)
    "tender.format_requirements.page_numbering",  # P1-β批七 招标格式要求页码(L1-022 inputs,2026-11-08)
    "tender.format_requirements.sealing",  # P1-β批七 招标格式要求密封(L1-022 inputs,2026-11-08)
    "tender.format_requirements.toc",  # P1-β批七 招标格式要求目录(L1-022 inputs,2026-11-08)
    "tender.max_duration",
    "tender.max_price",
    "tender.min_performance_amount",  # P1-β批六 T4 L1-003 inputs 富化(2026-11-08)
    "tender.min_similar_performance_count",
    "tender.min_warranty_period",
    "tender.performance_window_months",  # P1-β批六 T4 L1-003 inputs 富化(2026-11-08)
    "tender.pm_req.certs",  # P1-β批七 项目负责人资格要求持证(L1-004 inputs,2026-11-08)
    "tender.pm_req.exclusive",  # P1-β批七 项目负责人专职要求(L1-004 inputs,2026-11-08)
    "tender.pm_req.social_months",  # P1-β批七 项目负责人社保月数要求(L1-004 inputs,2026-11-08)
    "tender.price_includes_tax",
    "tender.project_identity.code",
    "tender.project_identity.lot_section",
    "tender.project_identity.name",
    "tender.required_declarations",
    "tender.required_fields",  # R2+ L2-041 必填清单行未报价(plan 2026-11-05 规则族补齐)
    "tender.required_figures",  # P1-β批六 T1 招标要求附图/图表(L2-014 inputs,2026-11-08)
    "tender.required_qual_level",
    "tender.required_sections",
    "tender.required_signatures",  # P1-β批七 招标签章要求清单(L1-007 富化 inputs,2026-11-08)
    "tender.required_tables",  # P1-β批六 T1 必备表格要求(L2-040 inputs,2026-11-08)
    "tender.required_validity_days",
    "tender.scoring_items",
    "tender.signature_slots",  # P1-β批二续 T3 L2-030 招标要求签署位(2026-11-07)
    "tender.subcontract_limit.allowed",  # P1-β批七 分包允许布尔(L1-020 inputs,2026-11-08)
    "tender.subcontract_limit.scope",  # P1-β批七 分包允许范围(L1-020 inputs,2026-11-08)
    "tender.substantive_clauses",
    "tender.tax_rate",
    "tender.tech_sections_required",  # P1-β批六 T1 技术方案必备章节(L2-012 inputs,2026-11-08)
    "tender.tenderee_name",
    "tender.volume_specs",  # P1-β批二续 L2-002 招标份数要求(2026-11-07)
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
    def test_anchored_126(self):
        # 105→126(P1-β批七 §6.1 ❌4 消费面:21 叶平键经 L1-004/L1-020/L1-022/L1-026 inputs+L1-007 富化,2026-11-08;前值 92→105 系批六 T1-T5)
        assert len(EXPECTED_UNIVERSE) == 126
        assert registry.universe() == EXPECTED_UNIVERSE

    def test_second_stage_fields(self):
        # M1(spec §4)+ M2(spec §5)+ M3(spec §5)+ M4(spec §5):第二段字段域——进 universe(契约一致性域)但剔除出首段 prompt
        assert set(registry.SECOND_STAGE_FIELDS) == {"bid.attachments", "bid.section_tree", "bid.boq_rows", "bid.table_cells", "bid.performance_entries", "bid.performance_groups"}

    def test_collect_field_paths_excludes_second_stage(self):
        # 首段 prompt 71 路径逐位=R2+ 后 72−device_model_mismatches 服务端派生(M0 快照锚点随宇宙扩容)
        assert collect_field_paths() == [p for p in EXPECTED_UNIVERSE if p not in registry.SECOND_STAGE_FIELDS and p not in SERVER_DERIVED_PATHS]
        assert "bid.device_model_mismatches" not in collect_field_paths()  # 服务端派生(禁模型换算 P0③)
        assert "bid.attachments" not in collect_field_paths()
        assert "bid.section_tree" not in collect_field_paths()
        assert "bid.boq_rows" not in collect_field_paths()
        assert "bid.table_cells" not in collect_field_paths()
        assert "bid.performance_entries" not in collect_field_paths()
        assert "bid.performance_groups" not in collect_field_paths()

    def test_first_stage_equals_universe_minus_second_stage(self):
        assert set(collect_field_paths()) == set(registry.universe()) - set(registry.SECOND_STAGE_FIELDS) - set(SERVER_DERIVED_PATHS)


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


class TestSeverityOverride:
    """EAI-CUSTOM 批十T1(A-β10-②③,2026-11-09):severity_override 卡级注记载入门。
    四拒载钉(spec 缺失/域外/等值/reason 空)+非 dict 形态钉(校验四条全钉满)+一正钉
    (注记入 dataclass 审计面、生效 severity 仍=卡字段零行为)+真包零噪声回归钉。
    已知偏离集反向钉({L2-041} ⊆ 带注记卡)属 T2 controller 直办随 L2-041 注记同 commit 落,
    本批不落(A-β10-③,保每 commit 全绿)。"""

    def _write(self, tmp_path, rule):
        p = tmp_path / "pack.yaml"
        p.write_text(yaml.safe_dump({"rules": [rule]}, allow_unicode=True), encoding="utf-8")
        return p

    def test_missing_spec_rejected(self, tmp_path):
        rule = _synthetic_rule("L2-995", "L2", "fatal")
        rule["severity_override"] = {"reason": "EAI 上调"}
        with pytest.raises(RulePackError, match="L2-995"):
            load_rulepack(self._write(tmp_path, rule))

    def test_spec_out_of_domain_rejected(self, tmp_path):
        rule = _synthetic_rule("L2-994", "L2", "fatal")
        rule["severity_override"] = {"spec": "majors", "reason": "EAI 上调"}
        with pytest.raises(RulePackError, match="L2-994"):
            load_rulepack(self._write(tmp_path, rule))

    def test_spec_equals_severity_rejected(self, tmp_path):
        rule = _synthetic_rule("L2-993", "L2", "fatal")
        rule["severity_override"] = {"spec": "fatal", "reason": "EAI 上调"}
        with pytest.raises(RulePackError, match="L2-993"):
            load_rulepack(self._write(tmp_path, rule))

    def test_reason_blank_rejected(self, tmp_path):
        rule = _synthetic_rule("L2-992", "L2", "fatal")
        rule["severity_override"] = {"spec": "major", "reason": "   "}
        with pytest.raises(RulePackError, match="L2-992"):
            load_rulepack(self._write(tmp_path, rule))

    def test_non_dict_rejected(self, tmp_path):
        rule = _synthetic_rule("L2-991", "L2", "fatal")
        rule["severity_override"] = "major"
        with pytest.raises(RulePackError, match="L2-991"):
            load_rulepack(self._write(tmp_path, rule))

    def test_valid_override_loaded(self, tmp_path):
        # 正钉(A-β10-②):合法注记进 dataclass;生效 severity 仍=卡 severity 字段(裁决① 零行为)
        rule = _synthetic_rule("L2-990", "L2", "fatal")
        rule["severity_override"] = {"spec": "major", "reason": "EAI 上调:必填清单行缺价属实质性不响应,与 L1-011 漏项同档"}
        pack = load_rulepack(self._write(tmp_path, rule))
        loaded = pack.rules[0]
        assert loaded.id == "L2-990"
        assert loaded.severity == "fatal"
        assert loaded.severity_override == {"spec": "major", "reason": "EAI 上调:必填清单行缺价属实质性不响应,与 L1-011 漏项同档"}

    def test_real_pack_zero_noise(self):
        # 真包回归(A-β10-① 范围锁):T1 时点真包零卡带注记 → 全 None,加载零异常零噪声
        pack = load_rulepack(registry.RULEPACK_DIR / "1.0.0.yaml")
        assert pack.rules
        assert all(r.severity_override is None for r in pack.rules)


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

    def test_labels_subset_universe(self):
        # 批八(A-β8-④,2026-11-08):labels 必须是 universe 子集——批六起新路径漏挂
        # labels 的扫尾债即此因,钉死后新 inputs 入包即红,不再欠账。
        assert set(FIELD_LABELS) <= set(registry.universe())
