"""Map physical DB rows to ontology objects (api_names, nulls omitted, hidden excluded)."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.extensions.ontology.registry import ObjectTypeDecl


def jsonable(v: Any) -> Any:
    """Make a DB value JSON-serializable (Decimal→float, date/datetime→isoformat)."""
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, (dict, list)):
        return json.loads(json.dumps(v, default=str))
    return v


def to_object(obj: ObjectTypeDecl, row: Any) -> dict[str, Any]:
    """row: an object exposing ``[column_name]`` (SQLAlchemy Row / dict)."""
    mapping = dict(row) if isinstance(row, dict) else dict(row._mapping)
    props: dict[str, Any] = {}
    for p in obj.properties:
        if p.hidden:
            continue
        v = mapping.get(p.name)
        if v is None:
            continue
        props[p.api_name] = jsonable(v)
    return {"primaryKey": str(mapping.get(obj.pk.column)), "properties": props}


def select_columns(obj: ObjectTypeDecl) -> list[str]:
    """Visible physical columns to select (pk + non-hidden properties)."""
    return [obj.pk.column] + [p.name for p in obj.properties if not p.hidden]
