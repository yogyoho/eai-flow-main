"""Task 20 测试:bid_review 评测指标——对齐配对/compute_metrics/gate_check(素材③ 5.2 公式落地)。

纯函数测试不落库;评测入口 run_eval.py 的全链冒烟走 `make eval-bid-review`(设计文档 §7:
评测分钟级不进默认测试链,指标单测才归 make test),本文件只锁 metrics.py 计算语义:
全对 P=R=1 / 错页 evidence_accuracy 降 / fatal 降级率>0 / gate 边界 0.95==0.95 过 /
need_human 分列(A12)/ det evidence=[] 重权 / 贪心一对一 1TP+(n-1)FP / 零漂移与
单条 fatal 规则零召回门禁。
"""

import importlib.util
import sys
from pathlib import Path

_METRICS_PATH = Path(__file__).resolve().parent / "eval" / "bid_review" / "metrics.py"
_spec = importlib.util.spec_from_file_location("bid_review_eval_metrics", _METRICS_PATH)
metrics = importlib.util.module_from_spec(_spec)
sys.modules["bid_review_eval_metrics"] = metrics  # dataclass 装饰器查 sys.modules[cls.__module__],先注册再执行
_spec.loader.exec_module(metrics)

Issue = metrics.Issue
CaseEval = metrics.CaseEval


def _sem_issue(rule="L1-013", msg="质保期承诺与招标要求不一致", sev="major", doc="D1", page=3):
    """sem 形态:携带证据(evidence 非空),证据维度参与计分。"""
    return Issue(
        rule_id=rule,
        layer="L3",
        severity=sev,
        verdict="violation",
        message=msg,
        fix="修正质保承诺",
        evidence=[{"doc_id": doc, "page": page, "section_path": "质保/承诺", "text": "质保期承诺摘录"}],
        dedup_key=f"{rule}|-|{msg[:40]}",
    )


def _det_issue(rule="L1-009", msg="投标总价 5000001.00 超过最高限价 5000000.00", sev="fatal"):
    """det 形态:evidence=[](评审修正 A9,证据由编排层补齐)。"""
    return Issue(
        rule_id=rule,
        layer="L1",
        severity=sev,
        verdict="violation",
        message=msg,
        fix="复核报价汇总与含税口径",
        evidence=[],
        dedup_key=f"{rule}|-|{msg[:40]}",
    )


def _golden(**kw):
    base = dict(
        rule_id="L1-009",
        layer="L1",
        severity="fatal",
        verdict="violation",
        message="投标总价 5000001.00 超过最高限价 5000000.00",
        fix="复核报价汇总与含税口径",
        evidence=[{"doc_id": "A-PRICE-SHEET", "page": 1, "section_path": "报价汇总表", "text": "投标总价:5000001.00 元"}],
        dedup_key="L1-009|-|投标总价 5000001.00",
    )
    base.update(kw)
    return Issue(**base)


# ── Step 2 规定四景 ──────────────────────────────────────────────────


def test_perfect_match_precision_recall_1():
    """全对:2 预测/2 金标准逐条对上 → P=R=1。"""
    g = [_golden(), _golden(rule_id="L1-010", layer="L1", message="报价加总不一致:明细合计与总价不一致", dedup_key="L1-010|-|报价加总")]
    p = [_det_issue(), _det_issue(rule="L1-010", msg="报价加总不一致:明细合计与总价不一致")]
    m = metrics.compute_metrics([CaseEval(case_id="C1", golden=g, predictions=p)])
    assert m["tp"] == 2 and m["fp"] == 0 and m["fn"] == 0
    assert m["precision"] == 1.0 and m["recall"] == 1.0


