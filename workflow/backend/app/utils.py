"""Small shared helpers: IDs, datetimes, JSON, key conversion."""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime
from typing import Any

_seq_lock = threading.Lock()
_last_ms = 0
_seq = 0


def next_id() -> int:
    """Monotonic 64-bit identifier in the spirit of warm-flow's snowflake IDs.

    ``ms * 1000 + sequence`` stays well below ``2**63`` until year 292 million
    and works on SQLite, PostgreSQL and MySQL alike.
    """

    global _last_ms, _seq
    with _seq_lock:
        now_ms = int(time.time() * 1000)
        if now_ms == _last_ms:
            _seq += 1
            if _seq >= 1000:
                now_ms += 1
                _seq = 0
        else:
            _seq = 0
        _last_ms = now_ms
        return now_ms * 1000 + _seq


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_json(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def from_json(value: str | None, default: Any = None) -> Any:
    if not value:
        return {} if default is None else default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return {} if default is None else default


def to_camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


def to_snake(name: str) -> str:
    out: list[str] = []
    for char in name:
        if char.isupper():
            out.append("_")
            out.append(char.lower())
        else:
            out.append(char)
    return "".join(out)


def split_permissions(permission_flag: str | None) -> list[str]:
    """warm-flow stores handler ids joined by ``@@``.

    The designer in this port also accepts commas so hand-written fixtures are
    pleasant to use.
    """

    if not permission_flag:
        return []
    normalized = permission_flag.replace(",", "@@")
    return [item.strip() for item in normalized.split("@@") if item.strip()]


def join_permissions(items: list[str]) -> str:
    seen: list[str] = []
    for item in items:
        value = str(item).strip()
        if value and value not in seen:
            seen.append(value)
    return "@@".join(seen)
