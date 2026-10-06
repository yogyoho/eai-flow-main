#!/usr/bin/env python3
"""从后端源码生成文档中心两张易漂移表（MCP 工具总表 / 国标 C1-C5 对照表）。

用法: cd ontostudio/docs-site && python scripts/gen_reference_tables.py
只重写目标 md 内 <!-- GENERATED:KEY BEGIN/END --> 区间，区间外手写内容不触碰。
自检: python scripts/gen_reference_tables.py --selftest
"""
import ast
import pathlib
import re
import sys

DOCS = pathlib.Path(__file__).resolve().parents[1]          # docs-site/
BACKEND = DOCS.parent / "backend" / "app"                    # ontostudio/backend/app


def extract_tools_spec(path: pathlib.Path) -> list[tuple]:
    """ast 解析 _TOOLS_SPEC = [(name, desc, schema), ...]——把 Name 引用（如 _SCOPE_PARAM_SPEC）
    替换为占位串后 literal_eval，无需导入后端依赖。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "_TOOLS_SPEC":
            value = ast.NodeTransformer.generic_visit(_NameToPlaceholder(), node.value)
            return ast.literal_eval(value)
    raise ValueError(f"_TOOLS_SPEC not found in {path}")


class _NameToPlaceholder(ast.NodeTransformer):
    def visit_Name(self, node: ast.Name) -> ast.Constant:
        return ast.Constant(value=f"<{node.id}>")


def extract_conformance_rows() -> list[tuple[str, str, str, str]]:
    """解析 conformance.py 模块 docstring 的 C1-C5 行：按 2+ 空格切四段。"""
    src = (BACKEND / "ontology" / "kernel" / "conformance.py").read_text(encoding="utf-8")
    doc = ast.get_docstring(ast.parse(src)) or ""
    rows = []
    for line in doc.splitlines():
        if not re.match(r"\s*C[1-5]\s", line):
            continue
        parts = re.split(r"\s{2,}", line.strip())
        cid, clause = parts[0].split(" ", 1)
        rows.append((cid, clause, parts[1], parts[2]))
    if len(rows) != 5:
        raise ValueError(f"expected 5 conformance rows, got {len(rows)}")
    return rows


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def mcp_table() -> str:
    rows = ["| 工具 | 侧 | 用途 | 关键参数 |", "|---|---|---|---|"]
    for name, desc, schema in extract_tools_spec(BACKEND / "ontology" / "mcp.py"):
        req = ", ".join(schema.get("required", [])) or "—"
        rows.append(f"| `{name}` | 读 | {_cell(desc)} | {req} |")
    for name, desc, schema in extract_tools_spec(BACKEND / "doc_graph" / "mcp.py"):
        req = ", ".join(schema.get("required", [])) or "—"
        rows.append(f"| `{name}` | 写 | {_cell(desc)} | {req} |")
    return "\n".join(rows)


def conformance_table() -> str:
    rows = ["| 校验项 | 条款 | 校什么 | 通过标准（来源：conformance.py） |", "|---|---|---|---|"]
    for cid, clause, what, crit in extract_conformance_rows():
        rows.append(f"| {cid} | {clause} | {_cell(what)} | {_cell(crit)} |")
    return "\n".join(rows)


def replace_region(md_text: str, key: str, content: str) -> str:
    pat = re.compile(
        r"(<!-- GENERATED:%s BEGIN -->\n).*?(\n<!-- GENERATED:%s END -->)" % (key, key), re.S
    )
    if not pat.search(md_text):
        raise SystemExit(f"GENERATED region {key} not found")
    return pat.sub(lambda m: m.group(1) + content + m.group(2), md_text)


def selftest() -> None:
    onto = extract_tools_spec(BACKEND / "ontology" / "mcp.py")
    doc = extract_tools_spec(BACKEND / "doc_graph" / "mcp.py")
    assert len(onto) == 17, f"ontology tools {len(onto)} != 17"
    assert len(doc) == 5, f"doc_graph tools {len(doc)} != 5"
    rows = extract_conformance_rows()
    assert [r[0] for r in rows] == ["C1", "C2", "C3", "C4", "C5"]
    probe = "<!-- GENERATED:X BEGIN -->\nold\n<!-- GENERATED:X END -->"
    assert "new" in replace_region(probe, "X", "new") and "old" not in replace_region(probe, "X", "new")
    print("selftest OK: 17+5 tools, 5 conformance rows, region replace")


def main() -> None:
    if "--selftest" in sys.argv:
        selftest()
        return
    for rel, key, table in [
        ("reference/mcp-tools.md", "MCP-TOOLS", mcp_table()),
        ("reference/gbt-48000.md", "CONFORMANCE-TABLE", conformance_table()),
    ]:
        p = DOCS / rel
        p.write_text(replace_region(p.read_text(encoding="utf-8"), key, table), encoding="utf-8", newline="\n")
        print(f"regenerated region {key} in {rel}")


if __name__ == "__main__":
    main()
