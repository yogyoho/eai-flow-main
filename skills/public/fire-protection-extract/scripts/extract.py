#!/usr/bin/env python3
"""按映射契约从 structure.json 逐字摘抄组装消防专篇 Markdown。

Each source atom:
  para  -> 按段落索引逐字复制（paras: [i]）
  range -> 按闭区间逐段复制（paras: [from, to]）
  table -> 按 no 取整表，渲染为 Markdown 表
未命中 → 显式 [⚠未找到...] 标记。
class=template -> 输出 mapping.templates[name]；class=compute -> 输出 [需计算]。

段落索引由 E3 工作流中的 LLM 分析 structure.json 后生成——不在此引擎中做字符串
匹配。引擎只做一件事：按给定的段落区间逐字复制。
"""
import json
import sys
from pathlib import Path


def table_md(t):
    rows = t["rows"]
    if not rows:
        return ""

    def _flat(cell):
        return cell.replace("\n", " ")

    head = [_flat(c) for c in rows[0]]
    out = ["| " + " | ".join(head) + " |",
           "|" + "|".join(["---"] * len(head)) + "|"]
    for r in rows[1:]:
        out.append("| " + " | ".join(_flat(c) for c in r) + " |")
    return "\n".join(out)


def extract(structure, mapping):
    paras, tables = structure["paras"], structure["tables"]
    lines, citations = [], []
    n_paras = len(paras)

    for sec in mapping["sections"]:
        lines.append("")
        level = sec.get("heading_level", 2)
        prefix = "#" * level
        lines.append(f"{prefix} {sec['fire']}")
        lines.append("")
        cls = sec.get("class")
        if cls == "heading":
            continue
        if cls == "template":
            tpl = (mapping.get("templates") or {}).get(sec.get("template"))
            if tpl is None:
                lines.append(f"[⚠未找到模板: {sec.get('template') or '<未指定>'}]")
            else:
                lines.append(tpl.rstrip())
            lines.append("")
            continue
        if cls == "compute":
            lines.append(f"[需计算] {sec.get('note', '')}")
            lines.append("")
            continue

        sources = sec.get("sources", []) or []
        src_ref = sec.get("source_label", "设计说明书")

        for src in sources:
            kind = src.get("kind")
            idxs = src.get("paras")

            # backward-compat: "para_run" is the pre-migration name for "range"
            resolved_kind = "range" if kind == "para_run" else kind

            if resolved_kind == "para" and idxs and len(idxs) >= 1 and 0 <= idxs[0] < n_paras:
                p = paras[idxs[0]]
                lines.append(p["text"])
                lines.append(f"> 源: {src_ref} ¶{p['i']}")
                citations.append((sec["fire"], "¶", p["i"], str(idxs[0])))

            elif resolved_kind == "range" and idxs and len(idxs) >= 2 and 0 <= idxs[0] < n_paras and idxs[1] < n_paras:
                start, end = idxs[0], idxs[1]
                for p in paras[start:end + 1]:
                    lines.append(p["text"])
                    lines.append("")
                lines.append(f"> 源: {src_ref} ¶{paras[start]['i']}-{paras[end]['i']}")
                citations.append((sec["fire"], "¶run", (paras[start]["i"], paras[end]["i"]), str(idxs)))

            elif kind == "table":
                no = src.get("no", "")
                t = tables.get(no)
                if t:
                    lines.append(table_md(t))
                    lines.append(f"> 源: {src_ref} {no}")
                    citations.append((sec["fire"], "表", no, ""))
                else:
                    lines.append(f"[⚠未找到表: {no}]")

            elif resolved_kind in ("para", "range"):
                lines.append(f"[⚠未找到段落: {idxs}]")

            else:
                lines.append(f"[⚠未知源类型: {kind or '<未指定>'}]")

            lines.append("")

    return "\n".join(lines).strip(), citations


def build_report(structure, mapping, project_name="XX"):
    body, _ = extract(structure, mapping)
    title = mapping.get("report_title", "{项目名} 消防设计专篇")
    if "{项目名}" in title:
        title = title.replace("{项目名}", project_name)
    else:
        parts = title.split(None, 1)
        rest = parts[1] if len(parts) > 1 else ""
        title = f"{project_name} {rest}".rstrip()
    return f"# {title}\n\n{body}\n"


def _load_mapping(path_str):
    """Load mapping from .json or .yaml.  Prefer .json (stdlib); fall back to .yaml (needs PyYAML)."""
    p = Path(path_str)
    text = p.read_text(encoding="utf-8")
    # Try JSON first (covers .json and extensionless paths)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fall back to YAML
    import yaml
    return yaml.safe_load(text)


def main(argv):
    if len(argv) != 3:
        print("usage: extract.py <structure.json> <mapping.json|.yaml> <report.md>", file=sys.stderr)
        return 2
    structure = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    mapping = _load_mapping(argv[1])
    report = build_report(structure, mapping)
    Path(argv[2]).write_text(report, encoding="utf-8")
    print(f"OK -> {argv[2]} ({len(report)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
