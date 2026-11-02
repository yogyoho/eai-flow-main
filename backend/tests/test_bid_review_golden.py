"""金标准回归门(金标准 spec §7)+loader/runner/report 单测。题库=人工标注答案,
diff 即回归;快照式自动生成被 spec 明确否决(把 bug 固化成标准)。"""

from pathlib import Path

import pytest

from app.extensions.bid_review.engine.rule_runner import load_rulepack
from app.extensions.bid_review.golden import loader
from app.extensions.bid_review.golden.runner import run_case
from app.extensions.bid_review.golden.schema import Expectation, GoldenCase

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


# ── T3 golden runner:diff 引擎(verdict 分桶消化/expect_absent/strict/checklist;spec §6/§7)──

_SAMPLE = CASES_DIR / "L1-009-over-max-price.yaml"


def _pack():
    return load_rulepack(PACK)


@pytest.mark.asyncio
async def test_sample_case_passes():
    res = await run_case(loader.load_case(_SAMPLE), pack=_pack())
    assert res.ok, res.diff_lines
    assert res.diff_lines == []
    assert res.hits.get("L1-009") == 1


@pytest.mark.asyncio
async def test_missing_expectation_detected():
    c = loader.load_case(_SAMPLE)
    c.expect_issues[0].contains = ["不存在的关键词XYZ"]  # 载后突变免走 loader(loader 只在加载期校验)
    res = await run_case(c, pack=_pack())
    assert not res.ok
    joined = "\n".join(res.diff_lines)
    assert "L1-009" in joined and "未命中" in joined


@pytest.mark.asyncio
async def test_strict_flags_unexpected_violation_but_tolerates_need_human():
    pack = _pack()
    c = loader.load_case(_SAMPLE)
    c.strict = True
    ok_res = await run_case(c, pack=pack)
    assert ok_res.ok, ok_res.diff_lines  # need_human 全数容忍;L1-009 violation 已被期望消化不数期望外
    # L1-014 inputs=[bid.duration_main_text, tender.max_duration]:两输入齐备才避开 need_human 降级(999>100 → lte 违例)
    c.fields["bid.duration_main_text"] = 999
    c.fields["tender.max_duration"] = 100
    res = await run_case(c, pack=pack)
    assert not res.ok
    assert any("期望外" in ln and "L1-014" in ln for ln in res.diff_lines)


@pytest.mark.asyncio
async def test_expect_absent_and_severity_mismatch():
    pack = _pack()
    c = loader.load_case(_SAMPLE)
    c.expect_absent = ["L1-009"]  # 必然违例的规则放抑制名单 → absent 断言必报(非空转)
    res = await run_case(c, pack=pack)
    assert not res.ok
    joined = "\n".join(res.diff_lines)
    assert "L1-009" in joined and "不应报" in joined
    fresh = loader.load_case(_SAMPLE)
    fresh.expect_issues[0].severity = "minor"  # 实际 fatal → severity 不符单列
    res2 = await run_case(fresh, pack=pack)
    assert not res2.ok
    assert "severity" in "\n".join(res2.diff_lines)


@pytest.mark.asyncio
async def test_acceptable_rule_ids_any_hit_counts():
    c = GoldenCase(  # 直构绕过 loader:免文件名/命名校验,专测记账语义
        case="T5-alias-credit",
        desc="acceptable_rule_ids 等价规则集:实报 L1-009 记账到主 id L2-024",
        fields={
            "bid.total_price": 1000001.0,
            "tender.max_price": 1000000.0,
            "bid.price_includes_tax": True,
            "tender.price_includes_tax": True,
        },
        expect_issues=[Expectation(rule_id="L2-024", severity="fatal", contains=["1,000,001"], acceptable_rule_ids=["L1-009"])],
        expect_absent=[],
    )
    res = await run_case(c, pack=_pack())
    assert res.ok, res.diff_lines
    assert res.hits.get("L2-024") == 1


_L2_FIELDS = {
    "tender.attachment_requirements": [
        {"no": "E-1", "name": "营业执照副本", "mandatory": True},
        {"no": "E-2", "name": "财务报表", "mandatory": True},
    ],
    "bid.attachment_index": [{"no": "E-1", "name": "营业执照副本"}],
}


@pytest.mark.asyncio
async def test_entity_disambiguation_filters_per_entity_issues():
    pack = _pack()
    e2 = GoldenCase(
        case="T6-entity-hit",
        desc="entity 子串消歧:E-2 缺失断言命中 E-2 实体(entity_keys=attachment:E-2)",
        fields=dict(_L2_FIELDS),
        expect_issues=[Expectation(rule_id="L2-020", severity="fatal", entity="E-2")],
        expect_absent=[],
    )
    assert (await run_case(e2, pack=pack)).ok
    e9 = GoldenCase(
        case="T6-entity-miss",
        desc="entity 子串消歧:期望 E-9 无对应实体 → 必未命中(逐实体过滤生效)",
        fields=dict(_L2_FIELDS),
        expect_issues=[Expectation(rule_id="L2-020", severity="fatal", entity="E-9")],
        expect_absent=[],
    )
    res = await run_case(e9, pack=pack)
    assert not res.ok
