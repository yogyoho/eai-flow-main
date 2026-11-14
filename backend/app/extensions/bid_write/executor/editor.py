"""编辑器真执行器桥(批三十,EAI-CUSTOM 2026-11-14)——把云端正文 AST 覆盖到
任务生成 ctx,交真实断言执行器(43 条注册断言)判定,再把失败结果按编辑器锚点
映射成 ``{D0|D1|D2}`` 侧信道。只读:不落 skill_run、不改任务/文档。

口径:
- **价格表**是编辑器真值:行 id=table_row.row_id(生成器约定与招标清单 id 同源),
  qty 列取 ``col_role=qty``,单价取 ``col_role=unit``(当前 schema 无独立单价角色;
  ``unit`` 列在报价表内承载单价,单位度量沿用任务 ctx 同名行),金额取
  ``amount_cell role=amount``,合计取 ``role=total_num``、大写取 ``role=total_cn``。
- **商务响应表**是编辑器真值:row_id 约定=clause_id;结论取 enum_cell.current,
  偏离原因/替代方案取同 row_id 的 deviation_note;star/证据/要求摘录沿用任务 ctx
  同 clause_id 行(素材实体面未进 AST)。
- **投标函文本**是编辑器真值:金额取投标函章节内最大金额数字,大写取「大写:…」
  括注;其余槽位/签章/承诺沿用任务 ctx(本批不重建)。
- 附件索引表尚未进 AST schema → AI 面沿用任务生成 ctx(边界诚实,挂后续批)。
- row_id 全文唯一是生成器约定;重复即 ValueError(router 422),不静默首配。
- 失败结果锚点:price:{row_id} / rt:{row_id} / devnote:{row_id} / todo:{id} /
  投标函段落 slot;无法定位的失败只进状态栏,不伪造段级红点。
"""

from __future__ import annotations

import copy
import re
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher

from app.extensions.bid_write.executor.models import (
    ST_ERROR,
    ST_FAIL,
    ST_SKIPPED,
    RunReport,
)
from app.extensions.bid_write.executor.runner import run_assertions
from app.extensions.bid_write.executor.validators import norm_text
from app.extensions.bid_write.executor.wordscan import scan_text, words_for

_SEVERITY = {"D0": 3, "D1": 2, "D2": 1}
_LEVELS = frozenset(_SEVERITY)

_AMOUNT_RE = re.compile(r"-?\d[\d,，]*(?:\.\d+)?")
_CN_AFTER_LABEL = re.compile(r"大写\s*[:：]\s*([零壹贰叁肆伍陆柒捌玖拾佰仟万亿元圆角分整]+)")

_TONE_WORDS = words_for("placeholder", "absolute", "redline")
_BL_WORDS = words_for("absolute", "redline", "vague", "placeholder", "price_vague")
_RT_EMPTY_WORDS = words_for("empty_answer")
_RT_PLACEHOLDER_WORDS = words_for("placeholder")
_RT_DEVIATION_MARKERS = ("无法满足", "不满足", "有异议", "不予响应", "难于满足", "负偏离")

_NEGATIVE = "负偏离"


# ── AST helpers ─────────────────────────────────────────────────────────────


def _iter_nodes(node: dict, parent: dict | None = None):
    yield node, parent
    for child in node.get("content") or []:
        if isinstance(child, dict):
            yield from _iter_nodes(child, node)


def _attrs(node: dict) -> dict:
    value = node.get("attrs")
    return value if isinstance(value, dict) else {}


def _node_text(node: dict) -> str:
    """文本投影(attachment_ref 记为「见附件X」,与 AI-003 正文引用面同词形)。"""
    kind = node.get("type")
    if kind == "text":
        return str(node.get("text") or "")
    if kind == "attachment_ref":
        return f"见附件{_attrs(node).get('attachment_no') or ''}"
    return "".join(_node_text(child) for child in node.get("content") or [] if isinstance(child, dict))


def _parse_dec(value) -> Decimal | None:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("，", "")
    match = _AMOUNT_RE.search(text)
    if not match:
        return None
    try:
        return Decimal(match.group(0))
    except InvalidOperation:
        return None


def _plain(value: Decimal | None):
    if value is None:
        return None
    quantized = value.quantize(Decimal("0.01"))
    return int(quantized) if quantized == quantized.to_integral_value() else float(quantized)


def _cell_text(cell: dict) -> str:
    return _node_text(cell).strip()


