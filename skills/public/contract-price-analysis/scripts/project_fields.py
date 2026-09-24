"""Extract project-level fields from OCR'd contract pages.

Six fields (order matters — cli unpacks positionally):
  (project_name, project_location, contract_no, supplier, sign_date, project_no)

Resolution layers per field, cheapest first:
  1. text layer: ``标签：值`` on one line (+ cross-line join for project_name:
     continuation lines until a label line / closure suffix / 80-char cap);
     a bare label line takes the next line as value unless that line is itself
     a label (F2b guard).
  2. table cells: a label cell (exact or startswith) yields its same-cell
     colon value, then the right / below neighbour — with per-field validators
     (contract shape gate, supplier company-word screen, project-no code gate).
  3. field-specific anchors: project_name falls back to the 甲方 organisation
     when it ends with 项目经理部/项目部 (approval-form layouts where the
     buyer org IS the project dept); sign_date scans ±3 lines around
     盖章/甲方：/乙方： signature anchors for a FILLED 年月 date (handwritten
     underscores tolerated). No anchor / no date → honest None.

2026-09-21 metadata fix (forensics: .wolf/tmp/meta_fix/forensic1~3):
  supplier labels 分包人/供方单位/卖方单位 + company-word screen (rejects
  易全勇/联系电话 mis-extractions) + （或/以下简称“X”） suffix strip;
  project_name two-tier selection (explicit labels 项目名称/工程名称/项目全称
  win first, most complete among them; 合同名称 + 甲方 anchor only as
  fallback when no labeled source exists); project_no new field; contract
  numbers keep a Chinese tail segment (-补01) and gain a label-cell→right-
  neighbour path (JZGS); sign_date stamp-window path (桂北 合同订立时间).
"""

from __future__ import annotations

import re

# Order matters: earlier labels win when several match the same text.
_NAME_LABELS = ["项目名称", "工程名称", "项目全称", "合同名称"]
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
_PROJECT_NO_LABELS = ["项目编号", "工程编号"]
# Supplier = the performing party. 甲方 is the buyer (总包), NOT the supplier
# whose prices we analyze, so it's excluded. Order matters: 分包人 must beat
# 承包人 (桂北 has both; the 分包人 is the supplier), 供方单位 before 供方
# (prefix), 卖方 before 乙方 (补充协议 form). 供应商 dropped: no real contract
# uses it (实际标签=乙方/卖方/分包人/供方单位), and the word only appeared in
# prose ('中标供应商宜春市…').
_SUPPLIER_LABELS = [
    "分包人", "分包方", "供方单位", "卖方单位", "供方", "卖方",
    "乙方", "承包人", "承包方", "施工单位",
]
_DATE_LABELS = [
    "合同签订日期", "签订日期", "签署日期", "签订时间", "签署时间", "签定日期", "合同签定日期",
]

