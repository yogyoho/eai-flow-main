"""End-to-end on the real sample pair. Skips unless the sample docx is present
(set FIRE_SAMPLE_DOCX env var or use the default path)."""
import os
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = Path(os.environ.get(
    "FIRE_SAMPLE_DOCX",
    r"D:/18 辽宁创元/03 项目策划/02 中石油/吉林院/报告智能体/模板资料-00/基地项目/基地项目-设计说明书.docx",
))
MAPPING = ROOT / "references" / "fire_spec_mapping.json"

pytestmark = pytest.mark.skipif(not SAMPLE.exists(), reason="sample design spec not present")


def test_sample_pipeline_meets_acceptance(tmp_path):
    struct_path = tmp_path / "struct.json"
    report_path = tmp_path / "report.md"
    # 1. parse
    subprocess.run([sys.executable, str(ROOT / "scripts" / "parse_spec.py"),
                    str(SAMPLE), str(struct_path)], check=True)
    structure = json.loads(struct_path.read_text(encoding="utf-8"))
    assert len(structure["paras"]) > 500, "expected a real design spec, not a stub"
    # 2. extract
    subprocess.run([sys.executable, str(ROOT / "scripts" / "extract.py"),
                    str(struct_path), str(MAPPING), str(report_path)], check=True)
    report = report_path.read_text(encoding="utf-8")
    # 3. acceptance: conflict field correct (§9.2 消防, not §9.1 给水)
    assert "30L/s" in report and "DN200" in report
    assert "生活用水量8L/s" not in report and "DN150" not in report
    # 4. acceptance: compute section not fabricated
    assert "[需计算]" in report
    # 5. grounding
    from scripts.grounding_check import check
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    res = check(report, structure, mapping)
    assert not res["missing_anchors"], f"unresolved anchors: {res['missing_anchors'][:5]}"
    assert res["rate"] >= 0.85, f"grounding rate {res['rate']:.2%} < 85%; failures: {res['failed_samples']}"
    # 6. regression: §8 must NOT dump the whole spec body. The original mapping
    #    used para_run "区域位置图"→"设备一览表"; "设备一览表" first appears deep
    #    in the body (¶847), so the run captured ~744 paragraphs and inflated the
    #    report to ~37k chars. "有线电视系统" (cable TV) is out of scope for a fire
    #    report — it only ever appeared via that §8 body leak.
    assert "有线电视系统" not in report, (
        "§8 over-copy regression: out-of-scope body content '有线电视系统' leaked in — "
        "check §8 para_run anchors don't overshoot into the spec body"
    )
    assert len(report) < 25000, (
        f"report suspiciously large ({len(report)} chars) — likely a para_run overshoot; "
        "was 37095 when §8 grabbed the whole spec"
    )