def _cell_by_role(cells: list, role: str) -> dict | None:
    for cell in cells:
        if not isinstance(cell, dict) or cell.get("type") != "table_cell":
            continue
        if str(_attrs(cell).get("col_role") or "") == role:
            return cell
    return None


def _amount_cell_by_role(cells: list, role: str) -> dict | None:
    for cell in cells:
        if not isinstance(cell, dict) or cell.get("type") != "amount_cell":
            continue
        if str(_attrs(cell).get("role") or "") == role:
            return cell
    return None


def _enum_cell(row: dict) -> dict | None:
    for cell in row.get("content") or []:
        if isinstance(cell, dict) and cell.get("type") == "enum_cell":
            return cell
    return None


def _find_table(ast: dict, table_type: str) -> dict | None:
    for node, _parent in _iter_nodes(ast):
        if node.get("type") == "table" and str(_attrs(node).get("table_type") or "") == table_type:
            return node
    return None


def _rows(table: dict) -> list[dict]:
    return [row for row in table.get("content") or [] if isinstance(row, dict) and row.get("type") == "table_row"]


def _row_id(row: dict, index: int) -> str:
    return str(_attrs(row).get("row_id") or f"row[{index}]")


def _row_key(row: dict) -> str:
    return (norm_text(row.get("id")) or norm_text(row.get("name"))).lower()


def _merge(states: dict, key: str | None, level: str, code: str, message: str) -> None:
    if not key or level not in _LEVELS:
        return
    current = states.get(key)
    if current is None or _SEVERITY[level] > _SEVERITY[current["state"]]:
        states[key] = {"state": level, "err_code": code, "message": message}


# ── overlays ────────────────────────────────────────────────────────────────


def _price_overlay(base_ps: dict, ast: dict) -> tuple[dict, dict]:
    table = _find_table(ast, "price")
    if table is None:
        return base_ps, {"rows": {}, "total_row": None}

    base_rows = [r for r in base_ps.get("rows") or [] if isinstance(r, dict)]
    base_by_id = {norm_text(r.get("id")): r for r in base_rows if norm_text(r.get("id"))}
    base_by_name = {norm_text(r.get("name")).lower(): r for r in base_rows if norm_text(r.get("name"))}

    rows: list[dict] = []
    meta_rows: dict[str, dict] = {}
    seen: set[str] = set()
    total_row_id: str | None = None
    total_num: Decimal | None = None
    total_cn = ""

    for index, row in enumerate(_rows(table)):
        cells = [c for c in row.get("content") or [] if isinstance(c, dict)]
        rid = _row_id(row, index)
        total_cell = _amount_cell_by_role(cells, "total_num")
        cn_cell = _amount_cell_by_role(cells, "total_cn")
        if total_cell is not None:
            total_row_id = rid
            total_num = _parse_dec(_cell_text(total_cell))
            total_cn = _cell_text(cn_cell) if cn_cell is not None else ""
            continue
        if rid in seen:
            raise ValueError(f"报价表 row_id 重复: {rid!r}(row_id 须全文唯一)")
        seen.add(rid)

        name_cell = _cell_by_role(cells, "name")
        qty_cell = _cell_by_role(cells, "qty")
        unit_cell = _cell_by_role(cells, "unit")
        amount_cell = _amount_cell_by_role(cells, "amount")
        name = _cell_text(name_cell) if name_cell is not None else ""
        qty = _parse_dec(_cell_text(qty_cell)) if qty_cell is not None else None
        unit_price = _parse_dec(_cell_text(unit_cell)) if unit_cell is not None else None
        amount = _parse_dec(_cell_text(amount_cell)) if amount_cell is not None else None

        base = base_by_id.get(rid) or base_by_name.get(norm_text(name).lower()) or {}
        rows.append(
            {
                "id": rid,
                "name": name or base.get("name"),
                "qty": _plain(qty),
                "unit": str(base.get("unit") or ""),
                "unit_price": _plain(unit_price),
                "amount": _plain(amount),
                "price_mode": base.get("price_mode"),
                "tax_rate": base.get("tax_rate"),
            }
        )
        meta_rows[rid] = {
            "qty": qty,
            "unit_price": unit_price,
            "amount": amount,
            "name": name,
            "unit": str(base.get("unit") or ""),
            "row": row,
        }

    detail = sum((r["amount"] for r in meta_rows.values() if r.get("amount") is not None), Decimal("0"))
    summary = total_num if total_num is not None else detail
    base_detail = _parse_dec(base_ps.get("detail_total"))
    if total_cn:
        amount_cn = total_cn
    elif base_detail is not None and base_detail == detail:
        amount_cn = str(base_ps.get("amount_cn") or "")
    else:
        amount_cn = ""

    replay_ok = detail == summary and all(m["qty"] is not None and m["unit_price"] is not None and m["amount"] is not None and abs(m["qty"] * m["unit_price"] - m["amount"]) <= Decimal("0.005") for m in meta_rows.values())

    overlay = {
        **base_ps,
        "rows": rows,
        "detail_total": _plain(detail),
        "summary_total": _plain(summary),
        "open_letter_total": _plain(summary),
        "amount_cn": amount_cn,
    }
    meta = {"rows": meta_rows, "total_row": total_row_id, "replay_ok": replay_ok}
    return overlay, meta


