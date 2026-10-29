"""bid-review 评测指标(Task 20)——金标准对齐 + 指标计算 + 门禁判定(素材③ 5.2 公式落地)。

对齐算法(设计文档 §7 / 素材③ 5.2):score = 0.5·rule_match + 0.3·evidence_overlap +
0.2·semantic_sim,>=0.55 贪心一对一配对;一条金标准被 n 条预测命中 = 1TP+(n-1)FP(贪心
一对一下落选预测自然落 FP)。embedding 相似度以 difflib.SequenceMatcher(去空白归一)代占。

统计口径(Task 20 显式取舍,plan 未写明处逐条声明):
1. need_human 与正式违规分列(A12 收口口径):need_human=True 或 verdict!=violation 的预测
   不进配对、不进 precision/recall/per_rule 分母,单列 need_human_predicted——待人工条目是
   人审队列不是违规判定,混入会把「宁多报交人工」的 need_human 通路误计成误报;金标准行
   同口径过滤(当前 fixtures 全为正式行,代码路径对称保留)。
2. 证据维度仅对携带证据(evidence 非空,sem/hyb 形态)的预测计分(golden/manifest 口径注,
   评审修正 A9:det 预测恒产 evidence=[]):det 预测 score 按 (0.5·rule+0.2·semantic)/0.7
   重权归一(rule 单独命中即 0.714>=0.55,rule 不符上限 0.286 永不配对——规则身份是 det
   匹配的唯一强信号);evidence_accuracy 门禁仅在「配对成功且预测携带证据」集合取均值,
   空集记 1.0 空过(det-only 首跑不因 evidence=[] 按构造 0 分)。
3. evidence_overlap = 金标准证据锚覆盖率:|{g: ∃p, doc_id 相同且 |page 差|<=1}|/|golden 证据|
   (金标准无证据行记 1.0;双侧均有页码才计页容差,缺页按 doc_id 相等命中)。
4. fatal_downgrade_rate 分母 = 已配对的金标准 fatal 行(降级是配对对的属性;漏报由
   fatal_recall 单独把关),分子 = 配对预测 severity 低于金标准档的行;无配对 fatal 记 0.0。
5. precision/recall 分母为 0 时空过记 1.0(无金标准且无误报 = 干净案通过;金标准在而预测
   全缺的漏报由 recall=0 与 fatal_recall 门禁兜住,不会被空过掩盖)。
6. W 权重 {fatal:5, major:2, minor:1, info:0.5} 产 severity 加权召回 weighted_recall
   (辅助报告指标,不设门禁)——高严重度漏报权重打击更大,供里程碑趋势观察。
7. bootstrap_ci 按 case 有放回重采样 n=1000(random.Random 固定种子:评测自身必须满足
   确定性零漂移),输出 recall/precision 的 2.5/97.5 分位区间;单案包区间退化为点值。
8. 门禁(design §7 MVP 阈值):fatal_recall>=0.95(硬阻断)/precision>=0.80/
   evidence_accuracy>=0.95/fatal 降级率<=0.02/确定性零漂移=100%/单条 fatal 规则召回
   不得为 0(有金标准正样本时,fatal_rule_recall_zero 非空即挂)。边界含等号(0.95==0.95 过)。
"""

from __future__ import annotations

import difflib
import random
from dataclasses import dataclass, field
from dataclasses import fields as dc_fields

MATCH_THRESHOLD = 0.55
PAGE_TOLERANCE = 1  # 页容差 ±1
WEIGHTS = {"rule": 0.5, "evidence": 0.3, "semantic": 0.2}
NO_EVIDENCE_DENOM = 0.7  # det 预测 evidence=[] 时 (0.5R+0.2S)/0.7 重权,分母 = 权重和
W = {"fatal": 5.0, "major": 2.0, "minor": 1.0, "info": 0.5}
SEVERITY_RANK = {"fatal": 3, "major": 2, "minor": 1, "info": 0}

