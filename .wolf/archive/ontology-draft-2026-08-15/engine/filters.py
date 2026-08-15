"""Compile typed ontology filters into read-only SQL WHERE fragments with bound params.

Filter DSL (mother spec §7):
  {"field": {"op": value}} | {"and": [...]} | {"or": [...]} | {"not": {...}}
op: eq|ne|gt|gte|lt|lte|in|between|is_null
Field names are registry api_names; compiled to physical columns. Values are
always bound (no string interpolation) — no injection.
"""

from __future__ import annotations

from typing import Any

from app.extensions.ontology.registry import ObjectTypeDecl

_OPS = {"eq": "=", "ne": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "in": "IN", "between": "BETWEEN"}


def _bind_value(bind: dict[str, Any], value: Any) -> str:
    key = f"p{len(bind)}"
    bind[key] = value
    return f":{key}"


def _column(obj: ObjectTypeDecl, api_name: str) -> str:
    if api_name == obj.pk.api_name:
        return obj.pk.column
    prop = obj.property_by_api(api_name)
    if prop is None:
        raise ValueError(f"unknown filter field: {api_name} on {obj.api_name}")
    if not prop.filterable and not prop.searchable:
        raise ValueError(f"field not filterable: {api_name} on {obj.api_name}")
    return prop.name


def _compile_node(obj: ObjectTypeDecl, node: dict, bind: dict) -> str:
    if not node or len(node) != 1:
        raise ValueError("filter node must have exactly one key (field or and/or/not)")
    key, value = next(iter(node.items()))
    if key in ("and", "or"):
        if not isinstance(value, list) or not value:
            raise ValueError(f"{key} expects a non-empty list")
        parts = [_compile_node(obj, item, bind) for item in value]
        sep = " AND " if key == "and" else " OR "
        return f"({sep.join(parts)})" if len(parts) > 1 else parts[0]
    if key == "not":
        return f"NOT ({_compile_node(obj, value, bind)})"
    # field node: value is {op: val}
    if not isinstance(value, dict) or len(value) != 1:
        raise ValueError(f"field filter {key} must be {{op: value}}")
    op, val = next(iter(value.items()))
    col = _column(obj, key)
    if op == "is_null":
        return f"{col} IS NULL" if val else f"{col} IS NOT NULL"
    if op not in _OPS:
        raise ValueError(f"unsupported op: {op}")
    if op == "in":
        if not isinstance(val, list) or not val:
            raise ValueError("in expects a non-empty list")
        keys = ", ".join(_bind_value(bind, v) for v in val)
        return f"{col} {_OPS[op]} ({keys})"
    if op == "between":
        if not isinstance(val, list) or len(val) != 2:
            raise ValueError("between expects a [lo, hi] list")
        lo, hi = val
        return f"{col} BETWEEN {_bind_value(bind, lo)} AND {_bind_value(bind, hi)}"
    return f"{col} {_OPS[op]} {_bind_value(bind, val)}"


def compile_filter(obj: ObjectTypeDecl, node: dict, bind: dict[str, Any]) -> str:
    """Return a SQL WHERE fragment (no WHERE keyword) and mutate ``bind`` with params."""
    return _compile_node(obj, node, bind)