def _letter_sections(ast: dict) -> list[dict]:
    return [node for node, _parent in _iter_nodes(ast) if node.get("type") == "section" and "投标函" in str(_attrs(node).get("title") or "")]


def _letter_overlay(base_bl: dict, ast: dict) -> tuple[dict, dict]:
    sections = _letter_sections(ast)
    if not sections:
        return base_bl, {"anchor": None, "paras": []}

    texts = [_node_text(section) for section in sections]
    joined = "\n".join(texts)
    numbers = [n for n in (_parse_dec(t) for t in _split_amount_tokens(joined)) if n is not None and n >= 1000]
    amount = max(numbers) if numbers else None
    cn_match = _CN_AFTER_LABEL.search(joined)

    slots = dict(base_bl.get("slots") or {})
    if amount is not None:
        slots["total_amount_num"] = _plain(amount)
    if cn_match:
        slots["total_amount_cn"] = cn_match.group(1)

    paras: list[dict] = []
    anchor: str | None = None
    for section in sections:
        for node, _parent in _iter_nodes(section):
            if node.get("type") not in ("para", "locked_paragraph"):
                continue
            slot = str(_attrs(node).get("slot_id") or _attrs(node).get("template_id") or "")
            text = _node_text(node)
            if slot and anchor is None and _parse_dec(text) is not None:
                anchor = slot
            if slot:
                paras.append({"anchor": slot, "text": text})

    if anchor is None and paras:
        anchor = paras[0]["anchor"]

    return {**base_bl, "slots": slots, "text": joined}, {"anchor": anchor, "paras": paras}


def _split_amount_tokens(text: str) -> list[str]:
    return [m.group(0) for m in _AMOUNT_RE.finditer(text or "")]


def _collect_deviation_notes(ast: dict) -> dict[str, dict]:
    notes: dict[str, dict] = {}
    for node, _parent in _iter_nodes(ast):
        if node.get("type") != "deviation_note":
            continue
        rid = str(_attrs(node).get("row_id") or "")
        reason = ""
        alt = ""
        filled = False
        for child in node.get("content") or []:
            if not isinstance(child, dict):
                continue
            label = str(_attrs(child).get("label") or "")
            text = _node_text(child).strip()
            filled = filled or bool(text)
            if label == "偏离原因":
                reason = text
            elif label == "替代方案":
                alt = text
        if rid:
            notes[rid] = {"reason": reason, "alt": alt, "filled": filled}
    return notes


def _collect_negative_rows(ast: dict) -> dict[str, str]:
    rows: dict[str, str] = {}
    for node, parent in _iter_nodes(ast):
        if node.get("type") != "enum_cell" or parent is None or parent.get("type") != "table_row":
            continue
        current = str(_attrs(node).get("current") or _cell_text(node) or "")
        if current.strip() != _NEGATIVE:
            continue
        rid = str(_attrs(parent).get("row_id") or "")
        if rid:
            rows[rid] = current.strip()
    return rows


