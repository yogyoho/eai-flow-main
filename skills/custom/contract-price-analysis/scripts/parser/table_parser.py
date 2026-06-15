"""Markdown-table parser.

Contracts commonly embed price lists as Markdown tables (the form RAGFlow returns
after layout parsing). This parser reads the header row, maps known column
headers to roles (name/spec/tech/qty/unit/price), then reads each data row.
"""

import re

from scripts.parser import ParsedItem, parse_price
from scripts.parser.base import BaseParser

# Recognised Chinese header tokens → role.
_HEADER_MAP = {
    "货物名称": "name",
    "设备名称": "name",
    "名称": "name",
    "物资名称": "name",
    "规格型号": "spec",
    "规格": "spec",
    "型号": "spec",
    "技术参数": "tech",
    "参数": "tech",
    "数量": "qty",
    "单位": "unit",
    "单价": "price",
    "单价(元)": "price",
    "单价（元）": "price",
    "价格": "price",
    "金额": "price",
}

# Pull key=value-ish tech params from free text, e.g. "电压10kV", "容量1000kVA".
_TECH_KV = re.compile(
    r"(电压|电流|容量|功率|频率|压力|温度|流量|转速|扬程)\s*[:：]?\s*"
    r"(\d+(?:\.\d+)?)\s*([a-zA-Zµμ²³kVAkvAKWakw/]+)?"
)


class TableParser(BaseParser):
    def parse(self, chunk: str) -> list[ParsedItem]:
        lines = [ln for ln in chunk.splitlines() if ln.lstrip().startswith("|")]
        if len(lines) < 2:
            return []

        header = [c.strip() for c in self._split_row(lines[0])]
        col: dict[str, int] = {}
        for idx, h in enumerate(header):
            for token, role in _HEADER_MAP.items():
                if token in h and role not in col:
                    col[role] = idx

        items: list[ParsedItem] = []
        for line in lines[1:]:
            if "---" in line or "===" in line:
                continue
            cells = [c.strip() for c in self._split_row(line)]
            get = self._cell_getter(cells, col)
            name = get("name")
            price = parse_price(get("price") or "")
            if not name or price is None:
                continue
            if name in ("序号", "合计", "小计", "总计", "名称"):
                continue
            tech_text = get("tech") or get("spec") or ""
            items.append(
                ParsedItem(
                    goods_name=name,
                    spec_model=get("spec") or None,
                    tech_params=extract_tech_params(tech_text),
                    quantity=parse_qty(get("qty")),
                    unit=get("unit") or None,
                    unit_price=price,
                )
            )
        return items

    @staticmethod
    def _split_row(line: str) -> list[str]:
        return line.strip().strip("|").split("|")

    @staticmethod
    def _cell_getter(cells: list[str], col: dict[str, int]):
        def get(role: str) -> str:
            idx = col.get(role)
            if idx is None or idx >= len(cells):
                return ""
            return cells[idx]

        return get


def parse_qty(text: str) -> float | None:
    if not text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else None


def extract_tech_params(text: str) -> dict:
    return {k: f"{v}{u or ''}" for k, v, u in _TECH_KV.findall(text or "")}
