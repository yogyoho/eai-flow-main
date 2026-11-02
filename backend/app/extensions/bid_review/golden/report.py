"""成绩单聚合与渲染(EAI-CUSTOM 2026-11-03,spec §7):信息型,不进 CI 强制。
per_rule 键:tp=期望命中题数/fn=期望未命中/absent_fp=expect_absent 违例/
unexpected=strict 期望外。fn/absent_fp/unexpected 从 runner diff 行解析——
首方括号 token=rule_id 是 runner 的输出契约(T3 F1 修复保持该格式)。"""

from app.extensions.bid_review.golden.schema import CaseResult, GoldenCase

_COUNT_KEYS = ("tp", "fn", "absent_fp", "unexpected")


def _new_row() -> dict:
    return dict.fromkeys(_COUNT_KEYS, 0)


def build_report(results: list[CaseResult], cases: list[GoldenCase] | None = None) -> dict:
    per: dict[str, dict] = {}
    for r in results:
        for rid, n in (r.hits or {}).items():  # tp 来自 runner 消化命中计数
            per.setdefault(rid, _new_row())["tp"] += n
        for line in r.missing:
            rid = line.split("[", 1)[1].split("]", 1)[0].split()[0]
            per.setdefault(rid, _new_row())["fn"] += 1
        for line in r.absent_violations:
            rid = line.split("[", 1)[1].split("]", 1)[0]
            per.setdefault(rid, _new_row())["absent_fp"] += 1
        for line in r.unexpected:
            rid = line.split("[", 1)[1].split("]", 1)[0].split()[0]
            per.setdefault(rid, _new_row())["unexpected"] += 1
    referenced: set[str] = set()
    for c in cases or []:
        referenced.update(e.rule_id for e in c.expect_issues)
        referenced.update(c.expect_absent)
    for rid in referenced:
        m = per.setdefault(rid, _new_row())
        m["zero_hit"] = sum(m[k] for k in _COUNT_KEYS) == 0  # 死规则/题失效告警(spec §1.5 采纳)
    return {"total": len(results), "failed": sum(1 for r in results if not r.ok), "per_rule": per, "results": [r.__dict__ for r in results]}


def render_markdown(rep: dict) -> str:
    lines = ["# 金标准成绩单", "", f"题数 {rep['total']} | 失败 {rep['failed']}", "", "| 规则 | TP | FN | 误报(absent) | 期望外(strict) | zero_hit |", "|---|---|---|---|---|---|"]
    for rid in sorted(rep["per_rule"]):
        m = rep["per_rule"][rid]
        lines.append(f"| {rid} | {m['tp']} | {m['fn']} | {m['absent_fp']} | {m['unexpected']} | {m.get('zero_hit', '')} |")
    lines.append("")
    for r in rep["results"]:
        mark = "PASS" if r["ok"] else "FAIL"
        lines.append(f"- {mark} {r['case']}" + ("" if r["ok"] else "：" + "；".join(r["missing"] + r["unexpected"] + r["absent_violations"] + r["checklist_diff"])))
    return "\n".join(lines) + "\n"
