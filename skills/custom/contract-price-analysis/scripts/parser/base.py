"""Parser interface."""

from abc import ABC, abstractmethod

from scripts.parser import ParsedItem


class BaseParser(ABC):
    @abstractmethod
    def parse(self, chunk: str) -> list[ParsedItem]:
        """Parse one chunk of text into zero or more line items."""
        ...