def test_wrong_page_drops_evidence_accuracy():
    """错页码(超 ±1 容差):配对仍成立(rule+message 主导),evidence_accuracy 降。"""
    g = [_sem_issue()]
    p = [_sem_issue(page=9)]  # golden page=3,|9-3|>1 → 证据锚不命中
    m = metrics.compute_metrics([CaseEval(case_id="C1", golden=g, predictions=p)])
    assert m["tp"] == 1
    assert m["evidence_pairs"] == 1
    assert m["evidence_accuracy"] == 0.0


def test_page_tolerance_plus_minus_1_hits():
    """页容差 ±1:page 2 对 golden page 1 命中,evidence_accuracy=1。"""
    g = [_sem_issue(page=1)]
    p = [_sem_issue(page=2)]
    m = metrics.compute_metrics([CaseEval(case_id="C1", golden=g, predictions=p)])
    assert m["evidence_accuracy"] == 1.0


def test_fatal_downgrade_rate_positive():
    """fatal 被低档预测配对:降级率>0;分母=已配对 fatal 金标准行(漏报归 recall 把关)。"""
    g = [_golden(), _golden(rule_id="L1-010", message="明细合计与总价不一致", dedup_key="L1-010|-|x")]
    p = [_det_issue(sev="major"), _det_issue(rule="L1-010", msg="明细合计与总价不一致")]  # 第一条被降级 major
    m = metrics.compute_metrics([CaseEval(case_id="C1", golden=g, predictions=p)])
    assert m["fatal_matched"] == 2
    assert m["fatal_downgraded"] == 1
    assert m["fatal_downgrade_rate"] == 0.5


def test_gate_check_boundary_095_equals_pass():
    """gate 边界:fatal_recall=0.95 与阈值相等 → 过;0.9 → 挂;降级率 0.02==0.02 → 过。"""
    base = {"precision": 1.0, "evidence_accuracy": 1.0, "fatal_downgrade_rate": 0.0, "determinism": 1.0, "fatal_rule_recall_zero": []}
    ok, failures = metrics.gate_check({**base, "fatal_recall": 0.95})
    assert ok and failures == []
    ok2, failures2 = metrics.gate_check({**base, "fatal_recall": 0.9})
    assert not ok2 and any("fatal_recall" in f for f in failures2)
    ok3, _ = metrics.gate_check({**base, "fatal_recall": 1.0, "fatal_downgrade_rate": 0.02})
    assert ok3
    ok4, _ = metrics.gate_check({**base, "fatal_recall": 1.0, "fatal_downgrade_rate": 0.021})
    assert not ok4


# ── A12:need_human 与正式违规分列 ────────────────────────────────────


def test_need_human_predictions_not_counted_as_fp():
    """A12:need_human 预测不入 TP/FP/FN 配对与 precision 分母,单列 need_human_predicted。"""
    g = [_golden()]
    nh = Issue(rule_id="L1-009", layer="L1", severity="fatal", verdict="need_human", need_human=True, message="字段缺失无法判定", evidence=[])
    m = metrics.compute_metrics([CaseEval(case_id="C1", golden=g, predictions=[nh])])
    assert m["tp"] == 0 and m["fp"] == 0 and m["fn"] == 1
    assert m["need_human_predicted"] == 1
    assert m["per_rule"]["L1-009"]["fp"] == 0  # 待人工不冒充误报
    assert m["recall"] == 0.0


def test_unclear_verdict_counts_as_need_human():
    """unclear 条目(A12 后语义=need_human 单列)不入正式违规统计。"""
    g = [_golden()]
    unc = Issue(rule_id="L1-009", layer="L1", severity="fatal", verdict="unclear", need_human=True, message="不确定", evidence=[])
    m = metrics.compute_metrics([CaseEval(case_id="C1", golden=g, predictions=[unc])])
    assert m["fp"] == 0 and m["need_human_predicted"] == 1


# ── 证据门禁口径(manifest 注:A9 det 行不计)────────────────────────


