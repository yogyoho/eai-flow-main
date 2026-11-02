"""金标准回归门(金标准 spec §7)+loader/runner/report 单测。题库=人工标注答案,
diff 即回归;快照式自动生成被 spec 明确否决(把 bug 固化成标准)。"""

from pathlib import Path

import pytest

from app.extensions.bid_review.golden import loader

PACK = str(Path(__file__).resolve().parent.parent / "app" / "extensions" / "bid_review" / "engine" / "rulepacks" / "bid-review-core" / "1.0.0.yaml")
CASES_DIR = Path(__file__).resolve().parent.parent / "app" / "extensions" / "bid_review" / "golden" / "cases"


def test_load_sample_case():
    c = loader.load_case(CASES_DIR / "L1-009-over-max-price.yaml")
    assert c.case == "L1-009-over-max-price"
    assert c.expect_issues[0].rule_id == "L1-009" and c.expect_issues[0].severity == "fatal"
    assert c.expect_issues[0].contains == ["1,000,001"]
    assert c.fields["bid.total_price"] == 1000001.0
    assert c.strict is False


def test_unknown_field_path_rejected(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text(
        "case: bad\ndesc: x\nfields:\n  tender.nonexistent.path: 1\nexpect_issues: []\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="未知字段路径"):
        loader.load_case(p)


@pytest.mark.parametrize("rid", ["L1-013", "L1-003"])  # sem 与 hybrid 两分支都钉(L1-003=hyb,已在 rulepack 确认)
def test_sem_expect_requires_model_script(tmp_path, rid):
    p = tmp_path / "bad2.yaml"
    p.write_text(
        f"case: bad2\ndesc: x\nfields: {{}}\nexpect_issues:\n- {{rule_id: {rid}, severity: major, contains: [x]}}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="model_script"):
        loader.load_case(p)


def test_expect_issues_unknown_rule_id_rejected(tmp_path):
    p = tmp_path / "bad3.yaml"
    p.write_text(
        "case: bad3\ndesc: x\nfields: {}\nexpect_issues:\n- {rule_id: L9-999, severity: fatal}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="expect_issues 引用不存在的规则"):
        loader.load_case(p)


def test_acceptable_rule_ids_unknown_rule_id_rejected(tmp_path):
    p = tmp_path / "bad4.yaml"
    p.write_text(
        "case: bad4\ndesc: x\nfields: {}\nexpect_issues:\n- {rule_id: L1-009, severity: fatal, acceptable_rule_ids: [NOPE-1]}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="acceptable_rule_ids 引用不存在的规则"):
        loader.load_case(p)


def test_expect_absent_unknown_rule_id_rejected(tmp_path):
    p = tmp_path / "bad5.yaml"
    p.write_text(
        "case: bad5\ndesc: x\nfields: {}\nexpect_issues: []\nexpect_absent: [BOGUS-1]\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="expect_absent 引用不存在的规则"):
        loader.load_case(p)


def test_non_mapping_yaml_rejected(tmp_path):
    p = tmp_path / "bad6.yaml"
    p.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(ValueError, match="映射"):
        loader.load_case(p)


def test_case_filename_must_match_case_id(tmp_path):
    p = tmp_path / "mismatch.yaml"
    # 夹具必须正则合法、仅与文件名不一致:否则删掉 case != stem 判定的变异照样绿,测试无杀伤力
    p.write_text("case: L1-009-other-name\ndesc: x\nfields: {}\nexpect_issues: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="case 与文件名"):
        loader.load_case(p)


def test_case_name_must_match_canonical_regex(tmp_path):
    p = tmp_path / "lowercase-slug.yaml"  # stem 与 case 恰好一致:只有 _NAME_RE 能拦,单独钉正则分支
    p.write_text("case: lowercase-slug\ndesc: x\nfields: {}\nexpect_issues: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="命名非法"):
        loader.load_case(p)
