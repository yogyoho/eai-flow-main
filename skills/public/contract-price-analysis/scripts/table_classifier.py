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

import re

from scripts.price_validator import parse_qty, validate_price

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

_NUM_RE = re.compile(r"^\d+(?:\.\d+)?$")


# ── bbox-x column alignment (drift-proof; replaces index mapping when usable) ──
# The OCR engine returns a page-normalized bbox per cell. A logical column is a
# vertical x-band, so aligning by x-center is immune to position-index shifts
# (rapid-table emitting an extra empty leading column, colspan expanding
# differently per page). Index drift is the root cause of (a) the p106+ loss —
# looks_like_continuation checked first[name_col] which was empty after drift —
# and (b) 含税单价 landing on 税率/数量 columns. Every function below falls back to
# the index path when bboxes are missing/zero, so tables without usable bboxes
# keep the pre-bbox behaviour.


def _x_center(bbox):
    """x-center of a page-normalized bbox [x1,y1,x2,y2]; None when missing.

    OCR returns [0,0,0,0] for cells without a real bbox (colspan/rowspan
    span-over placeholders, or failed detection) — those carry no position
    signal, so x-center 0.0 is treated as 'no bbox'."""
    if not bbox or len(bbox) < 4:
        return None
    xc = (float(bbox[0]) + float(bbox[2])) / 2.0
    return None if xc <= 0.0 else xc


