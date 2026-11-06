"""金标准回归门(金标准 spec §7)+loader/runner/report 单测。题库=人工标注答案,
diff 即回归;快照式自动生成被 spec 明确否决(把 bug 固化成标准)。"""

import json
from pathlib import Path

import pytest

from app.extensions.bid_review.engine.rule_runner import load_rulepack
from app.extensions.bid_review.golden import loader
from app.extensions.bid_review.golden.report import build_report, render_markdown
from app.extensions.bid_review.golden.runner import _QUIET, _fields_from_stub, _scripted_model, run_case, run_smoke_dir
from app.extensions.bid_review.golden.schema import ChecklistExpect, Expectation, GoldenCase

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


def test_loader_rejects_non_str_nested_keys(tmp_path):
    """bug-3938 类守卫(T6 挂账):裸 `no` 嵌套键被 PyYAML 解析为布尔 False,
    materials_hash 的 json.dumps(sort_keys=True) 对 str/bool 键会 TypeError——加载期即拒,
    报错点名字段路径+加引号修法。"""
    p = tmp_path / "bad7.yaml"
    p.write_text(
        "case: L2-020-guard\ndesc: x\n"
        "fields:\n"
        "  tender.attachment_requirements:\n"
        "    - {no: E-1, name: 业绩合同}\n"  # 键 no 裸写 → False
        "expect_issues: []\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="tender.attachment_requirements.*非字符串.*加引号"):
        loader.load_case(p)


def test_loader_accepts_quoted_no_keys(tmp_path):
    """守卫不误伤:加引号的 'no' 键(题库既定写法)照常加载。"""
    p = tmp_path / "L2-020-ok-no.yaml"  # 正例须全 loader 校验通过:命名也须合法(stem==case)
    p.write_text(
        "case: L2-020-ok-no\ndesc: x\nfields:\n  tender.attachment_requirements:\n    - {'no': E-1, name: 业绩合同}\nexpect_issues: []\n",
        encoding="utf-8",
    )
    c = loader.load_case(p)
    assert c.fields["tender.attachment_requirements"][0]["no"] == "E-1"


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
    assert any("entity" in ln for ln in res.diff_lines)  # F2:仅 entity 不符须单列,不得误报「关键词未命中」


@pytest.mark.asyncio
async def test_duplicate_expectation_requires_distinct_issue():
    c = loader.load_case(_SAMPLE)
    c.expect_issues.append(Expectation(rule_id="L1-009", severity="fatal", contains=["1,000,001"]))  # 同特征期望×2,引擎只出一条
    res = await run_case(c, pack=_pack())
    assert not res.ok
    assert res.hits.get("L1-009") == 1  # 第二个期望不得重复记账同一实例(hits 不自增=正确)
    assert any("命中数不足" in ln for ln in res.diff_lines)


@pytest.mark.asyncio
async def test_verdict_mismatch_tier_state_mismatch():
    c = loader.load_case(_SAMPLE)
    c.expect_issues[0].verdict = "need_human"  # 实际 violation:severity+contains 全对,仅态判错
    res = await run_case(c, pack=_pack())
    assert not res.ok
    assert any("verdict 不符" in ln for ln in res.diff_lines)


@pytest.mark.asyncio
async def test_checklist_expectation_flat_rows():
    pack = _pack()

    def _cl_case(status_by_no, unknown_count=0):
        return GoldenCase(
            case="T8-checklist",
            desc="checklist 期望对平铺 items 行(no 键直取;非嵌套 req.no,flat-row 契约钉死)",
            fields=dict(_L2_FIELDS),
            expect_issues=[],
            expect_absent=[],
            checklist=ChecklistExpect(unknown_count=unknown_count, status_by_no=status_by_no),
        )

    ok_res = await run_case(_cl_case({"E-1": "MATCHED"}), pack=pack)
    assert ok_res.ok and ok_res.checklist_diff == []
    bad = await run_case(_cl_case({"E-2": "MATCHED"}), pack=pack)  # E-2 实际 MISSING
    assert not bad.ok and any("E-2" in ln for ln in bad.diff_lines)
    unk = await run_case(_cl_case({}, unknown_count=1), pack=pack)  # 实际 counts.unknown=0
    assert not unk.ok and any("counts.unknown" in ln for ln in unk.diff_lines)


def test_scripted_model_routes_by_rule_card_header():
    m = _scripted_model(  # F6:钉住跨文件耦合——llm_runner.build_rule_card 卡头「规则:<id>」格式
        GoldenCase(
            case="T7-script-route",
            desc="scripted model_fn 按规则卡「规则:<id>」路由,未命中表走安静应答",
            fields={},
            expect_issues=[],
            expect_absent=[],
            model_script={"L1-013": "x"},
        )
    )
    assert m([{"role": "user", "content": "规则:L1-013 质保期"}]) == "x"
    assert m([{"role": "user", "content": "规则:L9-999 其他规则卡"}]) == _QUIET


# ---- 回归门:逐题参数化 + 覆盖率地板 ----
# 批C 起覆盖率翻全集(L1 17 + L2 6 + L3 17 = pack 40 条精确相等;整合版编号对齐 2026-11-06:
# W1~W5 迁移 021指纹→023/023空白→022/022必填报价→041/019聚类→026/020章节空缺→L2-015 层归位;
# P1-β批一 +L3-019 行乘算 2026-11-06)
EXPECTED_COVERAGE = {
    "L1-001",
    "L1-002",
    "L1-003",
    "L1-005",
    "L1-006",
    "L1-007",
    "L1-008",
    "L1-009",
    "L1-010",
    "L1-011",
    "L1-012",
    "L1-013",
    "L1-014",
    "L1-015",
    "L1-016",
    "L1-019",
    "L1-021",
    "L2-020",
    "L2-022",
    "L2-023",
    "L2-024",
    "L2-041",
    "L3-001",
    "L3-002",
    "L3-003",
    "L3-004",
    "L3-005",
    "L3-006",
    "L3-007",
    "L3-008",
    "L3-009",
    "L3-010",
    "L3-012",
    "L3-013",
    "L3-014",
    "L3-016",
    "L3-018",
    "L3-019",
    "L3-026",
    "L2-015",
}


@pytest.mark.parametrize("path", sorted(CASES_DIR.glob("*.yaml")), ids=lambda p: p.stem)
@pytest.mark.asyncio
async def test_golden_case(path):
    pack = load_rulepack(PACK)
    res = await run_case(loader.load_case(path, pack), pack)
    assert res.ok, "\n".join(res.diff_lines)


def test_rule_coverage_floor():
    pack = load_rulepack(PACK)
    # 只数主 rule_id;acceptable_rule_ids 是等价别名,不计地板(防靠别名凑覆盖,spec §1.5)
    covered = {e.rule_id for c in loader.load_cases() for e in c.expect_issues}
    pack_ids = {r.id for r in pack.rules}
    missing_floor = EXPECTED_COVERAGE - covered
    assert not missing_floor, f"覆盖率地板未达成: {sorted(missing_floor)}"
    unknown = covered - pack_ids
    assert not unknown, f"题库引用了不存在的规则: {sorted(unknown)}"


def test_coverage_complete_marker():
    """批C 收口:EXPECTED_COVERAGE、pack 全集、题库实 coverage 三方精确相等——漏建(题库漏规则)与多建(表与文件漂移)双方向即红。"""
    pack = load_rulepack(PACK)
    pack_ids = {r.id for r in pack.rules}
    assert EXPECTED_COVERAGE == pack_ids
    covered = {e.rule_id for c in loader.load_cases() for e in c.expect_issues}
    assert covered == pack_ids


# ---- report + CLI ----


def test_report_counts_and_markdown():
    from app.extensions.bid_review.golden.schema import CaseResult

    results = [
        CaseResult(case="a", desc="", strict=False, ok=True, missing=[], unexpected=[], absent_violations=[], checklist_diff=[], hits={"L1-009": 1}),
        CaseResult(case="b", desc="", strict=False, ok=False, missing=["期望未命中[L1-009 fatal violation] 未命中: contains=['x']"], unexpected=[], absent_violations=["不应报而报[L1-011]"], checklist_diff=[]),
    ]
    rep = build_report(results)
    assert rep["total"] == 2 and rep["failed"] == 1
    assert rep["per_rule"]["L1-009"]["tp"] == 1 and rep["per_rule"]["L1-009"]["fn"] == 1
    assert rep["per_rule"]["L1-011"]["absent_fp"] == 1
    md = render_markdown(rep)
    assert "| 规则 | TP | FN | 误报(absent) |" in md and "L1-009" in md and "FAIL" in md


def test_report_zero_hit_flag():
    """有题引用但四类计数全 0 → zero_hit 死规则告警(spec §1.5)。"""
    from app.extensions.bid_review.golden.schema import CaseResult, Expectation, GoldenCase

    res = CaseResult(case="a", desc="", strict=False, ok=True, missing=[], unexpected=[], absent_violations=[], checklist_diff=[])
    c = GoldenCase(case="a", desc="", fields={}, expect_issues=[Expectation(rule_id="L1-001", severity="fatal")], expect_absent=[])
    rep = build_report([res], [c])
    assert rep["per_rule"]["L1-001"]["zero_hit"] is True


def test_cli_main_exit_codes(tmp_path, capsys):
    from app.extensions.bid_review.golden.__main__ import main

    out = tmp_path / "rep.json"
    rc = main(["--report", "md", "--out", str(out)])
    assert rc == 0 and out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["total"] >= 1


def test_cli_main_failure_paths(capsys, monkeypatch):
    from app.extensions.bid_review.golden import __main__ as cli_main
    from app.extensions.bid_review.golden.schema import CaseResult

    def _boom():
        raise ValueError("boom")

    # 加载失败 → stderr + rc 1(patch 目标=__main__ 的 import 本名 load_cases,非 loader 模块属性)
    monkeypatch.setattr(cli_main, "load_cases", _boom)
    assert cli_main.main(["--report", "md"]) == 1
    assert "题库加载失败" in capsys.readouterr().err
    # 有题失败 → rc 1(成绩单仍输出;main 走 asyncio.run(run_all(cases)),fake 须回协程)
    bad = CaseResult(case="x", desc="", strict=False, ok=False, missing=["期望未命中[L1-009 fatal violation] 未命中: contains=[]"], unexpected=[], absent_violations=[], checklist_diff=[])

    async def _fake_run_all(cases, pack=None):
        return [bad]

    monkeypatch.setattr(cli_main, "load_cases", lambda: [])
    monkeypatch.setattr(cli_main, "run_all", _fake_run_all)
    assert cli_main.main(["--report", "md"]) == 1
    assert "FAIL" in capsys.readouterr().out


# ---- 全管线冒烟(spec §8):钉接线,不钉 LLM ----
SMOKE = CASES_DIR.parent / "smoke"


def test_fields_from_stub_unknown_key(tmp_path):
    """T6 挂账守卫:stub 键名笔误原本被「请求路径∩stub 键」过滤静默丢弃=抽取层假绿,
    现 _fields_from_stub 构造冒烟字段时(冒烟接线期,非 loader 加载期)对照 known_field_paths 大声报错。"""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "tender.md").write_text("x", encoding="utf-8")
    (tmp_path / "extract_stub.yaml").write_text("bid.total_pricee: 1.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="疑似键名笔误"):
        _fields_from_stub(tmp_path)


def test_smoke_docs_fixture_and_stub_extract():
    fields = _fields_from_stub(SMOKE / "smoke-1-basic")
    assert fields.get("bid.total_price") == 1000001.0


@pytest.mark.asyncio
async def test_smoke_pipeline_end_to_end():
    pack = load_rulepack(PACK)
    res = await run_smoke_dir(SMOKE / "smoke-1-basic", pack)
    assert res.ok, res.diff_lines