def _response_overlay(base_rt: dict, ast: dict) -> tuple[dict, dict]:
    table = _find_table(ast, "response")
    if table is None:
        return base_rt, {"rows": {}, "notes": _collect_deviation_notes(ast)}
    base_rows = [r for r in base_rt.get("rows") or [] if isinstance(r, dict)]
    base_by_id = {norm_text(r.get("clause_id")): r for r in base_rows if norm_text(r.get("clause_id"))}
    notes = _collect_deviation_notes(ast)

    rows: list[dict] = []
    meta_rows: dict[str, dict] = {}
    seen: set[str] = set()
    for index, row in enumerate(_rows(table)):
        rid = _row_id(row, index)
        if rid in seen:
            raise ValueError(f"响应表 row_id 重复: {rid!r}(row_id 须全文唯一)")
        seen.add(rid)
        base = base_by_id.get(rid) or {}
        enum = _enum_cell(row)
        conclusion = ""
        if enum is not None:
            conclusion = str(_attrs(enum).get("current") or _cell_text(enum) or "").strip()
        conclusion = conclusion or str(base.get("conclusion") or "完全响应")

        cells = [c for c in row.get("content") or [] if isinstance(c, dict) and c.get("type") == "table_cell"]
        parts = []
        for cell in cells:
            role = str(_attrs(cell).get("col_role") or "")
            if role in ("", "remark"):
                text = _cell_text(cell)
                if text:
                    parts.append(text)
        response_text = "；".join(parts) or str(base.get("response_text") or "")
        note = notes.get(rid) or {}
        rows.append(
            {
                "clause_id": rid,
                "star": bool(base.get("star")),
                "conclusion": conclusion,
                "response_text": response_text,
                "requirement_excerpt": str(base.get("requirement_excerpt") or ""),
                "evidence_refs": list(base.get("evidence_refs") or []),
                "entity_refs": list(base.get("entity_refs") or []),
                "deviation_reason": note.get("reason") or None,
                "replacement_plan": note.get("alt") or None,
            }
        )
        meta_rows[rid] = {"conclusion": conclusion, "response_text": response_text, "base": base}

    star_ids = list(base_rt.get("matrix_star_clause_ids") or [])
    if not star_ids:
        star_ids = [r["clause_id"] for r in rows if r["star"]]

    overlaps: dict[str, float] = {}
    for row in rows:
        excerpt = norm_text(row.get("requirement_excerpt"))
        if not excerpt:
            continue
        base_excerpt = norm_text((base_by_id.get(row["clause_id"]) or {}).get("requirement_excerpt"))
        overlaps[row["clause_id"]] = 1.0 if excerpt == base_excerpt else round(SequenceMatcher(None, excerpt, base_excerpt).ratio(), 4)

    overlay = {**base_rt, "rows": rows, "matrix_star_clause_ids": star_ids, "rt_excerpt_overlaps": overlaps}
    return overlay, {"rows": meta_rows, "notes": notes, "overlaps": overlaps}


def _base_meta(ast: dict) -> dict:
    paras: list[dict] = []
    for node, _parent in _iter_nodes(ast):
        if node.get("type") not in ("para", "locked_paragraph"):
            continue
        slot = str(_attrs(node).get("slot_id") or _attrs(node).get("template_id") or "")
        if slot:
            paras.append({"anchor": slot, "text": _node_text(node)})
    notes = _collect_deviation_notes(ast)
    negatives = _collect_negative_rows(ast)
    return {"paras": paras, "notes": notes, "negatives": negatives}


# ── editor-facing state mapping ────────────────────────────────────────────


def _reflect_ast_states(ast: dict, states: dict) -> None:
    """编辑器结构性事实:todo 占位/文中既存 status_mark/展开面闭环与孤儿。

    这些不是“新断言”:todo 是 AST 原子占位、status_mark 是生成器快照、展开面
    闭环与后端 SK-RT-005 同口径(双字段非空)。"""
    notes = _collect_deviation_notes(ast)
    negatives = _collect_negative_rows(ast)

    for index, (node, _parent) in enumerate(_iter_nodes(ast)):
        if node.get("type") != "todo_block":
            continue
        attrs = _attrs(node)
        key = f"todo:{attrs.get('pending_item_id') or f'row[{index}]'}"
        level = "D0" if str(attrs.get("level") or "D0") == "D0" else "D1"
        states[key] = {
            "state": level,
            "err_code": "",
            "message": f"缺件:{attrs.get('missing') or '待补'}",
        }

    for rid in negatives:
        note = notes.get(rid)
        if not note or not note.get("reason") or not note.get("alt"):
            _merge(states, f"devnote:{rid}", "D0", "SK-RT-005", "负偏离未闭环:需偏离原因+替代方案")
    for rid, note in notes.items():
        if rid in negatives or not note.get("filled"):
            continue
        _merge(states, f"devnote:{rid}", "D1", "SK-RT-005", "响应策略已非负偏离,展开面未清理(撤回或手删)")

    _reflect_status_marks(ast, states)


