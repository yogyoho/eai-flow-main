#!/usr/bin/env python3
"""Detect design stage (初步设计/基础设计) from a parsed structure.

Only reads document text; explicit user override is applied by run.sh.
"""
import json
import sys

DEFAULT_STAGE = "基础设计"
# 标题页阶段标记出现在文档前几十段；60 是封面+审批页+目录的保守窗口。
SCAN_WINDOW = 60


def _has_only(t: str, stage: str) -> bool:
    other = "基础设计" if stage == "初步设计" else "初步设计"
    return stage in t and other not in t


def detect_from_struct(struct: dict) -> str:
    # 标题页标记出现在前 SCAN_WINDOW 段；body 段超窗会被跳过，headings 兜底仍能命中。
    # 注：子串匹配对"扩大初步设计"等旧术语会有误判（含"初步设计"子串），本语料可接受。
    for p in struct.get("paras", [])[:SCAN_WINDOW]:
        t = p.get("text", "")
        if _has_only(t, "初步设计"):
            return "初步设计"
        if _has_only(t, "基础设计"):
            return "基础设计"
    for h in struct.get("headings", []):
        t = h.get("text", "")
        if _has_only(t, "初步设计"):
            return "初步设计"
        if _has_only(t, "基础设计"):
            return "基础设计"
    return DEFAULT_STAGE


def main(argv):
    if len(argv) != 1:
        print("usage: detect_stage.py <structure.json>", file=sys.stderr)
        return 2
    struct = json.loads(open(argv[0], encoding="utf-8").read())
    print(detect_from_struct(struct))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