# 门禁阈值(design §7 MVP):key → (比较符, 阈值)
GATES = {
    "fatal_recall": (">=", 0.95),  # 硬阻断
    "precision": (">=", 0.80),
    "evidence_accuracy": (">=", 0.95),
    "fatal_downgrade_rate": ("<=", 0.02),
    "determinism": (">=", 1.0),  # 零漂移 = 100%
}


@dataclass
class Issue:
    """评测侧问题行(与 ReviewIssue 列/golden_issues.jsonl 字段对齐;mutator 等溯源键不进指标)。"""

    rule_id: str
    layer: str = ""
    severity: str = "minor"
    verdict: str = "violation"
    need_human: bool = False
    message: str = ""
    fix: str = ""
    evidence: list = field(default_factory=list)
    dedup_key: str = ""
    confidence: float = 1.0

    @classmethod
    def from_row(cls, row) -> Issue:
        """ReviewIssue ORM 行(属性访问)或 golden jsonl dict(键访问)双形态装入。"""
        names = {f.name for f in dc_fields(cls)}
        if isinstance(row, dict):
            return cls(**{k: row[k] for k in names if k in row})
        return cls(**{k: getattr(row, k) for k in names if hasattr(row, k)})

    @property
    def is_formal(self) -> bool:
        """正式违规类(A12 分列口径):非待人工且 verdict==violation。"""
        return (not self.need_human) and self.verdict == "violation"


@dataclass
class CaseEval:
    """单案评测输入:金标准行 + 该案引擎预测(need_human 行不剔除,由 compute_metrics 分列)。"""

    case_id: str
    golden: list[Issue]
    predictions: list[Issue]


def _norm_text(s: str) -> str:
    return "".join(str(s).split()).lower()


def semantic_sim(a: str, b: str) -> float:
    """消息相似度:difflib.SequenceMatcher 归一代占 embedding(plan Step 1 口径)。"""
    if not a and not b:
        return 1.0
    return difflib.SequenceMatcher(None, _norm_text(a), _norm_text(b)).ratio()


def _page_of(item) -> int | None:
    p = item.get("page") if isinstance(item, dict) else None
    if isinstance(p, bool) or p is None:
        return None
    if isinstance(p, (int, float)):
        return int(p)
    if isinstance(p, str) and p.strip().lstrip("-").isdigit():
        return int(p)
    return None


def evidence_overlap(golden: Issue, pred: Issue) -> float:
    """金标准证据锚覆盖率(页容差 ±1;金标准无证据行记 1.0——无锚可覆盖即不罚)。"""
    g_ev = [e for e in (golden.evidence or []) if isinstance(e, dict)]
    if not g_ev:
        return 1.0
    p_ev = [e for e in (pred.evidence or []) if isinstance(e, dict)]
    hits = 0
    for g in g_ev:
        gp = _page_of(g)
        gd = str(g.get("doc_id"))
        for p in p_ev:
            if str(p.get("doc_id")) != gd:
                continue
            pp = _page_of(p)
            if gp is None or pp is None or abs(pp - gp) <= PAGE_TOLERANCE:
                hits += 1
                break
    return hits / len(g_ev)


def pair_score(golden: Issue, pred: Issue) -> float:
    """配对分:0.5·rule + 0.3·evidence + 0.2·semantic;预测不携带证据(det)按 0.7 重权。"""
    rule = 1.0 if golden.rule_id == pred.rule_id else 0.0
    sem = semantic_sim(golden.message, pred.message)
    if [e for e in (pred.evidence or []) if isinstance(e, dict)]:
        return WEIGHTS["rule"] * rule + WEIGHTS["evidence"] * evidence_overlap(golden, pred) + WEIGHTS["semantic"] * sem
    return (WEIGHTS["rule"] * rule + WEIGHTS["semantic"] * sem) / NO_EVIDENCE_DENOM