# label[:：、 ]value on one line.
_LINE = {
    lbl: re.compile(rf"{lbl}\s*[:：、]\s*([^\n\r]+)")
    for lbl in set(_NAME_LABELS) | set(_LOC_LABELS) | set(_SUPPLIER_LABELS) | set(_DATE_LABELS)
}
# a date in 年月日 or numeric form (normalized to YYYY-MM-DD by _parse_date).
# [\s_]* separators: handwritten fills on 盖章页 OCR as '2025_年12月_2日'.
_DATE_RE = re.compile(
    r"([12]\d{3})[\s_]*年[\s_]*(\d{1,2})[\s_]*月[\s_]*(\d{1,2})[\s_]*日"
    r"|(\d{4})[-/](\d{1,2})[-/](\d{1,2})"
)
# label + OPTIONAL separator + date captured directly — so a space separator
# ('签署日期 2025-06-18') works without a colon, not just '签订日期：...'.
_DATE_AFTER_LABEL = {
    lbl: re.compile(
        rf"{lbl}\s*[:：、]?\s*(\d{{4}}[\s_]*年\s*\d{{1,2}}[\s_]*月\s*\d{{1,2}}[\s_]*日"
        rf"|\d{{4}}[-/]\d{{1,2}}[-/]\d{{1,2}})"
    )
    for lbl in _DATE_LABELS
}
# contract/project numbers: alphanumerics + dashes; contract numbers may end
# with ONE Chinese tail segment ('ZCB-...-0353-补01' — the 补 is part of the no).
# Capture body must END alphanumeric — a greedy '[A-Za-z0-9\-]*' would swallow
# the dash before 补 and let the optional CJK tail match empty.
_CODE_BODY = r"[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?"
_CODE_BODY6 = r"[A-Za-z0-9][A-Za-z0-9\-]{5,}"  # ≥6 chars total, for shape gates
_CJK_TAIL = r"(?:-[一-鿿]{1,4}\d{0,4})?"
_CONTRACT_LINE = {
    lbl: re.compile(rf"{lbl}\s*[:：]\s*({_CODE_BODY}{_CJK_TAIL})") for lbl in _CONTRACT_LABELS
}
_PROJECT_NO_LINE = {
    lbl: re.compile(rf"{lbl}\s*[:：]\s*({_CODE_BODY})") for lbl in _PROJECT_NO_LABELS
}
# F2a 表格 cell 兜底(方案A,取证仿真已验证): '项目合同编号' 先于 '合同编号' 搜,
# 避免子串重复命中;含审批/招标编号字样的格是招标/审批流水号诱饵,整格跳过。
_TABLE_CONTRACT_LABELS = ["项目合同编号", "合同编号"]
_TABLE_CONTRACT_BAD = ("审批编号", "招标编号")
# 全值形态: 字母数字开头,主体仅字母数字+连字符(合同号允许中文结尾段),总长>=6;
# dash 段数另门(>=3)。项目编号更严: 纯代码,不允许中文。
_CONTRACT_SHAPE = re.compile(rf"^{_CODE_BODY6}{_CJK_TAIL}$")
_PROJECT_NO_SHAPE = re.compile(rf"^{_CODE_BODY6}$")
# F2b split-line 守卫: 候选值行本身含任何已知标签词 → 它是相邻标签不是值
# (砂石料 '合同名称' 下一行 '局审批编号' 被误当项目名)。
_KNOWN_LABELS = frozenset(
    set(_NAME_LABELS) | set(_LOC_LABELS) | set(_CONTRACT_LABELS)
    | set(_SUPPLIER_LABELS) | set(_DATE_LABELS) | set(_PROJECT_NO_LABELS)
    | set(_TABLE_CONTRACT_BAD)
)
# supplier 值守卫: (或/以下)简称尾缀剥离 + 标签词拒收 + 公司字样甄别。
_SUPPLIER_SHORT_RE = re.compile(
    r"[（(]\s*(?:或|以下)?简称\s*[:：]?\s*[“”\"']?\s*(?:乙方|卖方|供方|甲方|买方|丙方)\s*[“”\"']?\s*[）)]"
)
_SUPPLIER_BAD = (
    "联系电话", "代理人", "法定代表人", "委托代表人", "地址", "电话", "统一社会",
    "开户", "纳税人识别", "税号", "账号", "帐号", "邮箱", "传真", "经办人", "丙方",
    "盖章", "公章",
)
_SUPPLIER_ORG_RE = re.compile(r"公司|有限|厂|中心|集团")
# project_name 跨行拼接: 闭合尾缀(拼到项目经理部即停——印章碎片不得混入) + 上限。
_NAME_CLOSURE = ("项目经理部", "项目部", "经理部", "）")
_NAME_CAP = 80
# 项目名称 cell 源的页码上限: 元数据表单(审批单/会签表)都在前几页;更深的
# 工程量清单里 [项目名称] 是列头(值在下方),属于货物清单形态——guibei p25-94
# 38 个列头格取证定案(2026-09-21 复审)。项目名 cell 兜底同时只用表单形态
# (同格冒号值/右邻格),不取下方邻格。
_NAME_CELL_MAX_PAGE = 6
# sign_date 盖章区窗口: 锚行(盖章/甲方：/乙方：)±3 行内的已填年月日。
_STAMP_ANCHOR_RE = re.compile(r"盖章|甲方\s*[:：]|乙方\s*[:：]")
_STAMP_DATE_RE = re.compile(r"([12]\d{3})[\s_]*年[\s_]*(\d{1,2})[\s_]*月[\s_]*(\d{1,2})[\s_]*日")
_STAMP_EXCLUDE = ("合同开始", "合同终止", "开工日期", "完工日期", "交货日期", "交付日期")