def _reflect_status_marks(ast: dict, states: dict) -> None:
    def visit(node: dict, anchor: str | None, table_type: str | None = None) -> None:
        kind = node.get("type")
        if kind == "table":
            table_type = str(_attrs(node).get("table_type") or "")
        elif kind == "table_row":
            rid = str(_attrs(node).get("row_id") or "")
            if rid and table_type == "price":
                anchor = f"price:{rid}"
            elif rid and table_type == "response":
                anchor = f"rt:{rid}"
        elif kind in ("para", "locked_paragraph"):
            slot = str(_attrs(node).get("slot_id") or _attrs(node).get("template_id") or "")
            if slot:
                anchor = slot
        elif kind == "text" and anchor:
            for mark in node.get("marks") or []:
                if not isinstance(mark, dict) or mark.get("type") != "status_mark":
                    continue
                attrs = _attrs(mark)
                level = str(attrs.get("state") or "D1")
                if level in ("D0", "D1"):
                    _merge(states, anchor, level, str(attrs.get("err_code") or ""), "文中既存标记(生成器/执行器快照)")
        for child in node.get("content") or []:
            if isinstance(child, dict):
                visit(child, anchor, table_type)

    visit(ast, None)


def _price_rows_mismatch(meta: dict) -> list[str]:
    offenders: list[str] = []
    for rid, row in meta.get("price", {}).get("rows", {}).items():
        qty, price, amount = row.get("qty"), row.get("unit_price"), row.get("amount")
        if qty is not None and price is not None and amount is not None and abs(qty * price - amount) > Decimal("0.005"):
            offenders.append(rid)
    return offenders


def _response_rows_by(meta: dict, predicate) -> list[str]:
    return [rid for rid, row in meta.get("response", {}).get("rows", {}).items() if predicate(row)]


