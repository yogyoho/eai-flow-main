#!/usr/bin/env python3
"""Cluster tool failures by signature across all runs' events. Stats only.

Usage:
  python extract_failures.py --events-dir events/ [--top 15] [--samples 3]
Output: JSON on stdout — failures sorted by count desc:
  [{signature, count, runs:{run8:n}, first:{run8,seq}, last:{run8,seq}, samples:[...]}]
Every entry carries seq evidence ids so the report can cite them.
"""

from __future__ import annotations

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import classify_failure, iter_event_files, tool_result_text  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events-dir", required=True)
    ap.add_argument("--top", type=int, default=15, help="最多输出前 N 个签名 (默认 15)")
    ap.add_argument("--samples", type=int, default=2, help="每签名样本行数 (默认 2)")
    args = ap.parse_args()

    clusters: dict[str, dict] = {}
    for _fname, events in iter_event_files(args.events_dir):
        for ev in events:
            sig = classify_failure(ev)
            if sig is None:
                continue
            loc = {"run8": ev.get("run8", "?"), "seq": ev.get("seq")}
            c = clusters.setdefault(sig, {"signature": sig, "count": 0, "runs": {}, "first": loc, "last": loc, "samples": []})
            c["count"] += 1
            c["runs"][loc["run8"]] = c["runs"].get(loc["run8"], 0) + 1
            c["last"] = loc
            if len(c["samples"]) < args.samples:
                sample = tool_result_text(ev).strip().replace("\n", " ⏎ ")[:220]
                c["samples"].append({**loc, "text": sample})

    ranked = sorted(clusters.values(), key=lambda c: -c["count"])[: args.top]
    total = sum(c["count"] for c in clusters.values())
    print(json.dumps({"total_failures": total, "signatures": len(clusters), "clusters": ranked}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
