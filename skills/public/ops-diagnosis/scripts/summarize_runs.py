#!/usr/bin/env python3
"""Per-run metrics from runs.json + events dir. Stats only, no judgment.

Usage:
  python summarize_runs.py --runs runs.json --events-dir events/
Output: JSON on stdout — per-run {status, stop_reason, tokens, llm_calls,
event/tool counts, failure_count, first/last event time} + thread totals.
"""

from __future__ import annotations

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import classify_failure, iter_event_files, tool_calls_of  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True, help="ops_list_thread_runs 响应保存的 runs.json")
    ap.add_argument("--events-dir", required=True, help="各 run 事件文件目录")
    args = ap.parse_args()

    runs_payload = json.load(open(args.runs, encoding="utf-8"))
    runs = runs_payload.get("runs") if isinstance(runs_payload, dict) else runs_payload

    per_run_events: dict[str, list[dict]] = {}
    for _fname, events in iter_event_files(args.events_dir):
        for ev in events:
            per_run_events.setdefault(ev.get("run8", "?"), []).append(ev)

    out_runs = []
    totals = {"runs": 0, "error_runs": 0, "total_tokens": 0, "llm_calls": 0, "events": 0, "tool_calls": 0, "failures": 0}
    for r in runs:
        run8 = (r.get("run_id") or "")[:8]
        evs = sorted(per_run_events.get(run8, []), key=lambda e: e.get("seq", 0))
        failures = sum(1 for e in evs if classify_failure(e))
        tcs = sum(len(tool_calls_of(e)) for e in evs if e.get("event_type") == "llm.ai.response")
        out_runs.append(
            {
                "run8": run8,
                "status": r.get("status"),
                "stop_reason": r.get("stop_reason"),
                "total_tokens": r.get("total_tokens"),
                "llm_call_count": r.get("llm_call_count"),
                "run_event_count": r.get("event_count"),
                "loaded_events": len(evs),
                "tool_calls": tcs,
                "failure_count": failures,
                "first_event_at": evs[0]["created_at"] if evs else None,
                "last_event_at": evs[-1]["created_at"] if evs else None,
            }
        )
        totals["runs"] += 1
        totals["error_runs"] += 1 if r.get("status") == "error" else 0
        totals["total_tokens"] += r.get("total_tokens") or 0
        totals["llm_calls"] += r.get("llm_call_count") or 0
        totals["events"] += r.get("event_count") or 0
        totals["tool_calls"] += tcs
        totals["failures"] += failures

    print(json.dumps({"runs": out_runs, "totals": totals}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
