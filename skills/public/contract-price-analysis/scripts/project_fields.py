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
# Supplier = the performing party (乙方/分包方/承包方...). 甲方 is the buyer (总包),
# NOT the supplier whose prices we analyze, so it's excluded.
_SUPPLIER_LABELS = ["分包方", "乙方", "承包方", "承包人", "分包人", "施工单位", "供方", "供应商"]
_DATE_LABELS = [
    "合同签订日期", "签订日期", "签署日期", "签订时间", "签署时间", "签定日期", "合同签定日期",
]

# label[:：、 ]value on one line.
_LINE = {
    lbl: re.compile(rf"{lbl}\s*[:：、]\s*([^\n\r]+)")
    for lbl in set(_NAME_LABELS) | set(_LOC_LABELS) | set(_SUPPLIER_LABELS) | set(_DATE_LABELS)
}
# a date in 年月日 or numeric form (normalized to YYYY-MM-DD by _parse_date).
_DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日|(\d{4})[-/](\d{1,2})[-/](\d{1,2})")
# label + OPTIONAL separator + date captured directly — so a space separator
# ('签署日期 2025-06-18') works without a colon, not just '签订日期：...'.
_DATE_AFTER_LABEL = {
    lbl: re.compile(
        rf"{lbl}\s*[:：、]?\s*(\d{{4}}\s*年\s*\d{{1,2}}\s*月\s*\d{{1,2}}\s*日|\d{{4}}[-/]\d{{1,2}}[-/]\d{{1,2}})"
    )
    for lbl in _DATE_LABELS
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


def _parse_date(s: str | None) -> str | None:
    """Normalize a date string to YYYY-MM-DD (handles 年月日 + numeric). None if none."""
    m = _DATE_RE.search(s or "")
    if not m:
        return None
    if m.group(1):  # 年月日 form
        y, mo, d = m.group(1), m.group(2), m.group(3)
    else:  # numeric form
        y, mo, d = m.group(4), m.group(5), m.group(6)
    try:
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    except (ValueError, TypeError):
        return None


def _find_date(text: str) -> str | None:
    """Find a signature date anchored on a 签订/签署 label (same-line, with or
    without a colon) or the next non-empty line, normalized to YYYY-MM-DD."""
    for lbl in _DATE_LABELS:
        m = _DATE_AFTER_LABEL[lbl].search(text)
        if m:
            d = _parse_date(m.group(1))
            if d:
                return d
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    labelset = set(_DATE_LABELS)
    for i, ln in enumerate(lines):
        if ln.rstrip(":：、 ") in labelset and i + 1 < len(lines):
            d = _parse_date(lines[i + 1])
            if d:
                return d
    return None


def _valid_supplier(v: str | None) -> bool:
    """Reject obvious mis-extractions: seal fragments like '（盖' (from '（盖章）'
    split by OCR), too-short values, or bare seal words. Real supplier names are
    company names (≥3 chars, don't start with a parenthesis)."""
    if not v or len(v) < 3:
        return False
    if v[0] in "（(":
        return False
    if v in ("盖章", "公章", "合同专用章"):
        return False
    return True


def extract_project_fields(page_texts: dict[int, str]) -> tuple:
    """Search the front-page OCR text for project name + location + contract no
    + supplier + sign_date.

    page_texts: {page_no: text} (already limited to the first few pages by the
    OCR service). Returns (project_name, project_location, contract_no, supplier,
    sign_date); any may be None. sign_date is normalized to YYYY-MM-DD.
    contract_no is propagated to items' source_contract_no.
    """
    blob = "\n".join(t for _, t in sorted(page_texts.items()) if t)
    if not blob:
        return None, None, None, None, None
    supplier = _find(blob, _SUPPLIER_LABELS)
    if not _valid_supplier(supplier):
        supplier = None  # reject seal fragments / too-short → manual fill
    return (
        _find(blob, _NAME_LABELS),
        _find(blob, _LOC_LABELS),
        _find_contract(blob),
        supplier,
        _find_date(blob),
    )


if __name__ == "__main__":  # ponytail self-check: regex must catch common forms
    cases = [
        ({"1": "项目名称：桂北数据中心专业分包工程\n工程地点：桂北市\n合同编号：HT-2025-001\n乙方：桂北建工有限公司\n签订日期：2025年6月18日"},
         ("桂北数据中心专业分包工程", "桂北市", "HT-2025-001", "桂北建工有限公司", "2025-06-18")),
        ({"1": "项目名称\n桂北数据中心\n建设地点：\n桂北\n分包方：XX公司\n签署日期 2025-06-18"},
         ("桂北数据中心", "桂北", None, "XX公司", "2025-06-18")),
        ({"1": "合同名称：某合同\n项目所在地\n桂北高新区"}, ("某合同", "桂北高新区", None, None, None)),
        ({"1": "无标签封面文本"}, (None, None, None, None, None)),
        # supplier = seal fragment '（盖章）' (OCR split '（盖'+'章）') → rejected (None)
        ({"1": "乙方\n（盖章）"}, (None, None, None, None, None)),
    ]
    for pt, want in cases:
        got = extract_project_fields(pt)
        assert got == want, f"{pt!r} → {got}, want {want}"
    print("ok")
