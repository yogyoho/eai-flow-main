"""Mixed parser: tables first, fall back to list parsing per chunk.

Contracts vary: some embed prices in tables, others in lists. The mixed parser
tries the table parser first; if a chunk yields no table rows, it retries with
the list parser so neither format is silently dropped.
"""

from scripts.parser import ParsedItem
from scripts.parser.base import BaseParser
from scripts.parser.list_parser import ListParser
from scripts.parser.table_parser import TableParser


class MixedParser(BaseParser):
    def __init__(self):
        self._table = TableParser()
        self._list = ListParser()

    def parse(self, chunk: str) -> list[ParsedItem]:
        table_items = self._table.parse(chunk)
        if table_items:
            return table_items
        return self._list.parse(chunk)
