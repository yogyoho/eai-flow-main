"""Load read-only rule dictionaries for the compliance rule engine."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


_DICTIONARY_FILE = Path(__file__).parent / "data" / "rule_dictionaries.json"


@lru_cache(maxsize=1)
def load_rule_dictionaries() -> dict[str, list[dict[str, str]]]:
    with _DICTIONARY_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    return {
        "industries": list(data.get("industries", [])),
        "report_types": list(data.get("report_types", [])),
        "regions": list(data.get("regions", [])),
    }