def _map_results(ctx: dict, meta: dict, report: RunReport, states: dict) -> None:
    tender = ctx.get("tender") or {}
    tender_boq = [r for r in tender.get("tender.boq_items") or [] if isinstance(r, dict)]
    tender_map = {_row_key(r): r for r in tender_boq}
    price_rows = meta.get("price", {}).get("rows", {})
    total_row = meta.get("price", {}).get("total_row")
    letter_anchor = meta.get("letter", {}).get("anchor")
    response_rows = meta.get("response", {}).get("rows", {})

    for result in report.results:
        if result.status not in (ST_FAIL, ST_ERROR):
            continue
        level = result.level
        if level not in _LEVELS:
            continue
        code = result.assertion_id
        msg = result.message or ""
        anchored = False

        if code == "SK-PS-007":
            for rid, row in price_rows.items():
                if row.get("unit_price") is None or row["unit_price"] <= 0:
                    _merge(states, f"price:{rid}", level, code, msg)
                    anchored = True
        elif code == "SK-PS-008":
            offenders = _price_rows_mismatch(meta) or ([total_row] if total_row else [])
            for rid in offenders:
                _merge(states, f"price:{rid}", level, code, msg)
                anchored = True
        elif code == "SK-PS-001":
            for rid, row in price_rows.items():
                if _row_key({"id": rid, "name": row.get("name")}) not in tender_map:
                    _merge(states, f"price:{rid}", level, code, msg)
                    anchored = True
        elif code == "SK-PS-002":
            for rid, row in price_rows.items():
                tender_row = tender_map.get(_row_key({"id": rid, "name": row.get("name")}))
                if tender_row is None:
                    continue
                qty = row.get("qty")
                if qty is None or Decimal(str(qty)) != Decimal(str(tender_row.get("qty"))):
                    _merge(states, f"price:{rid}", level, code, msg)
                    anchored = True
                elif norm_text(row.get("unit")) != norm_text(tender_row.get("unit")):
                    _merge(states, f"price:{rid}", level, code, msg)
                    anchored = True
        elif code == "SK-PS-003":
            for key in (f"price:{total_row}" if total_row else None, letter_anchor):
                _merge(states, key, level, code, msg)
                anchored = anchored or bool(key)
        elif code in ("SK-PS-004", "SK-PS-005", "SK-PS-006", "SK-PS-009", "SK-PS-010"):
            if total_row:
                _merge(states, f"price:{total_row}", level, code, msg)
                anchored = True
            elif letter_anchor and code in ("SK-PS-006", "SK-PS-010"):
                _merge(states, letter_anchor, level, code, msg)
                anchored = True
        elif code == "SK-RT-002":
            for rid, row in response_rows.items():
                if row.get("base", {}).get("star") and row.get("conclusion") == _NEGATIVE:
                    _merge(states, f"rt:{rid}", level, code, msg)
                    anchored = True
        elif code == "SK-RT-003":
            for rid, row in response_rows.items():
                if scan_text(norm_text(row.get("response_text")), _RT_EMPTY_WORDS):
                    _merge(states, f"rt:{rid}", level, code, msg)
                    anchored = True
        elif code == "SK-RT-005":
            for rid, row in response_rows.items():
                if row.get("conclusion") != _NEGATIVE:
                    continue
                note = meta.get("response", {}).get("notes", {}).get(rid) or {}
                if not note.get("reason") or not note.get("alt"):
                    _merge(states, f"devnote:{rid}", level, code, msg)
                    anchored = True
        elif code == "SK-RT-007":
            for rid, row in response_rows.items():
                refs = row.get("base", {}).get("evidence_refs")
                if not isinstance(refs, list) or not refs:
                    _merge(states, f"rt:{rid}", level, code, msg)
                    anchored = True
        elif code == "SK-RT-008":
            for rid, row in response_rows.items():
                if row.get("conclusion") != "完全响应":
                    continue
                text = norm_text(row.get("response_text"))
                if any(marker in text for marker in _RT_DEVIATION_MARKERS):
                    _merge(states, f"rt:{rid}", level, code, msg)
                    anchored = True
        elif code == "SK-RT-009":
            for rid, row in response_rows.items():
                if scan_text(norm_text(row.get("response_text")), _RT_PLACEHOLDER_WORDS):
                    _merge(states, f"rt:{rid}", level, code, msg)
                    anchored = True
        elif code == "SK-BL-006" or code in ("SK-CMN-001", "SK-CMN-002"):
            # BL-006/CMN 词级命中定位到含词段落(有 slot 才可装饰)
            words = _BL_WORDS if code == "SK-BL-006" else _TONE_WORDS
            for para in meta.get("paras", []):
                if scan_text(norm_text(para.get("text")), words):
                    _merge(states, para.get("anchor"), level, code, msg)
                    anchored = True
            if not anchored and letter_anchor:
                _merge(states, letter_anchor, level, code, msg)
                anchored = True
        elif code.startswith("SK-BL-"):
            _merge(states, letter_anchor, level, code, msg)
            anchored = anchored or bool(letter_anchor)

        # 无法定位到节点的失败:只进状态栏(不伪造段级红点)
        _ = anchored

    # D0 短路会把同技能后续断言标 SKIPPED,但行级事实仍然成立:补锚点时按
    # 具体条件重算(码=事实对应断言,级=静态 D0),不让「明细行算错」只显示在
    # 合计行上。SKIPPED 仍不改变报告口径(报告里照旧是 SKIPPED,不冒充 PASS)。
    if any(r.skill == "PS" and r.status in (ST_FAIL, ST_ERROR) for r in report.results):
        for rid in _price_rows_mismatch(meta):
            _merge(states, f"price:{rid}", "D0", "SK-PS-008", "行金额失配:qty×单价≠金额")
        for rid, row in price_rows.items():
            if row.get("unit_price") is None or row["unit_price"] <= 0:
                _merge(states, f"price:{rid}", "D0", "SK-PS-007", "空/非正单价(保留空格不导出)")
            key = _row_key({"id": rid, "name": row.get("name")})
            tender_row = tender_map.get(key)
            if tender_row is None:
                continue
            qty = row.get("qty")
            if qty is None or Decimal(str(qty)) != Decimal(str(tender_row.get("qty"))):
                _merge(states, f"price:{rid}", "D0", "SK-PS-002", "数量与招标清单不一致")
            elif norm_text(row.get("unit")) != norm_text(tender_row.get("unit")):
                _merge(states, f"price:{rid}", "D0", "SK-PS-002", "单位与招标清单不一致")

    if any(r.skill == "RT" and r.status in (ST_FAIL, ST_ERROR) for r in report.results):
        for rid, row in response_rows.items():
            if scan_text(norm_text(row.get("response_text")), _RT_EMPTY_WORDS):
                _merge(states, f"rt:{rid}", "D0", "SK-RT-003", "空应答(无参数化内容)")
            if scan_text(norm_text(row.get("response_text")), _RT_PLACEHOLDER_WORDS):
                _merge(states, f"rt:{rid}", "D0", "SK-RT-009", "响应文本含占位符")
            if row.get("conclusion") == "完全响应":
                text = norm_text(row.get("response_text"))
                if any(marker in text for marker in _RT_DEVIATION_MARKERS):
                    _merge(states, f"rt:{rid}", "D0", "SK-RT-008", "「完全响应」正文含偏离表述")
            refs = row.get("base", {}).get("evidence_refs")
            if not isinstance(refs, list) or not refs:
                _merge(states, f"rt:{rid}", "D0", "SK-RT-007", "证据缺面(evidence_refs 空)")


