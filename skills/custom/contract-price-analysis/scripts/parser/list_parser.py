"""Numbered-list parser.

For contracts whose price items appear as a numbered list rather than a table:

    1. 高压开关柜 KYN28-12，电压10kV，数量2台，单价120000元
    2. 变压器 SCB13，容量1000kVA，数量1台，单价85000元
"""

import re

from scripts.parser import ParsedItem, parse_price
from scripts.parser.base import BaseParser
from scripts.parser.table_parser import extract_tech_params, parse_qty

# Leading "1." / "1、" / "1)" then a goods name (Chinese/non-digit run).
_LINE = re.compile(
    r"^\s*\d+\s*[\.、)]\s*(?P<name>[^,，0-9\s]+(?:\s*[^,，0-9]+)*?)\s*"
    r"(?P<rest>.*)$"
)
_PRICE = re.compile(r"(?:单价|价格|金额)\s*[:：]?\s*(\d+(?:[\.,]\d+)*)\s*元?")
_QTY = re.compile(r"数量\s*[:：]?\s*(\d+(?:\.\d+)?)\s*([台套件个吨米块根立方])?")
_SPEC = re.compile(r"\b([A-Za-z][A-Za-z0-9\-/]{1,20})\b")


class ListParser(BaseParser):
    def parse(self, chunk: str) -> list[ParsedItem]:
        items: list[ParsedItem] = []
        for line in chunk.splitlines():
            m = _LINE.match(line)
            if not m:
                continue
            name = m.group("name").strip()
            rest = m.group("rest") or ""
            pm = _PRICE.search(rest)
            if not name or not pm:
                continue
            qm = _QTY.search(rest)
            sm = _SPEC.search(rest)
            items.append(
                ParsedItem(
                    goods_name=name,
                    spec_model=sm.group(1) if sm else None,
                    tech_params=extract_tech_params(rest),
                    quantity=float(qm.group(1)) if qm else None,
                    unit=qm.group(2) if qm else None,
                    unit_price=float(pm.group(1).replace(",", "")),
                )
            )
        return items