def test_det_no_evidence_renormalized_and_evidence_gate_vacuous():
    """det 预测 evidence=[]:score 按 (0.5R+0.2S)/0.7 重权(rule 命中即 0.714>=0.55 配对),
    evidence_accuracy 空集记 1.0(det-only 首跑不按构造 0 分)。"""
    g = [_golden()]
    p = [_det_issue()]
    m = metrics.compute_metrics([CaseEval(case_id="C1", golden=g, predictions=p)])
    assert m["tp"] == 1
    assert m["evidence_pairs"] == 0
    assert m["evidence_accuracy"] == 1.0


def test_det_rule_mismatch_cannot_reach_threshold():
    """det 预测 rule 不符:重权上限 0.2/0.7≈0.286 < 0.55,永不跨阈值配对(rule 门强)。"""
    g = [_golden()]
    p = [_det_issue(rule="L3-006", msg=_golden().message)]
    m = metrics.compute_metrics([CaseEval(case_id="C1", golden=g, predictions=p)])
    assert m["tp"] == 0 and m["fp"] == 1 and m["fn"] == 1


# ── 贪心一对一:1TP+(n-1)FP ──────────────────────────────────────────


def test_duplicate_hits_one_tp_plus_fp():
    """一条金标准被 n 条预测命中 = 1TP+(n-1)FP:贪心一对一,落选预测计 FP。"""
    g = [_golden()]
    p1 = _det_issue()
    p2 = _det_issue(msg="投标总价 5000001.00 超过最高限价 5000000.00(重复产出形态)")
    m = metrics.compute_metrics([CaseEval(case_id="C1", golden=g, predictions=[p1, p2])])
    assert m["tp"] == 1 and m["fp"] == 1 and m["fn"] == 0
    assert m["precision"] == 0.5


def test_cross_case_matching_isolated():
    """配对按案隔离:case1 的预测不匹配 case2 的金标准。"""
    g1, g2 = [_golden()], [_golden()]
    p2 = [_det_issue()]
    m = metrics.compute_metrics(
        [
            CaseEval(case_id="C1", golden=g1, predictions=[]),
            CaseEval(case_id="C2", golden=g2, predictions=p2),
        ]
    )
    assert m["tp"] == 1 and m["fn"] == 1 and m["fp"] == 0
    assert m["recall"] == 0.5 and m["precision"] == 1.0


# ── 干净案 / W 权重 / per_rule ───────────────────────────────────────


def test_clean_case_vacuous_pass():
    """干净案(无金标准无误报):空分母空过 P=R=1,不炸、不掉门禁。"""
    m = metrics.compute_metrics([CaseEval(case_id="CLEAN", golden=[], predictions=[])])
    assert m["precision"] == 1.0 and m["recall"] == 1.0 and m["fatal_recall"] == 1.0
    ok, failures = metrics.gate_check(m)
    assert ok and failures == []


def test_weighted_recall_uses_W_weights():
    """W 权重 {fatal:5,major:2,minor:1,info:0.5}:漏 fatal 比漏 major 权重打击更大。"""
    g_full = [_golden(), _golden(rule_id="L3-006", layer="L3", severity="major", message="金额与报价总价不一致", dedup_key="L3-006|-|x")]
    p_only_major = [_det_issue(rule="L3-006", msg="金额与报价总价不一致", sev="major")]
    m_miss_fatal = metrics.compute_metrics([CaseEval(case_id="C1", golden=g_full, predictions=p_only_major)])
    p_all = [_det_issue(), _det_issue(rule="L3-006", msg="金额与报价总价不一致", sev="major")]
    m_all = metrics.compute_metrics([CaseEval(case_id="C1", golden=g_full, predictions=p_all)])
    assert m_all["weighted_recall"] == 1.0
    assert m_miss_fatal["weighted_recall"] == metrics.W["major"] / (metrics.W["fatal"] + metrics.W["major"])
    assert m_miss_fatal["weighted_recall"] < 0.5  # fatal 权重 5 使漏报惩罚显著


