# EAI-CUSTOM: forked from contract-price-analysis/scripts/table_classifier.py。
# 唯一改动:name 角色加了备件名 token(备件名称/配件名称/零部件名称/零件名称/货品名称)。
# bbox 抗漂移逻辑(_x_center / _row_cells_by_x / looks_like_continuation)是实弹修复过
# 的(p106+ 丢页 bug),逐字保留——别"简化"掉,真实 OCR 表格会漂。
"""Classify extracted tables and map column roles.

一份备件合同含很多表(备件清单、付款节点、验收标准、工作内容)。只有备件/价格表
进管线;其余记进 parse_meta 供溯源(绝不静默丢弃)。列角色映射处理 OCR 表的脏现实:
多行合并表头压成一行,再按角色 token 匹配哪一列是 名称/数量/单位/单价。

price 拆成 price_taxed(含税)与 price_untaxed(不含税)——合同两列都列(含税合价/
不含税合价)。统计用含税;审计可见不含税。单列表回退到 generic price。
"""

import re

# Recognised Chinese header tokens -> role. Order in this dict = match priority
# (price_taxed wins over price_untaxed wins over price when a header matches
# several — "含税合价" must NOT collapse to generic "合价")。
# EAI-CUSTOM: name 角色补充备件域 token(原 contract_price 只有货物/设备/物资/材料/产品)。
ROLE_TOKENS = {
    "name": [
        "备件名称", "配件名称", "零部件名称", "零件名称", "货品名称",
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

_NUM_RE = re.compile(r"^\d+(?:\.\d+)?$")


# ── bbox-x column alignment (drift-proof; replaces index mapping when usable) ──


def _x_center(bbox):
    """x-center of a page-normalized bbox [x1,y1,x2,y2]; None when missing."""
    if not bbox or len(bbox) < 4:
        return None
    xc = (float(bbox[0]) + float(bbox[2])) / 2.0
    return None if xc <= 0.0 else xc


def _bboxes_usable(rows, cell_bboxes):
    """True iff cell_bboxes carries real (non-zero) x-centers for most cells."""
    if not cell_bboxes:
        return False
    have = real = 0
    for row in cell_bboxes:
        for bb in row or []:
            have += 1
            if _x_center(bb) is not None:
                real += 1
    return have > 0 and real / have >= 0.5


def _roles_x_from_data(rows, cell_bboxes, roles, header_rows, scan=8):
    """{role: x_center} for continuation-page alignment — read each role's
    column x from DATA cells, not header cells. Takes the median x over up to
    ``scan`` data rows for stability. Returns {role: median_x} or None."""
    if not cell_bboxes or not roles:
        return None
    xs: dict = {role: [] for role in roles}
    for ri in range(header_rows, min(header_rows + scan, len(rows))):
        bbox_row = cell_bboxes[ri] if ri < len(cell_bboxes) else []
        for role, ci in roles.items():
            if ci is None or ci >= len(bbox_row):
                continue
            xc = _x_center(bbox_row[ci])
            if xc is not None:
                xs[role].append(xc)
    out: dict = {}
    for role, vals in xs.items():
        if vals:
            vals.sort()
            out[role] = vals[len(vals) // 2]  # median
    return out or None


def _row_cells_by_x(text_row, bbox_row, roles_x, tol=0.06):
    """Map a data row's cells to roles by x-proximity (drift-proof)。"""
    bboxes = bbox_row or []
    cells = [(_x_center(bboxes[ci]) if ci < len(bboxes) else None, txt) for ci, txt in enumerate(text_row)]
    pairs = []
    for role, rx in roles_x.items():
        for ci, (xc, _) in enumerate(cells):
            if xc is None:
                continue
            pairs.append((abs(xc - rx), role, ci))
    pairs.sort(key=lambda p: p[0])
    used_cells: set = set()
    out: dict = {}
    for dist, role, ci in pairs:
        if role in out or ci in used_cells:
            continue
        if dist > tol:
            continue
        out[role] = cells[ci][1]
        used_cells.add(ci)
    return out


def _collapse_header(rows: list, peek: int = 3) -> tuple:
    """Collapse a multi-row merged header into one row。

    Row kinds, scanned top-down:
      - leading TITLE/caption rows (no role token) or single-cell caption with a
        token: SKIPPED from merge but CONSUMED (counted in header_rows)。
      - HEADER rows (≥2 non-empty cells with a role token): merged。
      - first DATA row after a header (no token): stops the scan。
    Returns (merged_header, header_rows)。
    """
    if not rows:
        return [], 0
    all_tokens = [t for tokens in ROLE_TOKENS.values() for t in tokens]
    header_idxs: list[int] = []
    last_consumed = 0
    seen_header = False
    for ri, row in enumerate(rows[:peek]):
        cells = [(c or "").strip() for c in row]
        nonempty = sum(1 for c in cells if c)
        row_text = " ".join(cells)
        has_token = any(t in row_text for t in all_tokens)
        if has_token:
            last_consumed = ri + 1
            if nonempty >= 2:
                header_idxs.append(ri)
                seen_header = True
        elif seen_header:
            break  # data row after the header — stop
        else:
            last_consumed = ri + 1  # leading title row (no token) — skip, consume
    if not header_idxs:
        return [], last_consumed
    maxcols = max(len(rows[i]) for i in header_idxs)
    merged = []
    for ci in range(maxcols):
        parts = []
        for ri in header_idxs:
            if ci < len(rows[ri]):
                v = (rows[ri][ci] or "").strip()
                if v and v not in parts:
                    parts.append(v)
        merged.append(" ".join(parts))
    return merged, last_consumed


def _map_roles(header: list) -> dict:
    """Map columns to roles by priority (price_taxed > price_untaxed > price)。

    Special case: "含税" is a substring of "不含税", so price_taxed must SKIP
    headers containing "不含税"。
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


def classify(rows: list, keywords: list[str] | None = None, cell_bboxes: list | None = None) -> tuple:
    """Classify one table。

    Returns (table_type, roles, roles_x, header_rows):
      table_type: goods_price | payment_schedule | acceptance | unclassified
      roles: column INDICES for each role (index path)
      roles_x: {role: x_center} drift-proof x-bands, or None
      header_rows: leading header rows to skip when extracting items

    ``keywords``: project-configured table-name keywords(如 备件清单/配件清单/报价单)。
    若任一 keyword 出现在表首几行(标题/题注)且检出 name 列,则即使没有识别出的价格
    表头也强判 goods_price。payment/acceptance 提示仍优先。
    """
    header, header_rows = _collapse_header(rows)
    roles = _map_roles(header)
    roles_x = _roles_x_from_data(rows, cell_bboxes, roles, header_rows) if _bboxes_usable(rows, cell_bboxes) else None
    hdr_text = " ".join(header)
    head_text = " ".join((c or "") for r in rows[:4] for c in r) if rows else ""
    has_kw = bool(keywords) and any(kw and kw in head_text for kw in keywords)

    if any(h in hdr_text for h in _PAYMENT_HINT):
        return "payment_schedule", roles, roles_x, header_rows
    if any(h in hdr_text for h in _ACCEPTANCE_HINT) and not _has_price(roles):
        return "acceptance", roles, roles_x, header_rows

    if "name" in roles and (_has_price(roles) or has_kw):
        return "goods_price", roles, roles_x, header_rows
    return "unclassified", roles, roles_x, header_rows


def _has_price(roles: dict) -> bool:
    return any(r in roles for r in ("price_taxed", "price_untaxed", "price"))


def _price_columns(roles: dict) -> tuple:
    """Return (taxed_col, untaxed_col) — taxed falls back to generic price."""
    taxed = roles.get("price_taxed")
    if taxed is None:
        taxed = roles.get("price")  # single-column table → treat as taxed
    untaxed = roles.get("price_untaxed")
    return taxed, untaxed


def extract_items(rows: list, roles: dict, header_rows: int, cell_bboxes: list | None = None, roles_x: dict | None = None) -> list:
    """Turn a goods/price table's data rows into raw item dicts。

    Column alignment: bbox-x when ``roles_x`` + ``cell_bboxes`` are usable
    (drift-proof), else index-based。Both yield the same item shape:
    {name, spec, qty, unit, price_taxed_raw, price_untaxed_raw, row_idx}。
    Empty-name / 合计/小计 rows are skipped。
    """
    name_col = roles.get("name")
    taxed_col, untaxed_col = _price_columns(roles)
    use_x = bool(roles_x) and "name" in roles_x and _bboxes_usable(rows, cell_bboxes)
    if not use_x and name_col is None:
        return []
    skip = {"序号", "合计", "小计", "总计"}

    items = []
    for ri, row in enumerate(rows[header_rows:], start=header_rows):
        if use_x:
            bbox_row = cell_bboxes[ri] if ri < len(cell_bboxes) else []
            cells = _row_cells_by_x(row, bbox_row, roles_x)
            name = (cells.get("name") or "").strip()
            if not name or name in skip:
                continue
            items.append(
                {
                    "name": name,
                    "spec": (cells.get("spec") or "").strip() or None,
                    "qty_raw": cells.get("qty") or None,
                    "unit": cells.get("unit") or None,
                    "price_taxed_raw": cells.get("price_taxed") or cells.get("price") or "",
                    "price_untaxed_raw": cells.get("price_untaxed") or "",
                    "row_idx": ri,
                }
            )
        else:
            name = (row[name_col].strip() if name_col is not None and name_col < len(row) else "")
            if not name or name in skip:
                continue

            def cell(idx):
                return (row[idx].strip() if idx is not None and idx < len(row) else "")

            items.append(
                {
                    "name": name,
                    "spec": cell(roles.get("spec")) or None,
                    "qty_raw": cell(roles.get("qty")) or None,
                    "unit": cell(roles.get("unit")) or None,
                    "price_taxed_raw": cell(taxed_col) if taxed_col is not None else "",
                    "price_untaxed_raw": cell(untaxed_col) if untaxed_col is not None else "",
                    "row_idx": ri,
                }
            )
    return items


def looks_like_continuation(rows: list, roles: dict, goods_col_count: int, cell_bboxes: list | None = None, roles_x: dict | None = None) -> bool:
    """Detect a headerless continuation page of a preceding goods/price table。

    The layout detector splits one logical 清单 across PDF pages; only the first
    repeats the header, so continuation pages have no role tokens and classify
    'unclassified'。We recover them by inheriting the preceding table's column
    layout (header_rows=0)。

    X-based when ``roles_x`` + ``cell_bboxes`` are usable; falls back to index
    name_col check otherwise。Heuristics: column count within ±2 of the goods
    table, ≥4 cols。
    """
    if not rows:
        return False
    col_count = max((len(r) for r in rows), default=0)
    if col_count < 4 or abs(col_count - goods_col_count) > 2:
        return False

    if roles_x and "name" in roles_x and _bboxes_usable(rows, cell_bboxes):
        name_x = roles_x["name"]
        for ri in range(min(4, len(rows))):
            bbox_row = cell_bboxes[ri] if ri < len(cell_bboxes) else []
            for ci, txt in enumerate(rows[ri]):
                xc = _x_center(bbox_row[ci]) if ci < len(bbox_row) else None
                if xc is None or abs(xc - name_x) > 0.06:
                    continue
                v = (txt or "").strip()
                if v and not _NUM_RE.match(v) and not any(t in v for t in ROLE_TOKENS["name"]):
                    return True
        return False

    # Index fallback (legacy)
    if "name" not in roles:
        return False
    name_col = roles["name"]
    first = rows[0]
    if name_col >= len(first):
        return False
    name_val = (first[name_col] or "").strip()
    if not name_val:
        return False
    if any(t in name_val for t in ROLE_TOKENS["name"]):
        return False  # header repeat, not continuation data
    return True