def _bboxes_usable(rows, cell_bboxes):
    """True iff cell_bboxes carries real (non-zero) x-centers for most cells.

    When False, callers fall back to index alignment — a table whose bbox
    detection failed does not regress."""
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
    column x from DATA cells, not header cells.

    Why data not header: rapid-table often fragments/misplaces header cells
    (group headers like '含税' spanning 单价+合价 land at the 合价 column's x;
    titles like '工程量清单' match the qty token). Trusting header-cell x made
    price_taxed grab 含税合价 instead of 含税单价. Role IDENTIFICATION stays on
    the index path (_map_roles over the collapsed header — proven correct); x is
    only used to recover cells on drifted continuation pages. Reading the column
    x from data cells (which have clean, positionally-accurate bboxes) is far
    more reliable.

    band = 该角色语义数据格 x 的中位数——只统计有真实文本的数据格,空单元格
    不定义列带(bug-3400 二阶段: p94 实测 price_total 种子列数据行大多为空串,
    空格参与中位数会把带钉在空列上);某角色在扫描窗口内没有任何非空数据格时,
    该角色整体从结果省略(无语义带,迫使上层回退列号路径而非用空格位置冒充)。
    Takes the median x over up to ``scan`` data rows for stability.

    Returns {role: median_x} (仅含窗口内有非空数据格的角色) or None when no
    role has any usable data cell."""
    if not cell_bboxes or not roles:
        return None
    xs: dict = {role: [] for role in roles}
    for ri in range(header_rows, min(header_rows + scan, len(rows))):
        text_row = rows[ri] if ri < len(rows) else []
        bbox_row = cell_bboxes[ri] if ri < len(cell_bboxes) else []
        for role, ci in roles.items():
            if ci is None or ci >= len(bbox_row):
                continue
            if ci >= len(text_row) or not (text_row[ci] or "").strip():
                continue  # 空单元格不定义列带
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
    """Map a data row's cells to roles by x-proximity (drift-proof).

    两段式认领(bug-3400 二阶段): pass1 只允许非空文本格按距离贪心认领角色;
    pass2 仍未认领的角色才可被空格认领(同样的 tol 与一格一角色约束)。
    空格映射到角色本来就产出空值,让稍远一点的非空格优先是纯信息升级
    (p94 实测: price_total 带内空格 dist 0.004 抢占,真合价 dist 0.053 被挡);
    某角色该行真无值时仍由 pass2 落空/缺席,不发明值。``tol`` 保持 0.06 不放宽。

    Each role → the cell whose x-center is nearest its x-band; resolved greedily
    by smallest distance so two roles can't claim one cell. Roles with no cell
    within ``tol`` (page-normalized) are left absent. Returns {role: cell_text}."""
    bboxes = bbox_row or []
    cells = [(_x_center(bboxes[ci]) if ci < len(bboxes) else None, txt) for ci, txt in enumerate(text_row)]
    pairs = []
    for role, rx in roles_x.items():
        for ci, (xc, txt) in enumerate(cells):
            if xc is None:
                continue
            pairs.append((abs(xc - rx), role, ci, bool((txt or "").strip())))
    pairs.sort(key=lambda p: p[0])
    used_cells: set = set()
    out: dict = {}
    # pass1: 非空格优先;pass2: 剩余角色允许空格补位(共用 used_cells,一格一角色)
    for pass_nonempty_only in (True, False):
        for dist, role, ci, _nonempty in pairs:
            if role in out or ci in used_cells:
                continue
            if dist > tol:
                continue
            if pass_nonempty_only and not _nonempty:
                continue
            out[role] = cells[ci][1]
            used_cells.add(ci)
    return out


def _collapse_header(rows: list, peek: int = 3) -> tuple:
    """Collapse a multi-row merged header into one row.

    Row kinds, scanned top-down:
      - leading TITLE/caption rows (no role token, e.g. '设备清单'; OR a single
        non-empty cell with a token, e.g. <td colspan="11">工程量清单</td>):
        SKIPPED from the merge (their text would pollute column roles) but
        CONSUMED (counted in header_rows so extract_items skips past them).
      - HEADER rows (≥2 non-empty cells with a role token): merged.
      - first DATA row after a header (no token): stops the scan.

    A no-token row BEFORE any header is treated as a title (skipped), not data
    — so a '设备清单' title above the real header doesn't abort the scan.
    Returns (merged_header, header_rows, header_row_idxs):
      merged_header: 折叠后的单行表头;
      header_rows: 数据区前的吞掉行数(标题行 + 表头行),extract 用它跳过;
      header_row_idxs: 被合并进表头的行索引集合——区别于吞掉的标题行。
        bug-3428 F1a: 标题关键词匹配必须排除这些行('物资名称'类列头不是表名),
        但标题行(表名所在)不在集合内、仍参与标题匹配。"""
    if not rows:
        return [], 0, []
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
            # else: single-cell caption with a token — skip from merge, consume
        elif seen_header:
            break  # data row after the header — stop
        else:
            last_consumed = ri + 1  # leading title row (no token) — skip, consume
    if not header_idxs:
        return [], last_consumed, []
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
    return merged, last_consumed, header_idxs


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


def classify(rows: list, keywords: list[str] | None = None, cell_bboxes: list | None = None) -> tuple:
    """Classify one table.

    Returns (table_type, roles, roles_x, header_rows):
      table_type: goods_price | payment_schedule | acceptance | unclassified
      roles: column INDICES for each role (index path; used when bboxes are
             unusable and for classification heuristics)
      roles_x: {role: x_center} drift-proof x-bands, or None when the OCR gave
             no usable cell bboxes (caller falls back to ``roles``)
      header_rows: leading header rows to skip when extracting items

    ``keywords``: project-configured table-name keywords (e.g. 工程量清单/设备清单/
    报价). If any keyword appears in the table's first few rows (the title/
    caption lives there) AND a name column is detected, the table is strongly
    judged goods_price even without a recognised price header — different
    contracts name their price tables differently, so the keyword lowers the
    bar from (name + price) to (name + keyword). payment/acceptance hints
    still win first.
    """
    header, header_rows, _hdr_idxs = _collapse_header(rows)
    roles = _map_roles(header)
    roles_x = _roles_x_from_data(rows, cell_bboxes, roles, header_rows) if _bboxes_usable(rows, cell_bboxes) else None
    hdr_text = " ".join(header)
    # title/caption + first rows carry the table-name keyword (the caption row
    # is excluded from the merged header, so scan the raw first rows too).
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
    """Turn a goods/price table's data rows into raw item dicts.

    Column alignment: bbox-x when ``roles_x`` + ``cell_bboxes`` are usable
    (drift-proof — finds each role's cell by page x, immune to position-index
    shifts), else index-based (legacy). Both yield the same item shape:
    {name, spec, qty, unit, price_taxed_raw, price_untaxed_raw, row_idx}.
    Empty-name / 合计/小计 rows are skipped.
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
                    # taxed falls back to generic price, mirroring _price_columns
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
    """Detect a headerless continuation page of a preceding goods/price table.

    The layout detector splits one logical 工程量清单 across PDF pages; only the
    first repeats the header, so continuation pages have no role tokens and
    classify 'unclassified'. We recover them by inheriting the preceding table's
    column layout (header_rows=0 — every row is data).

    X-based (drift-proof) when ``roles_x`` + ``cell_bboxes`` are usable: the page
    is a continuation iff some data-row cell lands near the inherited name x-band
    with non-empty, non-numeric, non-header text. This is the fix for the p106+
    loss — index detection checked first[name_col], which was empty when
    rapid-table emitted an extra leading column, orphaning every following page.
    Falls back to the index name_col check otherwise.

    Heuristics: column count within ±2 of the goods table, ≥4 cols.
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


# ── seed 定位规则匹配 (v3, 严格 seed-only; 设计 §2) ──────────────────────────

_ROLE_ORDER = ["name", "spec", "qty", "unit", "price_unit", "price_total", "price_untaxed"]


def _norm_header(s: str) -> str:
    """归一化表头单元格: 去全部空白、去（）()括注(公式后缀如 5=2+3)、全角转半角、小写。

    实测噪声: '5.综合单 价（5=2+3）'、'含 税 单 价'、'含税单 价（元 /t)' —
    归一化后锚点子串匹配才能命中。"""
    if not s:
        return ""
    out = []
    depth = 0
    for ch in s:
        if ch in "（(":
            depth += 1
            continue
        if ch in "）)":
            depth = max(0, depth - 1)
            continue
        if depth:
            continue
        if ch.isspace():
            continue
        # 全角转半角(0xFF01-0xFF5E → 0x21-0x7E),半角结果再小写(全角拉丁/数字一并归一)
        out.append(chr(ord(ch) - 0xFEE0).lower() if 0xFF01 <= ord(ch) <= 0xFF5E else ch.lower())
    return "".join(out)


def _title_text(rows: list, limit: int = 4, exclude_rows=None) -> str:
    """前若干行的归一化联合文本(标题/表名关键词在这里找)。

    exclude_rows: 要排除的行索引集合(表头行,由 _collapse_header 返回)——
    bug-3428 F1a: '物资名称'类列头格会被 seed 标题关键词('物资')假命中,
    劫持 seed 选择;标题关键词只应匹配表名,表头行必须从标题文本剔除。
    吞掉的标题行(表名所在)不在集合内,仍参与匹配。"""
    skip = set(exclude_rows or ())
    blob = " ".join(
        (c or "") for ri, r in enumerate(rows[:limit]) if ri not in skip for c in r
    )
    return _norm_header(blob)


def _first_anchor_col(norm_cols: list, anchors: list, banned: list) -> int | None:
    """第一个锚点命中的表头列索引(忽略占用;空格跳过、禁用词守卫同主循环)。
    无命中返回 None。复合表头拆分(bug-3428 F1b)用它探测 spec 锚的落格。"""
    for ci, h in enumerate(norm_cols):
        if not h:
            continue
        if any(b and b in h for b in banned):
            continue
        if any(a in h for a in anchors):
            return ci
    return None


def _match_one_seed(rows: list, seed: dict, header: list) -> tuple[dict, dict] | None:
    """单 seed 列锚定: 角色→第一个锚点命中的未占用列(exclude 守卫)。
    复合表头拆分(bug-3428 F1b): name/spec 锚命中同一表头格、且左邻格表头为
    空串时重绑 name→左邻格, spec→本格(两列共用一个表头格的形态)。
    返回 (roles, score_detail) 或 None(确认条件不满足)。"""
    norm_cols = [_norm_header(h) for h in header]
    excl = seed.get("exclude") or {}
    roles: dict = {}
    for role in _ROLE_ORDER:
        # 归一化后过滤空锚点(如"（）"归一化为"")——空串是任何列的子串,会误占列
        anchors = [a for a in (_norm_header(t) for t in (seed["columns"].get(role) or [])) if a]
        if not anchors:
            continue
        banned = [_norm_header(t) for t in (excl.get(role) or [])]
        for ci, h in enumerate(norm_cols):
            if ci in roles.values() or not h:
                continue
            if any(b and b in h for b in banned):
                continue
            if any(a in h for a in anchors):
                roles[role] = ci
                break
    # 复合表头拆分(门控缺一不可): (1)spec 锚的第一落格与 name 同格 ci——name
    # 先占格导致 spec 静默失绑、品名错拿规格文本; (2)左邻格(ci-1)表头为空串——
    # 真品名列表头空、'材质/规格'类复合词格落右列, 是两列共用表头格的形态指纹。
    # 重绑 name→ci-1, spec→ci;左邻格已被其他角色占用则不动(防拆错)。
    # roles_x 由调用方以 roles 为输入重建(_roles_x_from_data), 天然兼容新绑定。
    if "name" in roles and "spec" not in roles:
        spec_anchors = [a for a in (_norm_header(t) for t in (seed["columns"].get("spec") or [])) if a]
        if spec_anchors:
            spec_ci = _first_anchor_col(
                norm_cols, spec_anchors, [_norm_header(t) for t in (excl.get("spec") or [])]
            )
            ci = roles["name"]
            if (
                spec_ci == ci
                and ci >= 1
                and norm_cols[ci - 1] == ""
                and (ci - 1) not in roles.values()
            ):
                roles["name"] = ci - 1
                roles["spec"] = ci
    if "name" not in roles or not ("price_unit" in roles or "price_total" in roles):
        return None
    return roles, {"roles_n": len(roles)}


def match_seed(rows: list, seeds: list[dict]) -> tuple[dict, dict, int] | None:
    """严格 seed-only 主路径: 逐 seed 锚定,确认条件=name+任一价格角色;
    多候选: 标题关键词命中优先,其次锚定角色数多者;全并列时锚点更少(规则更专)者优。
    返回 (seed, roles{role: col_idx}, header_rows) 或 None(无 seed 确认)。
    标准表头折叠(前3行)未命中时走 _match_seed_deep 深扫兜底(同样 seed-only)。"""
    if not rows or not seeds:
        return None
    header, header_rows, hdr_idxs = _collapse_header(rows)
    if header:
        # 标题文本排除表头行(F1a): 列头词('物资名称')不是表名,不得参与标题命中
        title = _title_text(rows, exclude_rows=hdr_idxs)
        best: tuple[int, int, int, dict, dict] | None = None  # (title_hit, roles_n, -anchors_n, seed, roles)
        for seed in seeds:
            got = _match_one_seed(rows, seed, header)
            if got is None:
                continue
            roles, detail = got
            hit = any(_norm_header(kw) and _norm_header(kw) in title for kw in seed.get("title_keywords") or [])
            # 全并列消歧(标题/角色数都平): 锚点总数少 = 规则更专,应胜出 —
            # 如签字版表 gc-qzb(7 锚) 与通用 gcl-qd(12 锚) 同锚 7 角色且都无标题命中,
            # 专的 gc-qzb 必须赢。取 -anchors_n 使其与列表顺序无关(seed_defaults 镜像
            # 库/用户在配置 tab 重排都不改变行为)。
            anchors_n = sum(len(v or []) for v in (seed.get("columns") or {}).values())
            key = (1 if hit else 0, detail["roles_n"], -anchors_n)
            if best is None or key > best[0:3]:
                best = (key[0], key[1], key[2], seed, roles)
        if best is not None:
            return best[3], best[4], header_rows
    return _match_seed_deep(rows, seeds)


_DEEP_HEADER_SCAN = 8  # 深扫窗口(标准表头 peek=3 之外,覆盖审批单式表单)


def _match_seed_deep(rows: list, seeds: list[dict]) -> tuple[dict, dict, int] | None:
    """标准表头折叠未命中时的深扫兜底(ssxl-cgjh;严格 seed-only,零 seed 命中零行为)。

    审批单/表单类文档的真实价格表头不在前 3 行: 上方是表单 label:value 行
    (上报项目/制表人/联系电话…,甚至含伪表头 token——'完工时间' 的 '时间'),
    真表头行('计划采购主要物资 | 序号 物资名称 | 数量 | …')被压在 peek 窗口外。
    逐行(≤_DEEP_HEADER_SCAN)找「≥2 个不同角色的 seed 锚命中 + 其上方行命中
    该 seed 标题词」的候选行,再由 _match_one_seed(name+价格角色)确认——
    锚与标题词都来自 seed 自身,通用路径(_collapse_header/classify)零改动。
    返回 (seed, roles, header_rows=候选行idx+1) 或 None。"""
    best: tuple[int, int, dict, dict, int] | None = None  # (roles_n, -anchors_n, seed, roles, header_rows)
    for seed in seeds:
        kws = [k for k in (_norm_header(kw) for kw in seed.get("title_keywords") or []) if k]
        if not kws:
            continue  # 无标题词的 seed 不进深扫(防陌生表头误配)
        anchors_by_role = {
            role: [a for a in (_norm_header(t) for t in (seed["columns"].get(role) or [])) if a]
            for role in _ROLE_ORDER
        }
        anchors_n = sum(len(v or []) for v in (seed.get("columns") or {}).values())
        for ri in range(min(len(rows), _DEEP_HEADER_SCAN)):
            norm_cells = [_norm_header(c) for c in (rows[ri] or [])]
            hit_roles = {
                role
                for role, anchors in anchors_by_role.items()
                if anchors and any(any(a in h for a in anchors) for h in norm_cells if h)
            }
            if len(hit_roles) < 2:
                continue
            title = _title_text(rows[:ri], limit=ri) if ri else ""
            if not any(kw in title for kw in kws):
                continue
            got = _match_one_seed(rows, seed, rows[ri])
            if got is None:
                continue
            roles, detail = got
            key = (detail["roles_n"], -anchors_n)
            if best is None or key > best[0:2]:
                best = (key[0], key[1], seed, roles, ri + 1)
    if best is None:
        return None
    return best[2], best[3], best[4]


def _is_category_row(cells: dict) -> bool:
    """分类行判别: 名称非空 且 数量/单位/价格列全空(设计 §2)。
    价格漏读行通常带数量/单位,不会误判;今天此类行反正被跳过,零损失。"""
    if not (cells.get("name") or "").strip():
        return False
    return not any(
        (cells.get(k) or "").strip()
        for k in ("qty", "unit", "price_unit", "price_total", "price_untaxed")
    )


_SEED_SKIP = {"序号", "合计", "小计", "总计"}


def _is_totals_row(cells: dict) -> bool:
    """合计行守卫(bug-3400): x-band 可能把「合计」标签格落到非名称列,名称格捡到
    数字垃圾、再被 cli 烂行改名救成「合计」→ 泄漏 item。任一映射格命中跳过集
    即整行跳过(此前只查名称格)。"""
    return any((v or "").strip() in _SEED_SKIP for v in cells.values())


def _seed_use_x(rows, cell_bboxes, roles_x) -> bool:
    """x-band 取值前提(单源): roles_x 带名称带,且本表 bboxes 可用。"""
    return bool(roles_x) and "name" in roles_x and _bboxes_usable(rows, cell_bboxes)


def _cells_by_index(row: list, roles: dict) -> dict:
    """按 seed 列号取格(无 bbox 路径与逐行回退共用,判别单源)。"""
    cells = {}
    for role, ci in roles.items():
        cells[role] = (row[ci].strip() if ci is not None and ci < len(row) else "")
    return cells


def _row_price_usable(cells: dict) -> bool:
    """该行映射格能否产出可用价格——镜像 cli._extract_from_tables 的 finalize
    判定(单价/不含税任一可校验,或 合价可校验且工程量>0 可反算)。
    finalize 改判定时必须同步这里(bug-3400 回退触发条件依赖它)。"""
    if validate_price(cells.get("price_unit") or "")[0] is not None:
        return True
    if validate_price(cells.get("price_untaxed") or "")[0] is not None:
        return True
    total = validate_price(cells.get("price_total") or "")[0]
    if total:
        q = parse_qty(cells.get("qty") or "")
        if q and q > 0:
            return True
    return False


def _has_price_signal(cells: dict) -> bool:
    """轻量探针(bug-3400): 映射格的 工程/价格格是否含任何数字。
    真正的 price-less 行(分类行/说明行,价格工程量格全无数字)不得触发回退——
    列号重映射会把错位数字格捡进价格角色,把分类行变成垃圾 item。"""
    return any(
        re.search(r"\d", cells.get(k) or "")
        for k in ("qty", "price_unit", "price_total", "price_untaxed")
    )


def _iter_seed_cells(
    rows: list, roles: dict, header_rows: int, cell_bboxes: list | None = None, roles_x: dict | None = None
):
    """行→角色 cell 映射迭代器(extract_items_seed / seed_category_tail 共用,判别单源)。
    x-band 可用按 x 对齐(抗漂移),否则按列号。yield (row_idx, cells)。"""
    use_x = _seed_use_x(rows, cell_bboxes, roles_x)
    for ri in range(header_rows, len(rows)):
        row = rows[ri]
        if use_x:
            bbox_row = cell_bboxes[ri] if ri < len(cell_bboxes) else []
            yield ri, _row_cells_by_x(row, bbox_row, roles_x)
        else:
            yield ri, _cells_by_index(row, roles)


def extract_items_seed(
    rows: list,
    seed: dict,
    roles: dict,
    header_rows: int,
    cell_bboxes: list | None = None,
    roles_x: dict | None = None,
    initial_category: str | None = None,
) -> list:
    """Seed 路径行提取: 按 seed 角色取单元格 + 分类行上下文传播。

    对齐方式与 extract_items 相同: bbox-x 可用则按 x-band(抗漂移),否则按列号。
    产出 raw item: {name, spec, qty_raw, unit, price_unit_raw, price_total_raw,
    price_untaxed_raw, category, row_idx}。分类行(名称非空+数值列全空)不产 item,
    其名称作为后续 item 的 category,直到下一个分类行。
    initial_category: 跨页续传入口——管线循环把上一表尾部分类传进来(设计§2 修订I2:
    表头重复页/续表页每页都会新开一次调用,不传则分类退化为页内局部)。
    bug-3400: x-band 路径下单行无可用价格且有数字信号时,给 seed 列号映射对该行的
    一次重映射机会(逐行回退,全局 x-band 行为不变)——见循环内注释。"""
    items: list = []
    use_x = _seed_use_x(rows, cell_bboxes, roles_x)
    current_category: str | None = initial_category

    for ri, cells in _iter_seed_cells(rows, roles, header_rows, cell_bboxes, roles_x):
        name = (cells.get("name") or "").strip()
        if not name or name in _SEED_SKIP:
            continue
        if _is_totals_row(cells):
            continue
        if _is_category_row(cells):
            current_category = name
            continue
        if use_x and not _row_price_usable(cells) and _has_price_signal(cells):
            # bug-3400 逐行 x→index 回退: x-band 对大多数行是对的(修复过真实漂移),
            # 但个别行会把价格格映射到粘连/错位格(p115 实弹: price_total 捡到
            # '68. 911346. 15' 粘连串,validate+反算双失败 → 行被当 price-less 丢弃),
            # 而同一行按 seed 列号映射 price_total='834.61' → 反算 1346.15=旧基线。
            # 触发条件(三者同时): x 路径该行无可用价格 + 行内有价格/工程量数字信号
            # (分类/说明行不触发) + 列号重映射确实可用(只升级不降级)。
            ix_cells = _cells_by_index(rows[ri] if ri < len(rows) else [], roles)
            if _row_price_usable(ix_cells):
                cells = ix_cells
                name = (cells.get("name") or "").strip()
                if not name or name in _SEED_SKIP or _is_totals_row(cells):
                    continue
                if _is_category_row(cells):
                    current_category = name
                    continue
        items.append(
            {
                "name": name,
                "spec": (cells.get("spec") or "").strip() or None,
                "qty_raw": cells.get("qty") or None,
                "unit": (cells.get("unit") or "").strip() or None,
                "price_unit_raw": cells.get("price_unit") or "",
                "price_total_raw": cells.get("price_total") or "",
                "price_untaxed_raw": cells.get("price_untaxed") or "",
                "category": current_category,
                "row_idx": ri,
            }
        )
    return items


def seed_category_tail(
    rows: list,
    roles: dict,
    header_rows: int,
    cell_bboxes: list | None = None,
    roles_x: dict | None = None,
    initial_category: str | None = None,
) -> str | None:
    """表内行扫的终态分类(含表尾悬挂分类行),供管线跨表/跨页续传(修订I2)。

    extract_items_seed 的返回值看不到表尾悬挂的分类行(分类行不产 item)——
    「页尾分类行 + 下页首数据行」的桂北式多页清单必须用它取尾态,否则续表
    首页的分类丢失。与 extract_items_seed 共用 _iter_seed_cells/_is_category_row,
    判别逻辑单源,不会漂移。"""
    current = initial_category
    for _ri, cells in _iter_seed_cells(rows, roles, header_rows, cell_bboxes, roles_x):
        name = (cells.get("name") or "").strip()
        if name and name not in _SEED_SKIP and _is_category_row(cells):
            current = name
    return current
