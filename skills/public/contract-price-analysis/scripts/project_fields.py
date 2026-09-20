"""Extract project-level fields (name, location) from OCR'd first-page text.

Scanned-contract cover/front pages usually carry a form like
``项目名称：XXX`` / ``工程地点：YYY``. The OCR service joins text boxes with
newlines, so a label and its value may share a line (``项目名称：桂北数据中心``)
or split across two boxes (``项目名称`` / ``桂北数据中心``). We try same-line
first, then an exact-label line whose value is the next non-empty line (guarded:
a next line that itself looks like a label is a neighbor label, not a value).
Contract numbers may additionally live inside a parsed table cell
(``合同编号：XXX``) invisible to the text layer — ``find_contract_from_tables``
covers that as the text-path miss fallback (方案A, forensics-verified).

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
# NOT the supplier whose prices we analyze, so it's excluded. 卖方 = seller in
# 买方/卖方 补充协议 form (买方 is the buyer — not added).
_SUPPLIER_LABELS = ["分包方", "乙方", "承包方", "承包人", "分包人", "施工单位", "供方", "供应商", "卖方"]
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
# F2a 表格 cell 兜底(方案A,取证仿真已验证): '项目合同编号' 先于 '合同编号' 搜,
# 避免子串重复命中;含审批/招标编号字样的格是招标/审批流水号诱饵,整格跳过。
_TABLE_CONTRACT_LABELS = ["项目合同编号", "合同编号"]
_TABLE_CONTRACT_BAD = ("审批编号", "招标编号")
# 全值形态: 字母数字开头,主体仅字母数字+连字符,总长>=6;dash 段数另门(>=3)。
_CONTRACT_SHAPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-]{5,}$")
# F2b split-line 守卫: 候选值行本身含任何已知标签词 → 它是相邻标签不是值
# (砂石料 '合同名称' 下一行 '局审批编号' 被误当项目名)。
_KNOWN_LABELS = frozenset(
    set(_NAME_LABELS) | set(_LOC_LABELS) | set(_CONTRACT_LABELS)
    | set(_SUPPLIER_LABELS) | set(_DATE_LABELS) | set(_TABLE_CONTRACT_BAD)
)


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
    # is the next non-empty line — unless that line itself contains a known
    # label word (F2b: it's a neighboring label, e.g. 砂石料 '局审批编号').
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    labelset = set(labels)
    for i, ln in enumerate(lines):
        if ln.rstrip(":：、 ") in labelset and i + 1 < len(lines):
            cand = lines[i + 1]
            if any(lbl in cand for lbl in _KNOWN_LABELS):
                continue
            val = _clean(cand)
            if val:
                return val
    return None


def _find_contract(text: str) -> str | None:
    for lbl in _CONTRACT_LABELS:
        m = _CONTRACT_LINE[lbl].search(text)
        if m:
            return m.group(1)
    return None


def find_contract_from_tables(tables) -> str | None:
    """F2a: contract number hiding in a parsed table cell (文本路 miss 时兜底).

    砂石料的编号只在 p10 会签表 cell ('项目合同编号：2GS-…') 里,文本层扫不到。
    门(按序,方案A): ①整格含 '审批编号'/'招标编号' → 跳过(流水号诱饵);
    ②'项目合同编号' 先于 '合同编号' 搜(避免子串重复命中);③同 cell 内冒号必需;
    ④冒号后整段须过 _CONTRACT_SHAPE 且 dash 段数>=3 —— 上浦 p3 OCR 粘连截断值
    ('…-011-20 包合同段项目经理部')由④挡住。取首个命中。

    tables 是 TableExtract(.rows)或等价 dict({"rows": …});纯只读,不触
    table_classifier 的 seed 语义。
    """
    for t in tables or []:
        rows = getattr(t, "rows", None)
        if rows is None and isinstance(t, dict):
            rows = t.get("rows")
        for row in rows or []:
            for cell in row:
                txt = str(cell)
                if any(b in txt for b in _TABLE_CONTRACT_BAD):
                    continue
                for lbl in _TABLE_CONTRACT_LABELS:
                    i = txt.find(lbl)
                    if i < 0:
                        continue
                    rest = txt[i + len(lbl):].lstrip()
                    if not rest.startswith((":", "：")):
                        continue
                    val = rest[1:].strip()
                    if val and _CONTRACT_SHAPE.match(val) and len(val.split("-")) >= 3:
                        return val
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
        # 买方/卖方 form (补充协议): 卖方=seller=supplier; 买方 must NOT match
        ({"1": "买方：某总承包公司\n卖方：某钢铁贸易有限公司"}, (None, None, None, "某钢铁贸易有限公司", None)),
        # F2b: split-line 下一行仍是标签 → 拒收(砂石料 '合同名称'→'局审批编号')
        ({"1": "合同名称\n局审批编号\n合同编号：HT-2025-001\n乙方：某公司\n签订日期：2025年6月18日"},
         (None, None, "HT-2025-001", "某公司", "2025-06-18")),
    ]
    for pt, want in cases:
        got = extract_project_fields(pt)
        assert got == want, f"{pt!r} → {got}, want {want}"

    # F2a: 表格 cell 冒号兜底(方案A) — 真实缓存取证结论固化为自检
    from types import SimpleNamespace

    def _t(rows):
        return SimpleNamespace(page_no=1, table_idx=0, rows=rows)

    assert find_contract_from_tables(
        [_t([["项目合同编号：2GS-YCXM-CL-CG-024-2019"]])]  # 砂石料 p10 真实格
    ) == "2GS-YCXM-CL-CG-024-2019"
    assert find_contract_from_tables([_t(
        [["招标文件审批编号：2GS-ZB-2019-038 供方单位全称"],  # 诱饵格先行
         ["项目合同编号：2GS-YCXM-CL-CG-024-2019"]],
    )]) == "2GS-YCXM-CL-CG-024-2019"
    assert find_contract_from_tables(
        [_t([["项目合同编号：2GS-SPXM-CL-CG-011-20 包合同段项目经理部"]])]  # 上浦粘连
    ) is None
    assert find_contract_from_tables([_t([["项目合同编号"]])]) is None  # 无冒号
    assert find_contract_from_tables([_t([["合同编号：HT-2025"]])]) is None  # dash 段数<3
    assert find_contract_from_tables(None) is None
    print("ok")
