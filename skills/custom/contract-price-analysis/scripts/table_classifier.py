"""Classify extracted tables and map column roles.

A contract contains many tables (price lists, payment schedules, acceptance
criteria, work-content descriptions). Only goods/price tables feed the
pipeline; the rest are recorded in parse_meta for traceability (never silently
dropped). Column-role mapping handles the messy reality of OCR'd tables:
multi-row merged headers get collapsed to one row, then headers are matched
against role tokens to find which column is name / qty / unit / price.
"""

import re

# Recognised Chinese header tokens -> role. First match wins per column.
ROLE_TOKENS = {
    "name": [
        "货物名称", "设备名称", "物资名称", "材料名称", "产品名称",
        "项目名称", "清单项目", "子目名称", "名称", "品名",
    ],
    "spec": ["规格型号", "规格", "型号", "技术参数", "参数"],
    "qty": ["工程量", "数量", "计量"],
    "unit": ["计量单位", "单位"],
    "price": [
        "综合单价", "不含税单价", "不含增值税", "含税合价", "含税单价",
        "税金", "单价", "合价", "金额", "总价", "小计", "含税",
    ],
    "date": ["付款节点", "日期", "时间"],
    "std": ["工作内容", "验收", "标准", "规范"],
}

# Header signal words that flip classification.
_PAYMENT_HINT = ("付款", "支付", "进度款")
_ACCEPTANCE_HINT = ("验收", "质量标准")


def _collapse_header(rows: list, peek: int = 3) -> list:
    """Collapse a multi-row merged header into one row.

    Scans the first ``peek`` rows; for each column takes the first non-empty
    cell across those rows. Returns the merged header (list[str]) plus the
    number of rows consumed (header_rows).
    """
    if not rows:
        return [], 0
    n = min(peek, len(rows))
    maxcols = max((len(r) for r in rows[:n]), default=0)
    merged = []
    for ci in range(maxcols):
        parts = []
        for ri in range(n):
            if ci < len(rows[ri]):
                v = (rows[ri][ci] or "").strip()
                if v and v not in parts:
                    parts.append(v)
        merged.append(" ".join(parts))
    return merged, n


def _map_roles(header: list) -> dict:
    roles: dict = {}
    for ci, h in enumerate(header):
        for role_name, tokens in ROLE_TOKENS.items():
            if any(t in h for t in tokens):
                if role_name not in roles:
                    roles[role_name] = ci
                break
    return roles


def classify(rows: list) -> tuple:
    """Classify one table.

    Returns (table_type, roles, header_rows):
      table_type: goods_price | payment_schedule | acceptance | unclassified
      roles: {name, spec, qty, unit, price} -> column index (only present roles)
      header_rows: how many leading rows are header (skip when extracting items)
    """
    header, header_rows = _collapse_header(rows)
    roles = _map_roles(header)
    hdr_text = " ".join(header)

    if any(h in hdr_text for h in _PAYMENT_HINT):
        return "payment_schedule", roles, header_rows
    if any(h in hdr_text for h in _ACCEPTANCE_HINT) and "price" not in roles:
        return "acceptance", roles, header_rows

    # Goods/price signal: name + price columns, ideally with qty/spec/unit.
    if "name" in roles and "price" in roles:
        return "goods_price", roles, header_rows
    return "unclassified", roles, header_rows


def extract_items(rows: list, roles: dict, header_rows: int) -> list:
    """Turn a goods/price table's data rows into raw item dicts.

    Each item: {name, spec, qty, unit, price_raw, col_idx}. Cells beyond the
    row length are treated empty. Empty-name rows are skipped.
    """
    name_col = roles.get("name")
    price_col = roles.get("price")
    if name_col is None:
        return []

    def cell(row, idx):
        return (row[idx].strip() if idx is not None and idx < len(row) else "")

    items = []
    for ri, row in enumerate(rows[header_rows:], start=header_rows):
        name = cell(row, name_col)
        if not name or name in ("序号", "合计", "小计", "总计"):
            continue
        items.append(
            {
                "name": name,
                "spec": cell(row, roles.get("spec")) or None,
                "qty_raw": cell(row, roles.get("qty")) or None,
                "unit": cell(row, roles.get("unit")) or None,
                "price_raw": cell(row, price_col) if price_col is not None else "",
                "row_idx": ri,
            }
        )
    return items