def _clean(v: str | None) -> str | None:
    if not v:
        return None
    v = v.strip().strip("：:、 \t。.")
    # a value that collapses back to a known label (e.g. "项目名称：工程名称")
    # is a misread, not a real value.
    return v or None


def _squash(v: str) -> str:
    """Collapse all whitespace inside a cell value (OCR cell-internal line
    breaks: '宜春大 道总承包项目经理部' → '宜春大道总承包项目经理部')."""
    return re.sub(r"\s+", "", str(v))


def _contains_label_word(line: str) -> bool:
    return any(lbl in line for lbl in _KNOWN_LABELS)


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


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
    lines = _lines(text)
    labelset = set(labels)
    for i, ln in enumerate(lines):
        if ln.rstrip(":：、 ") in labelset and i + 1 < len(lines):
            cand = lines[i + 1]
            if _contains_label_word(cand):
                continue
            val = _clean(cand)
            if val:
                return val
    return None


def _join_from(lines: list[str], start: int, base: str) -> str:
    """Cross-line join for project_name: append continuation lines until a
    label line, a closure suffix (项目经理部/项目部/…/）), or the 80-char cap.
    Continuation lines must not contain label words (F2b semantics)."""
    val = base
    j = start
    while j < len(lines) and len(val) < _NAME_CAP:
        nxt = lines[j]
        if _contains_label_word(nxt):
            break
        val += nxt
        if val.endswith(_NAME_CLOSURE):
            break
        j += 1
    return val[:_NAME_CAP]


def _iter_same_line(lines: list[str], labels: list[str]):
    """Yield (value, line_idx) per label in priority order, join-ready."""
    for lbl in labels:
        for i, ln in enumerate(lines):
            m = _LINE[lbl].search(ln)
            if m:
                val = _clean(m.group(1))
                if val:
                    yield val, i


def _iter_split_line(lines: list[str], labels: list[str]):
    """Yield (value, next_line_idx) for bare-label lines (F2b-guarded)."""
    labelset = set(labels)
    for i, ln in enumerate(lines):
        if ln.rstrip(":：、 ") in labelset and i + 1 < len(lines):
            if _contains_label_word(lines[i + 1]):
                continue
            val = _clean(lines[i + 1])
            if val:
                yield val, i + 1


def _cells(tables, max_page: int | None = None):
    """Yield (table, rows) for TableExtract objects or {"rows": …} dicts.
    max_page restricts to tables on pages <= max_page (metadata forms live in
    the front pages; deep 工程量清单 tables are goods-schedule territory)."""
    for t in tables or []:
        if max_page is not None and getattr(t, "page_no", 1) > max_page:
            continue
        rows = getattr(t, "rows", None)
        if rows is None and isinstance(t, dict):
            rows = t.get("rows")
        if rows:
            yield t, rows


def _label_cell_values(rows, labels: list[str], exact: bool = False, include_below: bool = True):
    """Yield candidate values from label cells, best-first per cell:
    same-cell colon value → right neighbour → below neighbour (disable
    include_below for header-column layouts, where the label cell tops a
    column of item values). Cell values are whitespace-squashed. `exact`
    requires the stripped cell to equal the label (merged cells like
    '局审批编号 合同编号' never qualify); otherwise the cell may start with
    the label ('供方单位 付款方式', '项目名称：')."""
    longest_first = sorted(labels, key=len, reverse=True)
    for ri, row in enumerate(rows):
        for ci, cell in enumerate(row):
            txt = str(cell).strip()
            for lbl in longest_first:
                if exact:
                    hit = txt in (lbl, lbl + ":", lbl + "：")
                else:
                    hit = txt.startswith(lbl)
                if not hit:
                    continue
                rest = txt[len(lbl):].strip()
                if rest[:1] in (":", "："):
                    val = _squash(rest[1:])
                    if val:
                        yield val
                if ci + 1 < len(row):
                    nb = _squash(row[ci + 1])
                    if nb:
                        yield nb
                if include_below and ri + 1 < len(rows) and ci < len(rows[ri + 1]):
                    nb = _squash(rows[ri + 1][ci])
                    if nb:
                        yield nb
                break


# ---------------------------------------------------------------- project_name