@dataclass
class MatchResult:
    """贪心一对一配对结果(均限正式违规类)。"""

    pairs: list[tuple[Issue, Issue, float]] = field(default_factory=list)  # (golden, pred, score)
    fp_preds: list[Issue] = field(default_factory=list)  # 落选/超阈预测 = 误报
    fn_goldens: list[Issue] = field(default_factory=list)  # 未配对金标准 = 漏报


def match(goldens: list[Issue], preds: list[Issue]) -> MatchResult:
    """贪心一对一:全对按分降序(同分按 (golden 序, pred 序) 保证确定性)依次占位,
    score>=0.55 且双侧未占用才成对;剩余预测=FP、剩余金标准=FN。"""
    pairs_all: list[tuple[float, int, int]] = []
    for gi, g in enumerate(goldens):
        for pi, p in enumerate(preds):
            s = pair_score(g, p)
            if s >= MATCH_THRESHOLD:
                pairs_all.append((s, gi, pi))
    pairs_all.sort(key=lambda t: (-t[0], t[1], t[2]))
    used_g: set[int] = set()
    used_p: set[int] = set()
    res = MatchResult()
    for s, gi, pi in pairs_all:
        if gi in used_g or pi in used_p:
            continue
        used_g.add(gi)
        used_p.add(pi)
        res.pairs.append((goldens[gi], preds[pi], s))
    res.fp_preds = [p for i, p in enumerate(preds) if i not in used_p]
    res.fn_goldens = [g for i, g in enumerate(goldens) if i not in used_g]
    return res


def _ratio(num: float, den: float, vacuous: float) -> float:
    return num / den if den else vacuous


def _agg(cases: list[CaseEval]) -> dict:
    """聚合配对统计(bootstrap 重采样共用同一计数路径)。"""
    tp = fp = fn = 0
    golden_total = 0
    per_rule: dict[str, dict] = {}
    for c in cases:
        g = [i for i in c.golden if i.is_formal]
        p = [i for i in c.predictions if i.is_formal]
        m = match(g, p)
        tp += len(m.pairs)
        fp += len(m.fp_preds)
        fn += len(m.fn_goldens)
        for gg, _pp, _s in m.pairs:
            # 配对要求 rule 相同(rule 不符时 score<=0.5<0.55 恒不成对),tp 只记金标准规则键
            per_rule.setdefault(gg.rule_id, {"tp": 0, "fp": 0, "fn": 0})["tp"] += 1
        for gg in m.fn_goldens:
            per_rule.setdefault(gg.rule_id, {"tp": 0, "fp": 0, "fn": 0})["fn"] += 1
        for pp in m.fp_preds:
            per_rule.setdefault(pp.rule_id, {"tp": 0, "fp": 0, "fn": 0})["fp"] += 1
        golden_total += len(g)
    for rid, e in per_rule.items():
        positives = e["tp"] + e["fn"]
        e["recall"] = _ratio(e["tp"], positives, 1.0)
    return {"tp": tp, "fp": fp, "fn": fn, "golden_total": golden_total, "per_rule": per_rule}


