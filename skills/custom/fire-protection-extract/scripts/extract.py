#!/usr/bin/env python3
"""按映射契约从 structure.json 逐字摘抄组装消防专篇 Markdown。

每个 source 原子摘抄：
  para      -> 找到含 anchor 子串的源段，整段逐字复制
  para_run  -> 从含 from 的段到含 to 的段（闭区间），逐段复制
  table     -> 按 no 取整表，渲染为 Markdown 表
未命中锚/表 -> 显式 [⚠未找到...] 标记（绝不静默跳过，绝不编造）。
class=template -> 输出 mapping.templates[name]；class=compute -> 输出 [需计算]。
"""
import json
import sys
from pathlib import Path

import yaml


def find_para(paras, anchor):
    for p in paras:
        if anchor in p["text"]:
            return p
    return None


def find_run(paras, frm, to):
    start = next((i for i, p in enumerate(paras) if frm in p["text"]), None)
    if start is None:
        return None
    end = start
    for i in range(start, len(paras)):
        if to in paras[i]["text"]:
            end = i
            break
    else:
        end = len(paras) - 1
    return paras[start:end + 1]


def table_md(t):
    rows = t["rows"]
    if not rows:
        return ""
    head = rows[0]
    out = ["| " + " | ".join(head) + " |",
           "|" + "|".join(["---"] * len(head)) + "|"]
    for r in rows[1:]:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def extract(structure, mapping):
    paras, tables = structure["paras"], structure["tables"]
    lines, citations = [], []
    for sec in mapping["sections"]:
        lines.append("")
        lines.append(f"## {sec['fire']}")
        lines.append("")
        cls = sec.get("class")
        if cls == "template":
            tpl = (mapping.get("templates") or {}).get(sec.get("template"))
            if tpl:
                lines.append(tpl.rstrip())
                lines.append("")
            continue
        if cls == "compute":
            lines.append(f"[需计算] {sec.get('note', '')}")
            lines.append("")
            continue
        for src in sec.get("sources", []) or []:
            kind = src["kind"]
            if kind == "para":
                p = find_para(paras, src["anchor"])
                if p:
                    lines.append(p["text"])
                    lines.append(f"<!-- 源:¶{p['i']} -->")
                    citations.append((sec["fire"], "¶", p["i"], src["anchor"]))
                else:
                    lines.append(f"[⚠未找到锚: {src['anchor'][:24]}…]")
            elif kind == "para_run":
                run = find_run(paras, src["from"], src["to"])
                if run:
                    for p in run:
                        lines.append(p["text"])
                    lines.append(f"<!-- 源:¶{run[0]['i']}-{run[-1]['i']} -->")
                    citations.append((sec["fire"], "¶run", (run[0]["i"], run[-1]["i"]), src["from"]))
                else:
                    lines.append(f"[⚠未找到区间: {src['from'][:24]}…]")
            elif kind == "table":
                t = tables.get(src["no"])
                if t:
                    lines.append(table_md(t))
                    lines.append(f"<!-- 源:{src['no']} -->")
                    citations.append((sec["fire"], "表", src["no"], ""))
                else:
                    lines.append(f"[⚠未找到表: {src['no']}]")
            lines.append("")
    return "\n".join(lines).strip(), citations


def build_report(structure, mapping, project_name="XX"):
    body, _ = extract(structure, mapping)
    title = mapping.get("report_title", "{项目名} 消防设计专篇")
    if "{项目名}" in title:
        title = title.replace("{项目名}", project_name)
    else:
        # 无显式 {项目名} 占位符时，视首词为项目名槽
        # （如 "T 消防设计专篇" -> "<项目名> 消防设计专篇"）。
        parts = title.split(None, 1)
        rest = parts[1] if len(parts) > 1 else ""
        title = f"{project_name} {rest}".rstrip()
    return f"# {title}\n\n{body}\n"


def main(argv):
    if len(argv) != 3:
        print("usage: extract.py <structure.json> <mapping.yaml> <report.md>", file=sys.stderr)
        return 2
    structure = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    mapping = yaml.safe_load(Path(argv[1]).read_text(encoding="utf-8"))
    report = build_report(structure, mapping)
    Path(argv[2]).write_text(report, encoding="utf-8")
    print(f"OK -> {argv[2]} ({len(report)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
