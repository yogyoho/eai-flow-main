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
    assert c.strict is False


def test_unknown_field_path_rejected(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text(
        "case: bad\ndesc: x\nfields:\n  tender.nonexistent.path: 1\nexpect_issues: []\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="未知字段路径"):
        loader.load_case(p)


def test_sem_expect_requires_model_script(tmp_path):
    p = tmp_path / "bad2.yaml"
    p.write_text(
        "case: bad2\ndesc: x\nfields: {}\nexpect_issues:\n- {rule_id: L1-013, severity: major, contains: [x]}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="model_script"):
        loader.load_case(p)


def test_case_filename_must_match_case_id(tmp_path):
    p = tmp_path / "mismatch.yaml"
    p.write_text("case: other-name\ndesc: x\nfields: {}\nexpect_issues: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="case 与文件名"):
        loader.load_case(p)
