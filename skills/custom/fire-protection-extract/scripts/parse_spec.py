#!/usr/bin/env python3
"""设计说明书 .docx → 带稳定 ID 的结构 JSON（{paras, tables}）。

优先用 python-docx（结构好）；装不上就回退到标准库 zipfile+xml（永远可用）。
表格按其前一个段落里的「表X.Y-Z」题注建索引；段落带稳定序号 i。
不依赖 Word 标题样式（样本里样式不一致），锚/区间定位交给上层 extract.py。
"""
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

TABLE_NO_RE = re.compile(r"^(表\s*\d[\d.\-]*[A-Za-z]?)\s*(.*)$")
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _norm_no(raw):
    return re.sub(r"\s+", "", raw)


# ── python-docx path ──────────────────────────────────────────────

def _parse_with_docx(docx_path):
    from docx import Document
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(str(docx_path))
    paras, tables = [], {}
    pending_no, pending_title = None, None
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            text = Paragraph(child, doc).text.strip()
            if not text:
                continue
            paras.append({"i": len(paras), "text": text})
            m = TABLE_NO_RE.match(text)
            if m:
                pending_no = _norm_no(m.group(1))
                pending_title = m.group(2).strip()
        elif child.tag == qn("w:tbl"):
            tbl = Table(child, doc)
            rows = [[c.text.strip() for c in row.cells] for row in tbl.rows]
            no = pending_no or f"__auto{len(tables)}"
            tables[no] = {"title": pending_title or "", "rows": rows, "n_rows": len(rows)}
            pending_no, pending_title = None, None
    return {"paras": paras, "tables": tables}


# ── stdlib fallback (zipfile + xml) ───────────────────────────────

def _iter_body_children(docx_path):
    """Yield ('p', text) or ('tbl', rows) in document order (stdlib only)."""
    with zipfile.ZipFile(str(docx_path)) as z:
        xml_bytes = z.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    body = root.find(f"{{{W_NS}}}body")
    if body is None:
        return
    for child in body:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag == "p":
            parts = []
            for elem in child.iter():
                etag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if etag == "t":
                    parts.append(elem.text or "")
                elif etag == "tab":
                    parts.append("\t")
                elif etag == "br":
                    parts.append("\n")
            text = "".join(parts).strip()
            if text:
                yield ("p", text)
        elif tag == "tbl":
            rows = []
            for tr in child.iter(f"{{{W_NS}}}tr"):
                cells = []
                for tc in tr.iter(f"{{{W_NS}}}tc"):
                    cell_text = "".join(t.text or "" for t in tc.iter(f"{{{W_NS}}}t")).strip()
                    cells.append(cell_text)
                if cells:
                    rows.append(cells)
            if rows:
                yield ("tbl", rows)


def _parse_with_stdlib(docx_path):
    paras, tables = [], {}
    pending_no, pending_title = None, None
    for kind, payload in _iter_body_children(docx_path):
        if kind == "p":
            paras.append({"i": len(paras), "text": payload})
            m = TABLE_NO_RE.match(payload)
            if m:
                pending_no = _norm_no(m.group(1))
                pending_title = m.group(2).strip()
        elif kind == "tbl":
            no = pending_no or f"__auto{len(tables)}"
            tables[no] = {"title": pending_title or "", "rows": payload, "n_rows": len(payload)}
            pending_no, pending_title = None, None
    return {"paras": paras, "tables": tables}


# ── public API ────────────────────────────────────────────────────

def parse_spec(docx_path):
    try:
        from docx import Document  # noqa: F401
        return _parse_with_docx(docx_path)
    except ImportError:
        return _parse_with_stdlib(docx_path)


def main(argv):
    if len(argv) != 2:
        print("usage: parse_spec.py <input.docx> <output.json>", file=sys.stderr)
        return 2
    data = parse_spec(argv[0])
    Path(argv[1]).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    # detect which backend was used
    try:
        from docx import Document  # noqa: F401
        backend = "python-docx"
    except ImportError:
        backend = "stdlib(zipfile+xml)"
    print(f"OK [{backend}] paras={len(data['paras'])} tables={len(data['tables'])} -> {argv[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