def compute_metrics(case_evals: list[CaseEval], determinism: float = 1.0) -> dict:
    """全集指标(逐案配对后聚合);determinism 由 run_eval 逐案零漂移实测写入。"""
    a = _agg(case_evals)
    tp, fp, fn = a["tp"], a["fp"], a["fn"]
    precision = _ratio(tp, tp + fp, 1.0)
    recall = _ratio(tp, tp + fn, 1.0)

    fatal_golden = fatal_matched = fatal_downgraded = 0
    ev_pairs: list[float] = []
    w_num = w_den = 0.0
    fatal_rule_positive: dict[str, list[int]] = {}
    for c in case_evals:
        g = [i for i in c.golden if i.is_formal]
        p = [i for i in c.predictions if i.is_formal]
        m = match(g, p)
        for gg, pp, _ in m.pairs:
            w_num += W.get(gg.severity, 0.5)
            if gg.severity == "fatal":
                fatal_matched += 1
                if SEVERITY_RANK.get(pp.severity, 0) < SEVERITY_RANK.get(gg.severity, 3):
                    fatal_downgraded += 1
            if [e for e in (pp.evidence or []) if isinstance(e, dict)]:
                ev_pairs.append(evidence_overlap(gg, pp))
        for gg in g:
            w_den += W.get(gg.severity, 0.5)
            if gg.severity == "fatal":
                fatal_golden += 1
                fatal_rule_positive.setdefault(gg.rule_id, []).append(0)

    fatal_recall = _ratio(fatal_matched, fatal_golden, 1.0)
    fatal_rule_recall_zero = sorted(rid for rid, hits in fatal_rule_positive.items() if a["per_rule"].get(rid, {}).get("tp", 0) == 0)
    return {
        "cases": len(case_evals),
        "golden_total": a["golden_total"],
        "need_human_predicted": sum(1 for c in case_evals for i in c.predictions if not i.is_formal),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": _ratio(2 * precision * recall, precision + recall, 0.0),
        "fatal_golden": fatal_golden,
        "fatal_matched": fatal_matched,
        "fatal_recall": fatal_recall,
        "fatal_downgraded": fatal_downgraded,
        "fatal_downgrade_rate": _ratio(fatal_downgraded, fatal_matched, 0.0),
        "evidence_accuracy": _ratio(sum(ev_pairs), len(ev_pairs), 1.0),
        "evidence_pairs": len(ev_pairs),
        "weighted_recall": _ratio(w_num, w_den, 1.0),
        "rule_coverage": {
            "rules_with_golden": sum(1 for e in a["per_rule"].values() if e["tp"] + e["fn"] > 0),
            "rules_in_recall_denominator": len(a["per_rule"]),
            "note": "无专属算子/无正样本的规则不进召回分母,计入覆盖率报告(design §7)",
        },
        "per_rule": a["per_rule"],
        "fatal_rule_recall_zero": fatal_rule_recall_zero,
        "determinism": determinism,
    }


def gate_check(metrics_dict: dict) -> tuple[bool, list[str]]:
    """门禁判定(边界含等号);另加单条 fatal 规则零召回硬门。返回 (是否全过, 失败清单)。"""
    failures: list[str] = []
    for key, (op, thr) in GATES.items():
        val = metrics_dict.get(key)
        if val is None:
            failures.append(f"{key} 缺失(阈值 {op}{thr})")
            continue
        ok = val >= thr if op == ">=" else val <= thr
        if not ok:
            failures.append(f"{key}={val} 违 {op}{thr}")
    for rid in metrics_dict.get("fatal_rule_recall_zero") or []:
        failures.append(f"单条 fatal 规则 {rid} 召回为 0(有金标准正样本)")
    return (not failures), failures


def bootstrap_ci(case_evals: list[CaseEval], n: int = 1000, seed: int = 20261029) -> dict:
    """按 case 有放回重采样 n 次,recall/precision 的 2.5/97.5 分位区间(固定种子保确定性)。"""
    rng = random.Random(seed)
    if not case_evals:
        return {"recall": [1.0, 1.0], "precision": [1.0, 1.0]}
    recalls: list[float] = []
    precisions: list[float] = []
    for _ in range(n):
        sample = [case_evals[rng.randrange(len(case_evals))] for _ in range(len(case_evals))]
        a = _agg(sample)
        precisions.append(_ratio(a["tp"], a["tp"] + a["fp"], 1.0))
        recalls.append(_ratio(a["tp"], a["tp"] + a["fn"], 1.0))
    recalls.sort()
    precisions.sort()

    def _pct(sorted_vals: list[float], q: float) -> float:
        return sorted_vals[int(q * (len(sorted_vals) - 1))]

    return {"recall": [_pct(recalls, 0.025), _pct(recalls, 0.975)], "precision": [_pct(precisions, 0.025), _pct(precisions, 0.975)]}
