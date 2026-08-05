#!/usr/bin/env python3
"""按阶段大纲 + 项目映射 逐字摘抄组装消防专篇 Markdown。

大纲 outline = 阶段骨架：sections[].{fire,class,heading_level,template,note,guide} + templates{}。
映射 mapping = 项目锚点：sources[] 与 outline.sections 按索引对齐（无源的节为 null 或 []）。

Each source atom:
  para  -> 按段落索引逐字复制（paras: [i]）
  range -> 按闭区间逐段复制（paras: [from, to]）
  table -> 按 no 取整表，渲染为 Markdown 表
未命中 → 显式 [⚠未找到...] 标记。
class=template -> 输出 outline.templates[name]；class=compute -> 输出 [需计算]。
段落索引由 E3 工作流中的 LLM 分析 structure.json 后生成——引擎只按给定索引逐字复制，
不做字符串匹配（字符串锚格式已废弃，见 extractor_rules.md）。
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


def extract(structure, outline, mapping):
    paras, tables = structure["paras"], structure["tables"]
    lines, citations = [], []
    n_paras = len(paras)
    sections = outline.get("sections", [])
    sources_by_idx = mapping.get("sources", [])

    for idx, sec in enumerate(sections):
        lines.append("")
        level = sec.get("heading_level", 2)
        lines.append(f"{'#' * level} {sec['fire']}")
        lines.append("")
        cls = sec.get("class")
        if cls == "heading":
            continue
        if cls == "template":
            tpl = (outline.get("templates") or {}).get(sec.get("template"))
            lines.append(tpl.rstrip() if tpl else f"[⚠未找到模板: {sec.get('template') or '<未指定>'}]")
            lines.append("")
            continue
        if cls == "compute":
            lines.append(f"[需计算] {sec.get('note', '')}")
            lines.append("")
            continue

        src_ref = sec.get("source_label", "设计说明书")
        sources = sources_by_idx[idx] if idx < len(sources_by_idx) else []
        sources = sources or []
        if not isinstance(sources, list):  # 非列表源（如 dict/str）一律视为无源，防逐字遍历报错
            sources = []
        if not sources:
            lines.append("[⚠未找到段落]")
            lines.append("")
            continue
        for src in sources:
            kind = src.get("kind")
            idxs = src.get("paras")
            resolved_kind = "range" if kind == "para_run" else kind  # 旧别名兼容（format 校验已挡，兜底）
            if resolved_kind == "para" and idxs and len(idxs) >= 1 and 0 <= idxs[0] < n_paras:
                p = paras[idxs[0]]
                lines.append(p["text"])
                lines.append(f"> 源: {src_ref} ¶{p['i']}")
                citations.append((sec["fire"], "¶", p["i"], str(idxs[0])))
            elif resolved_kind == "range" and idxs and len(idxs) >= 2 and 0 <= idxs[0] < n_paras and 0 <= idxs[1] < n_paras and idxs[0] <= idxs[1]:
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
            else:
                lines.append(f"[⚠未找到段落: {idxs}]")
            lines.append("")

    return "\n".join(lines).strip(), citations


def build_report(structure, outline, mapping, project_name="XX"):
    body, _ = extract(structure, outline, mapping)
    title = outline.get("report_title", "{项目名} 消防设计专篇")
    title = title.replace("{项目名}", project_name)
    return f"# {title}\n\n{body}\n"


def _load_json(path_str):
    p = Path(path_str)
    text = p.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        import yaml
        return yaml.safe_load(text)


def main(argv):
    if len(argv) != 5:
        print("usage: extract.py <structure.json> <outline.json> <mapping.json|yaml> <report.md> <project_name>", file=sys.stderr)
        return 2
    structure = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    outline = _load_json(argv[1])
    mapping = _load_json(argv[2])
    report = build_report(structure, outline, mapping, project_name=argv[4])
    Path(argv[3]).write_text(report, encoding="utf-8")
    print(f"OK -> {argv[3]} ({len(report)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
