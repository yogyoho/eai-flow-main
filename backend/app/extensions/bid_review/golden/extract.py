"""抽取层金标准评分器(B立项 M0,spec 2026-11-04 §3,EAI-CUSTOM)。

标注集=人工读 walkthrough 原文真值(独立于模型输出);score_fields 对 fields dict
出逐检查 rows+summary;score_snapshots 用冻结 R6 快照离线评分(零配额)做回归地板;
--live 经 worker._default_extract_fn 单次活体抽取并评分(切片边界用,烧一次配额)。
基线铁律:pass_rate 不得低于 annotations.meta.baseline_pass_rate(只升不降),
翻红=回归证据(标注错改标注/引擎错先修引擎)。
CLI: python -m app.extensions.bid_review.golden.extract [--live] [--update-baseline]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.extensions.bid_review.engine.attachments import normalize_name

_CASES = Path(__file__).resolve().parent / "extract_cases"
_ANNOTATIONS = _CASES / "walkthrough-annotations.json"
_SNAPSHOT = _CASES / "r6-snapshot.json"
_NAME_KEYS = frozenset({"name"})


def load_annotations() -> dict[str, Any]:
    return json.loads(_ANNOTATIONS.read_text(encoding="utf-8"))


def load_snapshot() -> dict[str, Any]:
    return json.loads(_SNAPSHOT.read_text(encoding="utf-8"))


def _atom(value: Any) -> Any:
    """浅归一:字符串去空白/千分位,数值字符串→数值;dict 递归。"""
    if isinstance(value, dict):
        return {k: _atom(v) for k, v in value.items()}
    if value is None or isinstance(value, bool) or isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        s = value.strip().replace(",", "")
        if s:
            try:
                return float(s) if "." in s else int(s)
            except ValueError:
                return s
        return ""
    return value


def _eq(got: Any, expect: Any) -> bool:
    return _atom(got) == _atom(expect)


def _item_match(item: Any, expect: dict) -> bool:
    """contains 的 dict 项子集匹配:name 键走 normalize_name+双向子串容忍,其余浅归一等值。"""
    if not isinstance(item, dict):
        return False
    for key, want in expect.items():
        got = item.get(key)
        if key in _NAME_KEYS:
            g, w = normalize_name(got), normalize_name(want)
            if not g or not w or not (w in g or g in w):
                return False
        elif not _eq(got, want):
            return False
    return True


def _check(fields: dict[str, Any], chk: dict) -> dict[str, Any]:
    path, kind, expect = chk["path"], chk["kind"], chk["expect"]
    got = fields.get(path)
    ok = False
    if kind == "value":
        ok = got is not None and _eq(got, expect)
    elif kind == "count":
        ok = isinstance(got, list) and len(got) == expect
    elif kind == "contains":
        if isinstance(got, list):
            if isinstance(expect, dict):
                ok = any(_item_match(i, expect) for i in got)
            else:
                ok = any(_eq(i, expect) for i in got)
    elif kind == "shape":
        keys = expect.get("keys", [])
        min_len = expect.get("min_len", 1)
        ok = isinstance(got, list) and len(got) >= min_len and all(isinstance(i, dict) and all(k in i for k in keys) for i in got)
    return {"path": path, "kind": kind, "verdict": "pass" if ok else "fail", "expect": expect, "got": None if ok else _atom(got)}


def score_fields(fields: dict[str, Any], annotations: dict) -> dict[str, Any]:
    rows = [_check(fields or {}, c) for c in annotations["checks"]]
    passed = sum(1 for r in rows if r["verdict"] == "pass")
    total = len(rows)
    return {
        "rows": rows,
        "summary": {"total": total, "passed": passed, "failed": total - passed, "pass_rate": round(passed / total, 4) if total else 0.0},
    }


def score_snapshots() -> dict[str, Any]:
    """离线回归地板:冻结 R6 快照 vs 标注集,零配额。"""
    return score_fields(load_snapshot()["fields"], load_annotations())


def score_live() -> dict[str, Any]:
    """单次活体抽取并评分(worker 生产 extract_fn,烧一次配额,切片边界用)。"""
    from app.extensions.bid_review.engine.extract import build_baseline
    from app.extensions.bid_review.worker import _default_extract_fn

    docs = [{"doc_id": name, "role": role, "text": (_CASES / name).read_text(encoding="utf-8")} for name, role in (("walkthrough-tender.md", "tender"), ("walkthrough-bid.md", "bid"))]
    baseline = build_baseline(docs, _default_extract_fn())
    return score_fields(baseline["fields"], load_annotations())


def _render(rep: dict) -> str:
    s = rep["summary"]
    lines = ["# 抽取金标准成绩单", "", f"passed {s['passed']}/{s['total']}  pass_rate {s['pass_rate']}  failed {s['failed']}"]
    for r in rep["rows"]:
        if r["verdict"] == "fail":
            lines.append(f"FAIL [{r['kind']}] {r['path']} expect={r['expect']!r} got={r['got']!r}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="golden-extract")
    ap.add_argument("--live", action="store_true", help="单次活体抽取并评分(烧一次配额)")
    ap.add_argument("--update-baseline", action="store_true", help="把本次 pass_rate 写入标注集 meta(只升不降)")
    args = ap.parse_args(argv)
    rep = score_live() if args.live else score_snapshots()
    print(_render(rep))
    ann = load_annotations()
    baseline = ann["meta"].get("baseline_pass_rate")
    if args.update_baseline:
        cur = rep["summary"]["pass_rate"]
        if baseline is not None and cur < baseline:
            print(f"拒绝降基线: 当前 {cur} < 基线 {baseline}", file=sys.stderr)
            return 1
        ann["meta"]["baseline_pass_rate"] = cur
        _ANNOTATIONS.write_text(json.dumps(ann, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"baseline_pass_rate -> {cur}")
        return 0
    if baseline is not None and rep["summary"]["pass_rate"] < baseline:
        print(f"低于基线: {rep['summary']['pass_rate']} < {baseline}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
