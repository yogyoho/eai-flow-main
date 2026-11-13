"""金标准 oracle 适配面(批二十 M1-d,EAI-CUSTOM 2026-11-13)——命令行薄壳:
ctx JSON 文件路径 → run_assertions → 确定性报告 JSON stdout。退出码 oracle:
0=全 PASS / 1=有 FAIL / 2=有 ERROR(ERROR 为基建/上下文缺陷面,优先于 FAIL)。
执行核零 IO 律不破:唯二 IO=读 argv 文件+写 stdout,均在壳内。"""

from __future__ import annotations

import argparse
import json
import sys

from app.extensions.bid_write.executor.report import to_report_dict
from app.extensions.bid_write.executor.runner import run_assertions


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="bid_write 断言执行器 oracle(ctx JSON→报告 JSON)")
    p.add_argument("ctx_json", help="执行上下文 JSON 文件路径(green/mutated ctx)")
    p.add_argument("--skills", default="", help="逗号分隔技能范围,如 BL,PS(空=全量)")
    a = p.parse_args(argv)
    with open(a.ctx_json, encoding="utf-8") as f:
        ctx = json.load(f)
    skills = tuple(s.strip().upper() for s in a.skills.split(",") if s.strip()) or None
    report = run_assertions(ctx, skills=skills)
    print(json.dumps(to_report_dict(report), sort_keys=True, ensure_ascii=False))
    statuses = {r.status for r in report.results}
    if "ERROR" in statuses:
        return 2
    if "FAIL" in statuses:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
