"""Load rule dictionaries — prefers database, falls back to JSON file."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DICTIONARY_FILE = Path(__file__).parent / "data" / "rule_dictionaries.json"


def load_rule_dictionaries_from_file() -> dict[str, list[dict[str, str]]]:
    """Load dictionaries from the static JSON file."""
    with _DICTIONARY_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    return {
        "industries": list(data.get("industries", [])),
        "report_types": list(data.get("report_types", [])),
        "regions": list(data.get("regions", [])),
        "rule_types": list(data.get("rule_types", [])),
        "severity_levels": list(data.get("severity_levels", [])),
    }


@lru_cache(maxsize=1)
def load_rule_dictionaries() -> dict[str, list[dict[str, str]]]:
    """Load dictionaries — reads from JSON file.

    When called from an async context (API request), the router layer
    should call ``load_rule_dictionaries_from_db`` instead and pass the
    result through. This cached function remains the fallback for
    synchronous callers and the seed-data importer.
    """
    return load_rule_dictionaries_from_file()


async def load_rule_dictionaries_from_db() -> dict[str, list[dict[str, str]]] | None:
    """Try loading dictionaries from database. Returns None if table is empty."""
    try:
        from app.extensions.database import get_db_context
        from .service import DictionaryService

        async with get_db_context() as db:
            data = await DictionaryService.load_all_as_dict(db)
            has_data = any(len(v) > 0 for v in data.values())
            return data if has_data else None
    except Exception:
        return None
