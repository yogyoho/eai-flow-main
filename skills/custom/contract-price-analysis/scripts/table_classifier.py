"""Classify extracted tables and map column roles.

A contract contains many tables (price lists, payment schedules, acceptance
criteria, work-content descriptions). Only goods/price tables feed the
pipeline; the rest are recorded in parse_meta for traceability (never silently
dropped). Column-role mapping handles the messy reality of OCR'd tables:
multi-row merged headers get collapsed to one row, then headers are matched
against role tokens to find which column is name / qty / unit / price.

v2 (Phase 2 T2): split the single "price" role into price_taxed (含税) and
price_untaxed (不含税) — contracts list BOTH (含税合价/不含税合价). Stats use
含税; audit can see 不含税. Previously first-match picked whichever came first,
often the wrong (不含税) one. price remains as a fallback for single-column tables.
"""

# Recognised Chinese header tokens -> role. Order in this dict = match priority
# (price_taxed wins over price_untaxed wins over price when a header matches
# several — "含税合价" must NOT collapse to generic "合价").
ROLE_TOKENS = {
    "name": [
        "货物名称", "设备名称", "物资名称", "材料名称", "产品名称",
        "项目名称", "清单项目", "子目名称", "名称", "品名",
    ],
    "price_taxed": [
        "含税合价", "含税单价", "综合单价(含税)", "含税综合单价", "含税",
    ],
    "price_untaxed": [
        "不含税合价", "不含税单价", "不含增值税", "综合单价(不含税)", "不含税",
    ],
    "price": ["合价", "单价", "金额", "总价", "小计", "综合单价"],  # fallback (no tax split)
    "spec": ["规格型号", "规格", "型号", "技术参数", "参数"],
    "qty": ["工程量", "数量", "计量"],
    "unit": ["计量单位", "单位"],
    "date": ["付款节点", "日期", "时间"],
    "std": ["工作内容", "验收", "标准", "规范"],
}

# Header signal words that flip classification.
_PAYMENT_HINT = ("付款", "支付", "进度款")
_ACCEPTANCE_HINT = ("验收", "质量标准")


def _collapse_header(rows: list, peek: int = 3) -> tuple:
    """Collapse a multi-row merged header into one row.

    A header row is one containing at least one role token (序号/项目名称/单价/
    ...). Scan up to ``peek`` rows; STOP at the first row with no role token
    (= pure data row). This avoids swallowing data when a table has a single-
    row header (the old fixed peek=3 ate 2 data rows of a 1-header table).
    Returns (merged_header, header_rows).
    """
    if not rows:
        return [], 0
    all_tokens = [t for tokens in ROLE_TOKENS.values() for t in tokens]
    header_rows = 0
    for ri, row in enumerate(rows[:peek]):
        row_text = " ".join((c or "") for c in row)
        if any(t in row_text for t in all_tokens):
            header_rows = ri + 1
        else:
            break  # pure data row — header ended
    n = max(1, header_rows)
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
    """Map columns to roles by priority (price_taxed > price_untaxed > price).

    Each column takes the FIRST role (in ROLE_TOKENS order) it matches, so a
    header "含税合价" becomes price_taxed, not generic price. Each role records
    only its first matching column.

    Special case: "含税" is a substring of "不含税", so price_taxed must SKIP
    headers containing "不含税" — else "不含税单价" wrongly matches the "含税"
    token and claims the price_taxed role.
    """
    roles: dict = {}
    for ci, h in enumerate(header):
        for role_name, tokens in ROLE_TOKENS.items():
            if role_name in roles:
                continue  # role already filled
            if role_name == "price_taxed" and "不含税" in h:
                continue  # 不含税 header must not claim the 含税 role (substring trap)
            if any(t in h for t in tokens):
                roles[role_name] = ci
                break  # this column is claimed; stop matching lower-priority roles
    return roles


def classify(rows: list) -> tuple:
    """Classify one table.

    Returns (table_type, roles, header_rows):
      table_type: goods_price | payment_schedule | acceptance | unclassified
      roles: column indices for name / price_taxed / price_untaxed / price / spec / qty / unit
             (only present roles)
      header_rows: leading header rows to skip when extracting items
    """
    header, header_rows = _collapse_header(rows)
    roles = _map_roles(header)
    hdr_text = " ".join(header)

    if any(h in hdr_text for h in _PAYMENT_HINT):
        return "payment_schedule", roles, header_rows
    if any(h in hdr_text for h in _ACCEPTANCE_HINT) and not _has_price(roles):
        return "acceptance", roles, header_rows

    if "name" in roles and _has_price(roles):
        return "goods_price", roles, header_rows
    return "unclassified", roles, header_rows


def _has_price(roles: dict) -> bool:
    return any(r in roles for r in ("price_taxed", "price_untaxed", "price"))


def _price_columns(roles: dict) -> tuple:
    """Return (taxed_col, untaxed_col) — taxed falls back to generic price."""
    taxed = roles.get("price_taxed")
    if taxed is None:
        taxed = roles.get("price")  # single-column table → treat as taxed
    untaxed = roles.get("price_untaxed")
    return taxed, untaxed


def extract_items(rows: list, roles: dict, header_rows: int) -> list:
    """Turn a goods/price table's data rows into raw item dicts.

    Each item: {name, spec, qty, unit, price_taxed_raw, price_untaxed_raw, row_idx}.
    Empty-name rows skipped.
    """
    name_col = roles.get("name")
    taxed_col, untaxed_col = _price_columns(roles)
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
                "price_taxed_raw": cell(row, taxed_col) if taxed_col is not None else "",
                "price_untaxed_raw": cell(row, untaxed_col) if untaxed_col is not None else "",
                "row_idx": ri,
            }
        )
    return items
