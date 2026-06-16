"""Document parsers for contract price line-items.

A ``ParsedItem`` is one extracted row from a contract (e.g. one goods line with
its price). ``parse_chunks`` dispatches to the right parser based on the user
selected ``mode`` (``table`` / ``list`` / ``mixed``).

NOTE: ``ParsedItem`` and ``parse_price`` are defined here at the top of the
module so the submodules can import them without triggering a circular import.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedItem:
    goods_name: str
    spec_model: Optional[str] = None
    tech_params: dict = field(default_factory=dict)
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    source_doc_id: Optional[str] = None  # RAGFlow doc id; set by the pipeline per-doc


def parse_price(text: str) -> Optional[float]:
    """Extract the first numeric price from a string like '120000' or '120,000元'."""
    if not text:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)", text)
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


# Submodule imports come AFTER the symbols they depend on are defined.
from scripts.parser.list_parser import ListParser  # noqa: E402
from scripts.parser.mixed_parser import MixedParser  # noqa: E402
from scripts.parser.table_parser import TableParser  # noqa: E402

_PARSERS = {"table": TableParser, "list": ListParser, "mixed": MixedParser}


def parse_chunks(chunks: list[str], mode: str = "table") -> list[ParsedItem]:
    """Parse a list of chunk strings in the given mode, returning line items."""
    parser_cls = _PARSERS.get(mode, TableParser)
    parser = parser_cls()
    items: list[ParsedItem] = []
    for chunk in chunks:
        items.extend(parser.parse(chunk))
    return items