def _valid_name(v: str | None) -> bool:
    if not v or len(v) < 2:
        return False
    if any(ch in v for ch in "：:"):
        return False  # unsplit label残渣 (合同备案编亏：… junk cells)
    return True


def _find_name(blob: str, tables) -> str | None:
    lines = _lines(blob)
    # 两级优先(2026-09-21 复审修正): 文档自带显式标签(项目名称/工程名称/项目全称)
    # 的候选最高优先,在其中取最完整者(长者胜,同长保标签优先序);
    # 仅当无任何带标签源时,才退回完整度排序(合同名称候选 + 甲方锚,尾缀者胜)。
    # 背景: jzgs [项目全称]格真值"…研创园项目"不带经理部尾缀,曾被尾缀排序
    # 压过而错取 [甲方]格部门全名。
    primary_labels = [l for l in _NAME_LABELS if l != "合同名称"]
    labeled: list[str] = []
    for val, i in _iter_same_line(lines, primary_labels):
        labeled.append(_join_from(lines, i + 1, val))
    for val, i in _iter_split_line(lines, primary_labels):
        labeled.append(_join_from(lines, i + 1, val))
    for _t, rows in _cells(tables, max_page=_NAME_CELL_MAX_PAGE):
        for val in _label_cell_values(rows, primary_labels, include_below=False):
            if _valid_name(val):
                labeled.append(val)
    labeled = [c for c in labeled if _valid_name(c)]
    if labeled:
        return max(labeled, key=len)
    # 回退路径: 合同名称候选 + 甲方锚(值须以 项目经理部/项目部 收尾——
    # '合同甲方：上浦项目'这类半截值与裸'甲方：'行拒绝),尾缀完整者胜。
    cands: list[str] = []
    for val, i in _iter_same_line(lines, ["合同名称"]):
        cands.append(_join_from(lines, i + 1, val))
    for val, i in _iter_split_line(lines, ["合同名称"]):
        cands.append(_join_from(lines, i + 1, val))
    for _t, rows in _cells(tables, max_page=_NAME_CELL_MAX_PAGE):
        for val in _label_cell_values(rows, ["合同名称"], include_below=False):
            if _valid_name(val):
                cands.append(val)
    for i, ln in enumerate(lines):
        m = re.search(r"甲方\s*[:：]\s*(\S.*)$", ln)
        if m:
            val = _join_from(lines, i + 1, _clean(m.group(1)) or "")
            if val.endswith(_NAME_CLOSURE[:3]) and _valid_name(val):
                cands.append(val)
    for _t, rows in _cells(tables):
        for val in _label_cell_values(rows, ["甲方"], exact=True):
            if val.endswith(_NAME_CLOSURE[:3]) and _valid_name(val):
                cands.append(val)
    cands = [c for c in cands if _valid_name(c)]
    if not cands:
        return None
    for c in cands:
        if c.endswith(_NAME_CLOSURE[:3]):
            return c
    return cands[0]


# ---------------------------------------------------------------- supplier


def _strip_short_suffix(v: str) -> str:
    prev = None
    while prev != v:
        prev = v
        v = _SUPPLIER_SHORT_RE.sub("", v).strip()
    return v.strip("：:、 ，,；;.")


def _valid_supplier(v: str | None) -> bool:
    """Company-word screen + label-fragment rejection. '易全勇' (乙方代理人
    person), '联系电话' (split-line neighbour) and seal fragments all fail."""
    if not v or len(v) < 3:
        return False
    if v[0] in "（(":
        return False
    if any(b in v for b in _SUPPLIER_BAD):
        return False
    return bool(_SUPPLIER_ORG_RE.search(v))


def _supplier_value(v: str) -> str | None:
    v = _strip_short_suffix(_clean(v) or "")
    return v if _valid_supplier(v) else None


def _find_supplier(blob: str, tables) -> str | None:
    lines = _lines(blob)
    for val, _i in _iter_same_line(lines, _SUPPLIER_LABELS):
        v = _supplier_value(val)
        if v:
            return v
    for val, _i in _iter_split_line(lines, _SUPPLIER_LABELS):
        v = _supplier_value(val)
        if v:
            return v
    for _t, rows in _cells(tables):
        for val in _label_cell_values(rows, _SUPPLIER_LABELS):
            v = _supplier_value(val)
            if v:
                return v
    return None


