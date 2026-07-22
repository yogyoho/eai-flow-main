"""Extract project-level fields (name, location) from OCR'd first-page text.

Scanned-contract cover/front pages usually carry a form like
``项目名称：XXX`` / ``工程地点：YYY``. The OCR service joins text boxes with
newlines, so a label and its value may share a line (``项目名称：桂北数据中心``)
or split across two boxes (``项目名称`` / ``桂北数据中心``). We try same-line
first, then an exact-label line whose value is the next non-empty line.

Anything we cannot anchor on returns None — the management UI offers manual
entry as the fallback (the pipeline marks such docs needs_review elsewhere).
"""

from __future__ import annotations

import re

# Order matters: earlier labels win when several match the same text.
_NAME_LABELS = ["项目名称", "工程名称", "合同名称"]
_LOC_LABELS = [
    "工程地点",
    "项目所在地",
    "建设地点",
    "项目地点",
    "施工地点",
    "工程地址",
    "项目地址",
]
_CONTRACT_LABELS = ["合同编号", "合同号"]

# label[:：、 ]value on one line.
_LINE = {
    lbl: re.compile(rf"{lbl}\s*[:：、]\s*([^\n\r]+)")
    for lbl in set(_NAME_LABELS) | set(_LOC_LABELS)
}
# contract number is alphanumeric+dashes (e.g. 101448206-1GS-GZ09-0105-2025-0021).
_CONTRACT_LINE = {
    lbl: re.compile(rf"{lbl}\s*[:：]\s*([A-Za-z0-9\-]+)") for lbl in _CONTRACT_LABELS
}


def _clean(v: str | None) -> str | None:
    if not v:
        return None
    v = v.strip().strip("：:、 \t。.")
    # a value that collapses back to a known label (e.g. "项目名称：工程名称")
    # is a misread, not a real value.
    return v or None


def _find(text: str, labels: list[str]) -> str | None:
    for lbl in labels:
        m = _LINE[lbl].search(text)
        if m:
            val = _clean(m.group(1))
            if val:
                return val
    # split-line fallback: a line that IS the label (trailing colon ok) → value
    # is the next non-empty line.
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    labelset = set(labels)
    for i, ln in enumerate(lines):
        if ln.rstrip(":：、 ") in labelset and i + 1 < len(lines):
            val = _clean(lines[i + 1])
            if val:
                return val
    return None


def _find_contract(text: str) -> str | None:
    for lbl in _CONTRACT_LABELS:
        m = _CONTRACT_LINE[lbl].search(text)
        if m:
            return m.group(1)
    return None


def extract_project_fields(page_texts: dict[int, str]) -> tuple[str | None, str | None, str | None]:
    """Search the front-page OCR text for project name + location + contract no.

    page_texts: {page_no: text} (already limited to the first few pages by the
    OCR service). Returns (project_name, project_location, contract_no); any may
    be None. contract_no is propagated to items' source_contract_no.
    """
    blob = "\n".join(t for _, t in sorted(page_texts.items()) if t)
    if not blob:
        return None, None, None
    return _find(blob, _NAME_LABELS), _find(blob, _LOC_LABELS), _find_contract(blob)


if __name__ == "__main__":  # ponytail self-check: regex must catch common forms
    cases = [
        ({"1": "项目名称：桂北数据中心专业分包工程\n工程地点：桂北市\n合同编号：HT-2025-001"}, ("桂北数据中心专业分包工程", "桂北市", "HT-2025-001")),
        ({"1": "项目名称\n桂北数据中心\n建设地点：\n桂北"}, ("桂北数据中心", "桂北", None)),
        ({"1": "合同名称：某合同\n项目所在地\n桂北高新区"}, ("某合同", "桂北高新区", None)),
        ({"1": "无标签封面文本"}, (None, None, None)),
    ]
    for pt, want in cases:
        got = extract_project_fields(pt)
        assert got == want, f"{pt!r} → {got}, want {want}"
    print("ok")
