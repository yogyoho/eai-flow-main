#!/usr/bin/env python3
"""设计说明书 .docx → 带稳定 ID 的结构 JSON（{paras, tables}）。

按文档顺序遍历段落与表格（python-docx 的 doc.paragraphs/doc.tables 是两个独立列表，
丢失顺序；这里直接遍历 body XML 子元素拿到交错的段落+表格）。
表格按其前一个段落里的「表X.Y-Z」题注建索引；段落带稳定序号 i。
不依赖 Word 标题样式（样本里样式不一致），锚/区间定位交给上层 extract.py。
"""
import json
import re
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

TABLE_NO_RE = re.compile(r"^(表\s*\d[\d.\-]*[A-Za-z]?)\s*(.*)$")


def iter_block_items(doc):
    """Yield Paragraph/Table in document order."""
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield Table(child, doc)


def _norm_no(raw):
    return re.sub(r"\s+", "", raw)


def parse_spec(docx_path):
    doc = Document(str(docx_path))
    paras, tables = [], {}
    pending_no, pending_title = None, None
    for blk in iter_block_items(doc):
        if isinstance(blk, Paragraph):
            text = blk.text.strip()
            if not text:
                continue
            paras.append({"i": len(paras), "text": text})
            m = TABLE_NO_RE.match(text)
            if m:
                pending_no = _norm_no(m.group(1))
                pending_title = m.group(2).strip()
        elif isinstance(blk, Table):
            rows = [[c.text.strip() for c in row.cells] for row in blk.rows]
            no = pending_no or f"__auto{len(tables)}"
            tables[no] = {"title": pending_title or "", "rows": rows, "n_rows": len(rows)}
            pending_no, pending_title = None, None
    return {"paras": paras, "tables": tables}


def main(argv):
    if len(argv) != 2:
        print("usage: parse_spec.py <input.docx> <output.json>", file=sys.stderr)
        return 2
    data = parse_spec(argv[0])
    Path(argv[1]).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK paras={len(data['paras'])} tables={len(data['tables'])} -> {argv[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
