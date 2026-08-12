# EAI-CUSTOM: forked from contract-price-analysis/scripts/project_fields.py。
# 关键域改动:④的分析维度 = customer(采购方/甲方/需方),故新增客户抽取;
# contract_price 原本抽 supplier(乙方)并排除甲方,这里反过来——customer 才是主维度。
"""Extract document-level fields from OCR'd first-page text。

扫描件封面/首页通常带 ``客户名称：XXX`` / ``合同编号：YYY`` / ``签订日期：...`` 之类
表单。OCR 服务把文本框用换行拼接,标签和值可能同行(``采购方：桂北矿业``)也可能
分两行(``采购方`` / ``桂北矿业``)。先试同行,再试"标签独占一行、值在下一行"。

与 contract_price 的核心差异:④把 **customer(采购方/甲方/需方)** 作为比价分析主维度,
故在原 supplier(供方/卖方)之外新增 customer 抽取。抽不到的字段返回 None,管理前端
兜底人工录入(管线在别处把这类文档标 needs_review)。
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
# Customer = the BUYER (采购方/甲方/需方) —— ④ 的比价分析主维度(D3)。
_CUSTOMER_LABELS = [
    "采购方", "买方", "甲方", "需方", "订货方", "购货方", "进货方", "客户名称", "客户",
]
# Supplier = the SELLER (供方/卖方) —— 文档元数据,非分析维度,但 OCR 会抽到,顺带留存。
_SUPPLIER_LABELS = ["供方", "供应商", "卖方", "乙方", "供货方", "销货方"]
_DATE_LABELS = [
    "合同签订日期", "签订日期", "签署日期", "签订时间", "签署时间", "签定日期", "合同签定日期",
]

_ALL_LABELS = (
    set(_NAME_LABELS) | set(_LOC_LABELS) | set(_CONTRACT_LABELS)
    | set(_CUSTOMER_LABELS) | set(_SUPPLIER_LABELS) | set(_DATE_LABELS)
)

# label[:：、 ]value on one line.
_LINE = {
    lbl: re.compile(rf"{lbl}\s*[:：、]\s*([^\n\r]+)")
    for lbl in _ALL_LABELS
}
# a date in 年月日 or numeric form (normalized to YYYY-MM-DD by _parse_date).
_DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日|(\d{4})[-/](\d{1,2})[-/](\d{1,2})")
# label + OPTIONAL separator + date captured directly.
_DATE_AFTER_LABEL = {
    lbl: re.compile(
        rf"{lbl}\s*[:：、]?\s*(\d{{4}}\s*年\s*\d{{1,2}}\s*月\s*\d{{1,2}}\s*日|\d{{4}}[-/]\d{{1,2}}[-/]\d{{1,2}})"
    )
    for lbl in _DATE_LABELS
}
# contract number is alphanumeric+dashes.
_CONTRACT_LINE = {
    lbl: re.compile(rf"{lbl}\s*[:：]\s*([A-Za-z0-9\-]+)") for lbl in _CONTRACT_LABELS
}


def _clean(v: str | None) -> str | None:
    if not v:
        return None
    v = v.strip().strip("：:、 \t。.")
    return v or None


def _find(text: str, labels: list[str]) -> str | None:
    for lbl in labels:
        m = _LINE[lbl].search(text)
        if m:
            val = _clean(m.group(1))
            if val:
                return val
    # split-line fallback: a line that IS the label (trailing colon ok) → value is the next non-empty line.
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
    """Find a signature date anchored on a 签订/签署 label, normalized to YYYY-MM-DD."""
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


def _valid_party(v: str | None) -> bool:
    """Reject obvious mis-extractions: seal fragments like '（盖' (from '（盖章）'
    split by OCR), too-short values, or bare seal words. Real party names are
    company names (≥3 chars, don't start with a parenthesis)."""
    if not v or len(v) < 3:
        return False
    if v[0] in "（(":
        return False
    if v in ("盖章", "公章", "合同专用章"):
        return False
    return True


def extract_project_fields(page_texts: dict[int, str]) -> tuple:
    """Search the front-page OCR text for customer + project name + location +
    contract no + supplier + sign_date。

    page_texts: {page_no: text}(已由 OCR 服务限在前几页)。返回
    (customer, project_name, project_location, contract_no, supplier, sign_date);
    任一可为 None。sign_date 归一为 YYYY-MM-DD。customer 经 T3 归一层映射到 customer_id;
    未命中则入待确认队列。contract_no 透传到 items 的 source_contract_no。
    """
    blob = "\n".join(t for _, t in sorted(page_texts.items()) if t)
    if not blob:
        return None, None, None, None, None, None
    customer = _find(blob, _CUSTOMER_LABELS)
    if not _valid_party(customer):
        customer = None  # 拒绝印章碎片/过短 → 待确认队列或人工填
    supplier = _find(blob, _SUPPLIER_LABELS)
    if not _valid_party(supplier):
        supplier = None
    return (
        customer,
        _find(blob, _NAME_LABELS),
        _find(blob, _LOC_LABELS),
        _find_contract(blob),
        supplier,
        _find_date(blob),
    )


if __name__ == "__main__":  # ponytail self-check: regex must catch common forms
    cases = [
        ({"1": "采购方：桂北矿业集团\n项目名称：液压支架备件采购\n合同编号：CSP-2025-001\n供方：中煤机械厂\n签订日期：2025年6月18日"},
         ("桂北矿业集团", "液压支架备件采购", None, "CSP-2025-001", "中煤机械厂", "2025-06-18")),
        ({"1": "甲方\n桂北矿业\n项目名称\n液压支架备件\n建设地点：\n桂北\n乙方：中煤机械厂\n签署日期 2025-06-18"},
         ("桂北矿业", "液压支架备件", "桂北", None, "中煤机械厂", "2025-06-18")),
        ({"1": "合同名称：某备件合同\n客户名称：A客户\n项目所在地\n桂北高新区"},
         ("A客户", "某备件合同", "桂北高新区", None, None, None)),
        ({"1": "无标签封面文本"}, (None, None, None, None, None, None)),
        # customer label present but value is a seal fragment '（盖章）' → rejected (None)
        ({"1": "采购方\n（盖章）"}, (None, None, None, None, None, None)),
    ]
    for pt, want in cases:
        got = extract_project_fields(pt)
        assert got == want, f"{pt!r} → {got}, want {want}"
    print("ok")