# ---------------------------------------------------------------- contract no


def _find_contract(text: str) -> str | None:
    for lbl in _CONTRACT_LABELS:
        m = _CONTRACT_LINE[lbl].search(text)
        if m:
            return m.group(1).strip("-")
    return None


def find_contract_from_tables(tables) -> str | None:
    """Contract number hiding in parsed table cells (文本路 miss 时兜底).

    门(按序,方案A): ①整格含 '审批编号'/'招标编号' → 跳过(流水号诱饵);
    ②'项目合同编号' 先于 '合同编号' 搜(避免子串重复命中);
    ③pass 1: 同 cell 内冒号值(砂石料会签表形态);须过 _CONTRACT_SHAPE 且
    dash 段数>=3 —— 上浦 p3 OCR 粘连截断值('…-011-20 包合同段项目经理部')
    由形态门挡住;
    ④pass 2: [合同编号] 独立标签格(精确匹配,合并格绝不参与)→ 右邻格
    (内部空白折叠,JZGS p1 形态)。取首个命中。

    tables 是 TableExtract(.rows)或等价 dict({"rows": …});纯只读,不触
    table_classifier 的 seed 语义。
    """
    for t, rows in _cells(tables):
        for row in rows:
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
    # pass 2: 独立标签格 → 右邻格(JZGS: [合同编号][JZGS-JS-IC-CL-01-2021])
    for t, rows in _cells(tables):
        for val in _label_cell_values(rows, _TABLE_CONTRACT_LABELS, exact=True):
            val = _squash(val).strip("-")
            if val and _CONTRACT_SHAPE.match(val) and len(val.split("-")) >= 3:
                return val
    return None


# ---------------------------------------------------------------- project_no


def _find_project_no(blob: str, tables) -> str | None:
    lines = _lines(blob)
    for lbl in _PROJECT_NO_LABELS:
        for ln in lines:
            m = _PROJECT_NO_LINE[lbl].search(ln)
            if m:
                val = m.group(1).strip("-")
                if _PROJECT_NO_SHAPE.match(val):
                    return val
    for _t, rows in _cells(tables):
        for val in _label_cell_values(rows, _PROJECT_NO_LABELS):
            val = val.strip("-")
            if _PROJECT_NO_SHAPE.match(val):
                return val
    return None