def _skipped_from(report: RunReport) -> list[dict]:
    grouped: dict[str, dict] = {}
    for result in report.results:
        if result.status != ST_SKIPPED:
            continue
        item = grouped.setdefault(result.assertion_id, {"code": result.assertion_id, "count": 0, "reason": result.message})
        item["count"] += 1
        if not item.get("reason"):
            item["reason"] = result.message
    return [grouped[key] for key in sorted(grouped)]


def _summary(states: dict) -> dict:
    counts = {"d0": 0, "d1": 0, "d2": 0}
    for state in states.values():
        if state["state"] == "D0":
            counts["d0"] += 1
        elif state["state"] == "D1":
            counts["d1"] += 1
        elif state["state"] == "D2":
            counts["d2"] += 1
    return counts


def prepare_editor_ctx(base_ctx: dict, ast: dict) -> tuple[dict, dict]:
    """把冻结 AST 覆盖到任务 ctx（导出 gate 与编辑器断言共用同一事实面）。

    Returns:
        ``(ctx, meta)``；ctx 已合并 price/response/letter 与 pre.* 断言输入。

    Raises:
        ValueError: ast 非法 / row_id 重复。
    """
    if not isinstance(ast, dict) or ast.get("type") != "doc":
        raise ValueError('ast 根节点 type 必须为 "doc"')

    ctx = copy.deepcopy(base_ctx or {})
    products = ctx.setdefault("products", {})
    if not isinstance(products, dict):
        raise ValueError("任务上下文 products 形态非法")

    meta: dict = _base_meta(ast)
    pre = ctx.setdefault("pre", {})

    price_sheet, price_meta = _price_overlay(products.get("price_sheet") or {}, ast)
    products["price_sheet"] = price_sheet
    meta["price"] = price_meta
    if price_meta.get("replay_ok") is not None:
        pre["ps_replay_equal"] = bool(price_meta["replay_ok"])

    bid_letter, letter_meta = _letter_overlay(products.get("bid_letter") or {}, ast)
    products["bid_letter"] = bid_letter
    meta["letter"] = letter_meta

    response_table, response_meta = _response_overlay(products.get("response_table") or {}, ast)
    products["response_table"] = response_table
    meta["response"] = response_meta
    if response_meta.get("overlaps") is not None:
        pre["rt_excerpt_overlaps"] = response_meta["overlaps"]

    slots = bid_letter.get("slots") or {}
    if slots.get("total_amount_num") is not None and price_sheet.get("detail_total") is not None:
        pre["rt_cross_field"] = {"total_amount": {"rt": slots["total_amount_num"], "other": price_sheet["detail_total"]}}

    return ctx, meta


def run_editor_assertions(base_ctx: dict, ast: dict, skills: tuple[str, ...] | list[str] | None = None) -> dict:
    """真实执行器 → 编辑器侧信道。返回 JSON 可序列化 payload。

    Raises:
        ValueError: ast 非法 / row_id 重复(router 422)。
    """
    ctx, meta = prepare_editor_ctx(base_ctx, ast)

    report = run_assertions(ctx, skills)

    states: dict[str, dict] = {}
    _reflect_ast_states(ast, states)
    _map_results(ctx, meta, report, states)

    skipped = _skipped_from(report)
    return {
        "states": states,
        "skipped": skipped,
        "run_at": datetime.now(UTC).isoformat(),
        "results": [asdict(result) for result in report.results],
        "summary": {**_summary(states), "skipped": skipped},
    }
