"""CLI 成绩单入口(EAI-CUSTOM 2026-11-03):python -m app.extensions.bid_review.golden
--report md [--out report.json]。加载失败/有题失败 → exit 1,成绩单仍完整输出(spec §11)。"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.extensions.bid_review.golden.loader import load_cases
from app.extensions.bid_review.golden.report import build_report, render_markdown
from app.extensions.bid_review.golden.runner import run_all


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="golden")
    ap.add_argument("--report", default="md", choices=["md"])
    ap.add_argument("--out", default=None, help="JSON 落盘路径")
    args = ap.parse_args(argv)
    try:
        cases = load_cases()
    except Exception as exc:  # noqa: BLE001
        print(f"题库加载失败: {exc}", file=sys.stderr)
        return 1
    results = asyncio.run(run_all(cases))
    rep = build_report(results, cases)
    print(render_markdown(rep))
    if args.out:
        Path(args.out).write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if rep["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
