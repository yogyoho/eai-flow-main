"""products → 正文 AST 确定性装配(批三十四,EAI-CUSTOM 2026-11-15)。

生成器四切片(bid_letter/price_sheet/response_table/attachment_index)→
ProseMirror 同形 AST,供工作台首次打开即显示真实生成物,而不是演示文档。
纯函数零 IO 零时钟;同一 products 输入字节级稳定。

装配口径与 executor.editor 的覆盖面严格对齐:
- 报价表 row_id=清单项 id,qty/unit 走 table_cell,金额走 amount_cell(role=amount),
  合计行走 role=total_num/total_cn;
- 商务响应表 row_id=clause_id,结论走 enum_cell,响应正文走 col_role=remark;
- 投标函按换行拆段,首段 slot_id=bl-opening(金额/大写由覆盖层从同段文本回读);
- 附件索引当前 AST schema 无专用节点,以 list 表如实呈现,导出可读;
  其校验仍走任务 ctx 的 attachment_index(边界诚实,不伪造覆盖能力)。
"""

from __future__ import annotations

from decimal import Decimal


def _money(value) -> str:
    if value is None:
        return ""
    try:
        amount = Decimal(str(value))
    except Exception:  # noqa: BLE001  非法值如实留空,不猜
        return ""
    return f"{amount:,.2f}"


def _qty(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _text(value) -> list[dict]:
    text = str(value or "")
    return [{"type": "text", "text": text}] if text else []


def _para(text: str, *, slot_id: str = "") -> dict:
    attrs = {"slot_id": slot_id} if slot_id else {}
    node = {"type": "para"}
    if attrs:
        node["attrs"] = attrs
    content = _text(text)
    if content:
        node["content"] = content
    return node


def _cell(text: str, role: str) -> dict:
    node = {"type": "table_cell", "attrs": {"col_role": role}}
    content = _text(text)
    if content:
        node["content"] = content
    return node


def _amount(text: str, role: str) -> dict:
    node = {
        "type": "amount_cell",
        "attrs": {"readonly": True, "computed_expr": "", "role": role},
    }
    content = _text(text)
    if content:
        node["content"] = content
    return node


def _enum(text: str, values: list[str]) -> dict:
    node = {"type": "enum_cell", "attrs": {"enum_values": values, "current": text}}
    content = _text(text)
    if content:
        node["content"] = content
    return node


def _row(row_id: str, cells: list[dict]) -> dict:
    return {"type": "table_row", "attrs": {"row_id": row_id}, "content": cells}


def _section(title: str, section_id: str, content: list[dict]) -> dict:
    return {
        "type": "section",
        "attrs": {"level": 1, "title": title, "section_id": section_id},
        "content": content or [_para("")],
    }


def _letter_section(letter: dict) -> dict:
    text = str(letter.get("text") or "")
    lines = text.splitlines() or [""]
    paras = [_para(line, slot_id="bl-opening" if index == 0 else "") for index, line in enumerate(lines)]
    return _section("一、投标函", "S-bid-letter", paras)


def _price_section(price: dict) -> dict:
    rows = [r for r in price.get("rows") or [] if isinstance(r, dict)]
    if not rows:
        return _section("二、开标一览表", "S-price", [_para("招标文件未提供可报价的工程量清单。")])
    content = [
        _row(
            str(row.get("id") or f"price-{index}"),
            [
                _cell(str(row.get("name") or ""), "name"),
                _cell(_qty(row.get("qty")), "qty"),
                # 覆盖层口径:col_role=unit 承载单价,单位取任务 ctx 同 id 行;
                # 这样编辑金额/单价后 gate 仍能按同一事实面重算。
                _cell(_money(row.get("unit_price")), "unit"),
                _amount(_money(row.get("amount")), "amount"),
            ],
        )
        for index, row in enumerate(rows, 1)
    ]
    content.append(
        _row(
            "PRICE-TOTAL",
            [
                _cell("合计", "name"),
                _amount(_money(price.get("detail_total")), "total_num"),
                _amount(str(price.get("amount_cn") or ""), "total_cn"),
            ],
        )
    )
    return _section("二、开标一览表", "S-price", [{"type": "table", "attrs": {"table_type": "price"}, "content": content}])


def _response_section(response: dict) -> dict:
    rows = [r for r in response.get("rows") or [] if isinstance(r, dict)]
    if not rows:
        return _section("三、商务响应表", "S-response", [_para("响应矩阵暂无需要写入商务响应表的条款。")])
    content = [
        _row(
            str(row.get("clause_id") or f"rt-{index}"),
            [
                _cell(str(row.get("clause_id") or ""), "name"),
                _enum(str(row.get("conclusion") or "完全响应"), ["完全响应", "正偏离", "负偏离"]),
                _cell(str(row.get("response_text") or ""), "remark"),
            ],
        )
        for index, row in enumerate(rows, 1)
    ]
    return _section("三、商务响应表", "S-response", [{"type": "table", "attrs": {"table_type": "response"}, "content": content}])


def _attachment_section(index: dict) -> dict:
    items = [i for i in index.get("items") or [] if isinstance(i, dict)]
    body = _para(str(index.get("body_text") or ""))
    if not items:
        return _section("四、附件索引", "S-attachment", [body])
    content = [
        _row(
            f"AI-{position}",
            [
                _cell(str(item.get("no") or "—"), "name"),
                _cell(str(item.get("name") or ""), "remark"),
                _cell(_qty(item.get("page")), "qty"),
                _cell(_qty(item.get("copies")), "unit"),
                _cell(str(item.get("status") or ""), "remark"),
            ],
        )
        for position, item in enumerate(items, 1)
    ]
    return _section(
        "四、附件索引",
        "S-attachment",
        [body, {"type": "table", "attrs": {"table_type": "list"}, "content": content}],
    )


def products_to_ast(products: dict) -> dict:
    """四切片产物 → 可入 PM schema 的正文 AST(确定性)。"""
    p = products or {}
    return {
        "type": "doc",
        "content": [
            {"type": "toc_entry", "attrs": {"title": "目录", "page_placeholder": "—"}},
            _letter_section(p.get("bid_letter") or {}),
            _price_section(p.get("price_sheet") or {}),
            _response_section(p.get("response_table") or {}),
            _attachment_section(p.get("attachment_index") or {}),
        ],
    }
