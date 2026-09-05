#!/usr/bin/env python3
"""Per-run tool-call sequences with consecutive-same-signature folding (xN).

Usage:
  python extract_sequences.py --events-dir events/ [--run 862aa466] [--max-line 60]
Output: JSON on stdout — per run: [{tool, sig, x}] folded runs plus totals.
Long retries (same command hitting a wall) collapse to one "x15" line.
"""

from __future__ import annotations

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import call_signature, iter_event_files, tool_calls_of  # noqa: E402


def fold(calls: list[dict]) -> list[dict]:
    out: list[dict] = []
    for c in calls:
        entry = {"tool": c["tool"], "sig": c["sig"]}
        if out and out[-1]["tool"] == entry["tool"] and out[-1]["sig"] == entry["sig"]:
            out[-1]["x"] += 1
        else:
            out.append({**entry, "x": 1})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events-dir", required=True)
    ap.add_argument("--run", help="只看某个 run (run8 前缀)")
    ap.add_argument("--max-line", type=int, default=60, help="每 run 最多输出行数 (默认 60, 超出截断)")
    args = ap.parse_args()

    seqs: dict[str, list[dict]] = {}
    for _fname, events in iter_event_files(args.events_dir):
        for ev in events:
            if ev.get("event_type") != "llm.ai.response":
                continue
            run8 = ev.get("run8", "?")
            for tc in tool_calls_of(ev):
                name = tc.get("name", "?")
                if not name:
                    continue
                a = tc.get("args") or {}
                seqs.setdefault(run8, []).append({"tool": name, "sig": call_signature(name, a if isinstance(a, dict) else {})})

    out_runs = []
    for run8 in sorted(seqs):
        if args.run and not run8.startswith(args.run):
            continue
        calls = seqs[run8]
        folded = fold(calls)
        out_runs.append(
            {
                "run8": run8,
                "total_calls": len(calls),
                "folded_lines": len(folded),
                "truncated": len(folded) > args.max_line,
                "sequence": folded[: args.max_line],
            }
        )
    print(json.dumps({"runs": out_runs}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