def test_per_rule_stats_and_fatal_zero_recall_list():
    """per_rule 命中/漏/误 + 单条 fatal 规则零召回清单(有正样本时进门禁)。"""
    g = [_golden(), _golden(rule_id="L3-006", layer="L3", severity="major", message="金额不一致", dedup_key="L3-006|-|x")]
    p = [_det_issue(), _det_issue(rule="L1-011", msg="清单条目不一致", sev="major")]
    m = metrics.compute_metrics([CaseEval(case_id="C1", golden=g, predictions=p)])
    assert m["per_rule"]["L1-009"] == {"tp": 1, "fp": 0, "fn": 0, "recall": 1.0}
    assert m["per_rule"]["L3-006"]["fn"] == 1
    assert m["per_rule"]["L1-011"]["fp"] == 1
    assert m["fatal_rule_recall_zero"] == []


def test_fatal_rule_zero_recall_enters_gate():
    """fatal 规则有正样本但一条未中 → fatal_rule_recall_zero 非空,gate_check 挂。"""
    g = [_golden(rule_id="L1-012", message="低于成本投标", dedup_key="L1-012|-|x")]
    p = [_det_issue(rule="L1-011", msg="清单条目不一致", sev="major")]
    m = metrics.compute_metrics([CaseEval(case_id="C1", golden=g, predictions=p)])
    assert m["fatal_rule_recall_zero"] == ["L1-012"]
    ok, failures = metrics.gate_check(m)
    assert not ok and any("L1-012" in f for f in failures)


# ── 确定性零漂移 / bootstrap_ci ──────────────────────────────────────


def test_determinism_gate_zero_drift_required():
    """确定性零漂移=100%:0.99 即挂,1.0 过。"""
    base = {"fatal_recall": 1.0, "precision": 1.0, "evidence_accuracy": 1.0, "fatal_downgrade_rate": 0.0, "fatal_rule_recall_zero": []}
    ok1, _ = metrics.gate_check({**base, "determinism": 1.0})
    ok2, failures2 = metrics.gate_check({**base, "determinism": 0.99})
    assert ok1 and not ok2 and any("determinism" in f for f in failures2)


def test_bootstrap_ci_deterministic_and_brackets_point():
    """bootstrap_ci 按 case 重采样:固定种子两次调用结果一致;区间套住点估计。"""
    cases = [
        CaseEval(case_id="C1", golden=[_golden()], predictions=[_det_issue()]),
        CaseEval(case_id="C2", golden=[_golden(), _golden(rule_id="L1-010", message="加总不一致", dedup_key="L1-010|-|y")], predictions=[_det_issue()]),
    ]
    ci1 = metrics.bootstrap_ci(cases, n=200, seed=7)
    ci2 = metrics.bootstrap_ci(cases, n=200, seed=7)
    assert ci1 == ci2
    point = metrics.compute_metrics(cases)
    assert ci1["recall"][0] <= point["recall"] <= ci1["recall"][1]
    assert ci1["precision"][0] <= point["precision"] <= ci1["precision"][1]


# ── from_row 兼容(golden jsonl dict / ReviewIssue ORM 行)────────────


def test_from_row_accepts_dict_and_attrs():
    d = {"rule_id": "L1-009", "layer": "L1", "severity": "fatal", "verdict": "violation", "need_human": False, "message": "m", "fix": "f", "evidence": [{"doc_id": "A", "page": 1}], "dedup_key": "k", "mutator": "MUT-001"}
    i1 = Issue.from_row(d)
    assert i1.rule_id == "L1-009" and i1.evidence[0]["doc_id"] == "A"

    class _Row:  # 模拟 ReviewIssue ORM 行属性访问
        rule_id, layer, severity, verdict, need_human, message, fix, evidence, dedup_key, confidence = ("L3-006", "L3", "major", "violation", False, "mm", "ff", [], "k2", 1.0)

    i2 = Issue.from_row(_Row())
    assert i2.rule_id == "L3-006" and i2.confidence == 1.0
