"""源①：26 份 outline digest → 术语提名频次 + report_type 归类。零 LLM 成本。

用法：python digest_stats.py [--src .wolf/tmp/eia-samples] [--out out/digest_stats.json]
产物：JSON {per_report: [{file, report_type, term_hits: {term: count}}], totals: {term: count}}

report_type 归类（实际语料文件名是拼音 slug、无中文关键词，纯 stem 归类全落 unknown）：
① digest 头部自带「场景判定」英文 token（planning_eia/project_eia/post_assessment）→ 直接采信；
② 否则按 REPORT_TYPE_KEYWORDS 逐级放宽：文件名 stem → 首行标题 → 前 12 行封面/元信息块。
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

from coal_terms import COAL_TERMS, REPORT_TYPE_KEYWORDS

HEADING = re.compile(r"^\s*(#{1,6})\s*(\d+(?:\.\d+)*)\s*(\S.*)$", re.MULTILINE)
TYPE_TOKEN = re.compile(r"(planning_eia|post_assessment|project_eia)")
TOKEN_WINDOW = 40   # 场景判定 token 只认头部 N 行（正文提及不计）
META_BLOCK = 12     # 无 token 时元信息块放宽到的行数


def classify(title: str) -> str:
    for rtype, kws in REPORT_TYPE_KEYWORDS.items():
        if any(k in title for k in kws):
            return rtype
    return "unknown"


def report_type_of(path: Path, text: str) -> str:
    """digest 自报 token 优先，stem→标题→元信息块逐级放宽。"""
    declared = TYPE_TOKEN.search("\n".join(text.splitlines()[:TOKEN_WINDOW]))
    if declared:
        return declared.group(1)
    lines = text.splitlines()
    cands = (path.stem, lines[0] if lines else "", "\n".join(lines[:META_BLOCK]))
    for cand in cands:
        rtype = classify(cand)
        if rtype != "unknown":
            return rtype
    return "unknown"


def scan_digest(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    hits: Counter[str] = Counter()
    for term in COAL_TERMS:
        hits[term] = len(re.findall(re.escape(term), text))
    headings = [m.group(0).strip() for m in HEADING.finditer(text)]
    return {
        "file": path.name,
        "report_type": report_type_of(path, text),
        "headings": len(headings),
        "term_hits": {t: c for t, c in hits.items() if c},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=".wolf/tmp/eia-samples")
    ap.add_argument("--out", default="out/digest_stats.json")
    args = ap.parse_args()
    digests = sorted(Path(args.src).glob("*-outline.md"))
    per = [scan_digest(p) for p in digests]
    totals: Counter[str] = Counter()
    for r in per:
        totals.update(r["term_hits"])
    out = {"per_report": per, "totals": dict(totals.most_common()),
           "report_types": dict(Counter(r["report_type"] for r in per))}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(per)} digests → {args.out}; report_types={out['report_types']}")


if __name__ == "__main__":
    main()