# ---------------------------------------------------------------- sign_date


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
    without a colon) or the next non-empty line, normalized to YYYY-MM-DD.
    The split-line value must not itself be another labeled field
    (合同开始日期：… as the neighbour of an empty 签订日期： is that field's
    value, not the signing date)."""
    for lbl in _DATE_LABELS:
        m = _DATE_AFTER_LABEL[lbl].search(text)
        if m:
            d = _parse_date(m.group(1))
            if d:
                return d
    lines = _lines(text)
    labelset = set(_DATE_LABELS)
    for i, ln in enumerate(lines):
        if ln.rstrip(":：、 ") in labelset and i + 1 < len(lines):
            nxt = lines[i + 1]
            if _contains_label_word(nxt) or any(x in nxt for x in _STAMP_EXCLUDE):
                continue
            d = _parse_date(nxt)
            if d:
                return d
    return None


def _find_stamp_date(page_texts: dict) -> str | None:
    """盖章区手写日期: 在含 盖章/甲方：/乙方： 锚行的页,锚行 ±3 行窗口内找
    已填数字的 年月日 形态(容忍手写下划线 '2025_年12月_2日');合同开始/终止
    等条款日期行排除。找不到 → None(诚实 NULL,不硬猜)。"""
    for pno in sorted(page_texts):
        lines = _lines(str(page_texts[pno]))
        anchors = [i for i, ln in enumerate(lines) if _STAMP_ANCHOR_RE.search(ln)]
        if not anchors:
            continue
        for i, ln in enumerate(lines):
            if any(x in ln for x in _STAMP_EXCLUDE):
                continue
            m = _STAMP_DATE_RE.search(ln)
            if m and any(abs(i - a) <= 3 for a in anchors):
                d = _parse_date(m.group(0))
                if d:
                    return d
    return None


def extract_project_fields(page_texts: dict, tables=None) -> tuple:
    """Search the OCR text (front pages + tail merge) and parsed tables for
    project-level metadata.

    page_texts: {page_no: text}. tables: parsed TableExtract list (optional;
    enables the cell fallbacks). Returns (project_name, project_location,
    contract_no, supplier, sign_date, project_no); any may be None. sign_date
    is normalized to YYYY-MM-DD. contract_no propagates to items'
    source_contract_no.
    """
    blob = "\n".join(t for _, t in sorted(page_texts.items()) if t)
    if not blob and not tables:
        return None, None, None, None, None, None
    name = _find_name(blob, tables)
    loc = _find(blob, _LOC_LABELS)
    contract = _find_contract(blob)
    if contract is None and tables:
        contract = find_contract_from_tables(tables)
    supplier = _find_supplier(blob, tables)
    if not _valid_supplier(supplier):
        supplier = None  # belt-and-braces: _find_supplier already validates
    sign_date = _find_date(blob) or _find_stamp_date(page_texts)
    project_no = _find_project_no(blob, tables)
    return name, loc, contract, supplier, sign_date, project_no


if __name__ == "__main__":  # ponytail self-check: regex must catch common forms
    cases = [
        ({"1": "项目名称：桂北数据中心专业分包工程\n工程地点：桂北市\n合同编号：HT-2025-001\n乙方：桂北建工有限公司\n签订日期：2025年6月18日"},
         ("桂北数据中心专业分包工程", "桂北市", "HT-2025-001", "桂北建工有限公司", "2025-06-18", None)),
        ({"1": "项目名称\n桂北数据中心\n建设地点：\n桂北\n分包方：XX公司\n签署日期 2025-06-18"},
         ("桂北数据中心", "桂北", None, "XX公司", "2025-06-18", None)),
        ({"1": "合同名称：某合同\n项目所在地\n桂北高新区"}, ("某合同", "桂北高新区", None, None, None, None)),
        ({"1": "无标签封面文本"}, (None, None, None, None, None, None)),
        # supplier = seal fragment '（盖章）' (OCR split '（盖'+'章）') → rejected (None)
        ({"1": "乙方\n（盖章）"}, (None, None, None, None, None, None)),
        # 买方/卖方 form (补充协议): 卖方=seller=supplier; 买方 must NOT match
        ({"1": "买方：某总承包公司\n卖方：某钢铁贸易有限公司"}, (None, None, None, "某钢铁贸易有限公司", None, None)),
        # F2b: split-line 下一行仍是标签 → 拒收(砂石料 '合同名称'→'局审批编号')
        ({"1": "合同名称\n局审批编号\n合同编号：HT-2025-001\n乙方：某公司\n签订日期：2025年6月18日"},
         (None, None, "HT-2025-001", "某公司", "2025-06-18", None)),
        # 2026-09-21: 个人名/标签词拒收(公司字样甄别);尾缀剥离;分包人优先于承包人
        ({"1": "供方：易全勇"}, (None, None, None, None, None, None)),
        ({"1": "卖方：中国交通物资有限公司（或简称“乙方”）"},
         (None, None, None, "中国交通物资有限公司", None, None)),
        ({"1": "承包人：甲方公司\n分包人：施工劳务有限公司"},
         (None, None, None, "施工劳务有限公司", None, None)),
        ({"1": "项目名称：某智能装备\n制造基地项目经理部\n项目编号：01116102P2020002"},
         ("某智能装备制造基地项目经理部", None, None, None, None, "01116102P2020002")),
        ({"1": "盖章\n合同订立时间：2025_年12月_2日。"}, (None, None, None, None, "2025-12-02", None)),
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
    # 2026-09-21: 独立标签格右邻兜底(JZGS p1);合并标签格绝不参与;中文尾段保留
    assert find_contract_from_tables(
        [_t([["合同名称", "物资采购合同（钢材）", "合同编号", "JZGS-JS-IC-CL-01-2021"]])]
    ) == "JZGS-JS-IC-CL-01-2021"
    assert find_contract_from_tables(
        [_t([["局审批编号 合同编号", "2-YCDD-13-201"]])]  # 合并格 → 右邻流水号不许命中
    ) is None
    assert find_contract_from_tables(
        [_t([["合同编号", "ZCB-HEB-0201-2025-0353-补01"]])]
    ) == "ZCB-HEB-0201-2025-0353-补01"
    assert find_contract_from_tables(None) is None
    print("ok")
