"""FormatProfile → 正文 AST(P1,EAI-CUSTOM 2026-11-15)。

与 ``products_to_ast`` 的四章节兜底并列:当招标文件检测到「投标文件格式/
投标文件目录/商务卷」区段时,优先按招标原文的章节顺序与表格结构装配 AST。

覆盖:
- 标题层级 → section 树(section_id 由 block index 派生,确定性);
- 固定文字 → locked_paragraph(template_id=tender-format:<block>),编辑器禁改;
- 占位符 → placeholder 行内原子,按任务/素材/报价事实填值,未命中保留原文;
- 表格 → table/table_row/table_cell,col_span/row_span 只保留合并起点单元格;
- 目录 → toc_entry(保留招标目录原文,页码可回填);
- 签章/贴图位 → para(slot_id=sig:/img:),先保位置与文字。

纯函数零 IO 零时钟;同一 profile/task/ctx 输入字节级稳定。
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from app.extensions.bid_write.format_profile import _is_format_title, _placeholders

from .ast import _cell, _para, _row

_TOC_PAGE_RE = re.compile(r"([.．·]{2,})\s*(\d+)\s*$")
_FORMAT_TITLE_SECTION_RE = re.compile(r"(投标文件格式|投标文件目录|商务卷|商务部分)")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _first(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _money(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        amount = Decimal(str(value))
    except Exception:  # noqa: BLE001  非数值不猜测
        return str(value)
    return f"{amount:,.2f}"


def _value_map(task: Any, ctx: dict | None) -> dict[str, str]:
    ctx = ctx or {}
    tender = ctx.get("tender") or {}
    material = ctx.get("material") or {}
    products = ctx.get("products") or {}
    bidder = material.get("bidder_profile") or {}
    price = products.get("price_sheet") or {}
    letter = products.get("bid_letter") or {}
    slots = letter.get("slots") or {}
    knobs = ctx.get("knobs") or {}
    return {
        "project_name": _first(getattr(task, "project_name", ""), tender.get("tender.project_name")),
        "lot_name": _first(getattr(task, "lot_name", ""), tender.get("tender.lot_name")),
        "tender_no": _first(getattr(task, "tender_no", ""), tender.get("tender.tender_no")),
        "purchaser_name": _first(tender.get("tender.purchaser_name")),
        "bidder_name": _first(bidder.get("name"), bidder.get("bidder_name"), bidder.get("company_name")),
        "legal_rep_name": _first(bidder.get("legal_rep"), bidder.get("legal_representative")),
        "address": _first(bidder.get("address"), bidder.get("registered_address")),
        "phone": _first(bidder.get("phone"), bidder.get("tel"), bidder.get("telephone")),
        "bank": _first(bidder.get("bank"), bidder.get("bank_name")),
        "account": _first(bidder.get("account"), bidder.get("bank_account")),
        "sign_date": _first(knobs.get("sign_date"), slots.get("sign_date")),
        "amount_cn": _first(price.get("amount_cn"), slots.get("total_amount_cn")),
        "amount_num": _money(_first(price.get("detail_total"), slots.get("total_amount_num"))),
        "deposit": _first(tender.get("tender.deposit_required"), slots.get("deposit_amount")),
        "validity": _first(tender.get("tender.required_validity_days"), slots.get("valid_days")),
    }


_SOURCE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("amount_cn", ("大写", "人民币大写", "金额大写")),
    ("amount_num", ("小写", "小写金额", "总价", "报价", "金额")),
    ("deposit", ("保证金",)),
    ("validity", ("有效期", "投标有效期")),
    ("project_name", ("项目名称", "工程名称", "标的名称")),
    ("lot_name", ("标段", "包号", "分包")),
    ("tender_no", ("招标编号", "采购编号", "项目编号", "文件编号")),
    ("purchaser_name", ("招标人", "采购人", "招标单位", "采购单位")),
    ("legal_rep_name", ("法定代表人", "法人代表", "法人")),
    ("bidder_name", ("投标人名称", "投标人", "公司名称", "供应商名称", "单位名称")),
    ("address", ("地址", "住所")),
    ("phone", ("联系电话", "电话", "联系方式")),
    ("bank", ("开户银行", "开户行", "银行")),
    ("account", ("账号", "账户")),
    ("sign_date", ("签署日期", "投标日期", "日期", "年月日")),
)


def _placeholder_source(item: dict) -> str:
    blob = f"{item.get('label') or ''} {item.get('text') or ''} {item.get('context') or ''}"
    compact = re.sub(r"\s+", "", blob)
    for source, keywords in _SOURCE_KEYWORDS:
        if any(keyword in compact for keyword in keywords):
            return source
    if str(item.get("type") or "") == "date_blank":
        return "sign_date"
    return ""


def _placeholder_node(item: dict, values: dict[str, str], block_index: int) -> dict:
    start = int(item.get("start") or 0)
    source = _placeholder_source(item)
    value = values.get(source, "") if source else ""
    return {
        "type": "placeholder",
        "attrs": {
            "slot_id": f"fmt-{block_index}-{start}",
            "placeholder_type": str(item.get("type") or ""),
            "label": str(item.get("label") or ""),
            "value": value,
            "required": not bool(value),
            "source": source,
            "raw": str(item.get("text") or ""),
        },
    }


def _inline_segments(
    text: str,
    placeholders: list[dict],
    values: dict[str, str],
    block_index: int,
) -> list[dict]:
    source = str(text or "")
    items = [item for item in placeholders if isinstance(item, dict)]
    items.sort(key=lambda item: int(item.get("start") or 0))
    out: list[dict] = []
    cursor = 0
    for item in items:
        start = max(0, int(item.get("start") or 0))
        end = min(len(source), int(item.get("end") or 0))
        if start < cursor or end <= start:
            continue
        if start > cursor:
            out.append({"type": "text", "text": source[cursor:start]})
        out.append(_placeholder_node(item, values, block_index))
        cursor = end
    if cursor < len(source):
        out.append({"type": "text", "text": source[cursor:]})
    if not out and source:
        out.append({"type": "text", "text": source})
    return out


def _locked(index: int, content: list[dict]) -> dict:
    return {
        "type": "locked_paragraph",
        "attrs": {"template_id": f"tender-format:{index}", "similarity_floor": 0.98},
        "content": content,
    }


def _toc_entry(text: str) -> dict:
    raw = str(text or "").strip()
    match = _TOC_PAGE_RE.search(raw)
    title = _TOC_PAGE_RE.sub("", raw).strip() or raw
    page = match.group(2) if match else "—"
    return {"type": "toc_entry", "attrs": {"title": title, "page_placeholder": page}}


def _table_type(table: dict) -> str:
    header = " ".join(str(item or "") for item in table.get("headers") or [])
    if any(token in header for token in ("报价", "金额", "单价", "合计")):
        return "price"
    if any(token in header for token in ("响应", "偏离", "条款")):
        return "response"
    return "list"


def _table_ast(block: dict, values: dict[str, str]) -> dict:
    table = block.get("table") or {}
    rows = [row for row in table.get("rows") or [] if isinstance(row, dict)]
    starts: list[list[tuple[int, dict]]] = []
    for row in rows:
        column = 0
        entries: list[tuple[int, dict]] = []
        for cell in row.get("cells") or []:
            if not isinstance(cell, dict):
                continue
            entries.append((column, cell))
            column += max(1, int(cell.get("col_span") or 1))
        starts.append(entries)

    block_index = int(block.get("index") or 0)
    covered: set[tuple[int, int]] = set()
    ast_rows: list[dict] = []
    for row_index, entries in enumerate(starts):
        cells: list[dict] = []
        for column, cell in entries:
            if (row_index, column) in covered:
                continue
            if str(cell.get("v_merge") or "") == "continue":
                continue
            row_span = 1
            next_row = row_index + 1
            while next_row < len(starts):
                continuation = next((item for grid, item in starts[next_row] if grid == column), None)
                if continuation is None or str(continuation.get("v_merge") or "") != "continue":
                    break
                row_span += 1
                covered.add((next_row, column))
                next_row += 1

            cell_text = str(cell.get("text") or "").replace("\r\n", "\n").replace("\r", "\n")
            inline = _inline_segments(cell_text, _placeholders(cell_text), values, block_index)
            node = _cell(
                "",
                "name" if column == 0 else "remark",
                col_span=max(1, int(cell.get("col_span") or 1)),
                row_span=row_span,
            )
            if inline:
                node["content"] = inline
            cells.append(node)
        if cells:
            ast_rows.append(_row(f"F{block_index}-R{row_index}", cells))

    if not ast_rows:
        ast_rows.append(_row(f"F{block_index}-R0", [_cell("", "name")]))
    return {
        "type": "table",
        "attrs": {"table_type": _table_type(table), "source_index": int(block.get("table_index") or -1)},
        "content": ast_rows,
    }


def _fill_empty(nodes: list[dict]) -> None:
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("type") in ("doc", "section"):
            content = node.setdefault("content", [])
            _fill_empty(content)
            if node.get("type") == "section" and not content:
                content.append(_para(""))
    if not nodes:
        nodes.append(_para(""))


def format_profile_to_ast(
    profile: dict,
    *,
    task: Any = None,
    ctx: dict | None = None,
) -> dict | None:
    """按招标格式装配 AST;未检测到格式区段/无 blocks 返回 None(调用方走四章节兜底)。"""

    if not isinstance(profile, dict) or not profile.get("supported"):
        return None
    section = profile.get("format_section") or {}
    if not section.get("detected"):
        return None
    blocks = [block for block in profile.get("blocks") or [] if isinstance(block, dict)]
    if not blocks:
        return None

    values = _value_map(task, ctx)
    fixed_blocks = {int(item.get("block_index")) for item in profile.get("fixed_texts") or [] if item.get("block_index") is not None}
    signature_blocks = {int(item.get("block_index")) for item in profile.get("signatures") or [] if item.get("block_index") is not None}
    image_blocks = {int(item.get("block_index")) for item in profile.get("image_slots") or [] if item.get("block_index") is not None}
    toc_entries = {int(item.get("block_index")) for item in section.get("toc_entries") or [] if isinstance(item, dict) and item.get("block_index") is not None}
    toc_titles = {int(chapter.get("block_index")) for chapter in profile.get("chapters") or [] if isinstance(chapter, dict) and chapter.get("kind") == "toc" and chapter.get("block_index") is not None}

    root: list[dict] = []
    stack: list[tuple[int, dict]] = []

    def add(node: dict) -> None:
        if stack:
            stack[-1][1]["content"].append(node)
        else:
            root.append(node)

    def open_section(level: int, title: str, block_index: int) -> None:
        level = min(max(int(level or 1), 1), 4)
        while stack and stack[-1][0] >= level:
            stack.pop()
        node = {
            "type": "section",
            "attrs": {"level": level, "title": title, "section_id": f"S-fmt-{block_index}"},
            "content": [],
        }
        if stack:
            stack[-1][1]["content"].append(node)
        else:
            root.append(node)
        stack.append((level, node))

    for block in blocks:
        kind = str(block.get("kind") or "")
        block_index = int(block.get("index") or 0)
        if kind == "table":
            add(_table_ast(block, values))
            continue
        if kind != "paragraph":
            continue

        text = str(block.get("text") or "")
        if not text:
            continue
        if block_index in toc_entries:
            add(_toc_entry(text))
            continue

        heading_level = int(block.get("heading_level") or 0)
        is_heading = bool(block.get("is_heading")) or heading_level > 0
        if is_heading and block_index not in toc_titles and not _is_format_title(text):
            open_section(heading_level or 1, text, block_index)
            continue
        if block_index in toc_titles or (is_heading and _is_format_title(text)) or (_FORMAT_TITLE_SECTION_RE.search(text) and len(text) < 30):
            # 格式封皮/目录标题保留为正文段落,不单独切册。
            add(_para(text))
            continue

        placeholders = [item for item in block.get("placeholders") or [] if isinstance(item, dict)]
        if placeholders:
            add(_locked(block_index, _inline_segments(text, placeholders, values, block_index)))
            continue
        if block_index in fixed_blocks:
            add(_locked(block_index, [{"type": "text", "text": text}]))
            continue
        if block_index in signature_blocks:
            add(_para(text, slot_id=f"sig:{block_index}"))
            continue
        if block_index in image_blocks:
            add(_para(text, slot_id=f"img:{block_index}"))
            continue
        add(_para(text))

    _fill_empty(root)
    return {"type": "doc", "content": root}
