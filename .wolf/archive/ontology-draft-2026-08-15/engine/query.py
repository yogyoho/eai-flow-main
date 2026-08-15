"""Ontology query engine — get/list/search/aggregate/link traversal over the registry.

Pure helpers (cursor, FK where, cross-module expression rewrite) are module-level
and unit-tested; DB-touching methods delegate to the connector selected by each
object type's access.path (postgres_ext direct / data_source guarded).
"""

from __future__ import annotations

import base64
import re
from typing import Any

from app.extensions.ontology.engine import filters as F
from app.extensions.ontology.engine import mapper as M
from app.extensions.ontology.registry import LinkTypeDecl, ObjectTypeDecl, Registry

_AGG_FNS = {"count", "sum", "avg", "min", "max", "percentile_cont"}


def cursor_encode(pk: Any) -> str:
    return base64.urlsafe_b64encode(str(pk).encode()).decode()


def cursor_decode(cursor: str) -> str:
    return base64.urlsafe_b64decode(cursor.encode()).decode()


def _coerce_pk(obj: ObjectTypeDecl, value: Any) -> Any:
    if obj.pk.type == "integer" and isinstance(value, str):
        return int(value)
    return value


def resolve_fk_where(link: LinkTypeDecl, source_table: str, source_pk_col: str, target_pk_col: str, forward: bool) -> str:
    """WHERE fragment for querying the OTHER side of a foreign_key link.

    forward=True  (current object is link.source): the FK lives on the current
      side, so target rows whose pk is IN the FK values of current-side rows
      (subquery — works without loading the FK into memory).
    forward=False (current object is link.target): source rows whose FK column
      equals the current pk (direct equality).
    """
    sc = link.join.source_column
    if forward:
        return f'"{target_pk_col}" IN (SELECT "{sc}" FROM {source_table} WHERE "{source_pk_col}" = :p0)'
    return f'"{sc}" = :p0'


def rewrite_match_expression(expr: str, table: str, obj: ObjectTypeDecl, cur: dict) -> tuple[str, dict[str, Any]]:
    """Rewrite a normalized_key_match expression for a single-table target query.

    Every ``table.column`` reference belonging to the CURRENT object is replaced
    with a bound parameter carrying the current row's value, leaving only
    target-side columns and params — so the fragment can run as a WHERE on the
    target table even when the two tables live in different databases
    (e.g. bid@data_source ↔ contract_document@postgres_ext).

    ``cur`` is a to_object() dict (hidden properties are absent — expressions
    must only reference visible columns).
    """
    pairs = [(obj.pk.column, cur["primaryKey"])] + [(p.name, cur["properties"].get(p.api_name)) for p in obj.properties]
    pairs.sort(key=lambda t: len(t[0]), reverse=True)  # longest column first — no prefix shadowing
    bind: dict[str, Any] = {}
    out = expr
    for col, val in pairs:
        pattern = re.compile(rf"\b{re.escape(table)}\.{re.escape(col)}\b")
        if pattern.search(out):
            key = f"p{len(bind)}"
            bind[key] = val
            out = pattern.sub(f":{key}", out)
    return out, bind


class QueryEngine:
    def __init__(self, registry: Registry, pg_connector=None, ds_connector=None):
        self.registry = registry
        self.pg = pg_connector
        self.ds = ds_connector

    def _obj(self, api_name: str) -> ObjectTypeDecl:
        obj = self.registry.object_by_name(api_name)
        if obj is None or not obj.enabled:
            raise ValueError(f"unknown or disabled object type: {api_name}")
        return obj

    async def _execute(self, obj: ObjectTypeDecl, columns: list[str], where: str, bind: dict, order_by: str | None, limit: int) -> list[dict]:
        """Dispatch to the connector chosen by access.path (signatures differ)."""
        if obj.access.path == "postgres_ext":
            return await self.pg.execute_select(obj.access.table, columns, where, bind, order_by, limit)
        return await self.ds.execute_select(obj.access.source_id, obj.access.table_name, columns, where, bind, order_by, limit)

    async def get(self, api_name: str, pk: Any, include_properties: list[str] | None = None) -> dict[str, Any] | None:
        obj = self._obj(api_name)
        rows = await self._execute(obj, M.select_columns(obj), f'"{obj.pk.column}" = :p0', {"p0": _coerce_pk(obj, pk)}, None, 1)
        return M.to_object(obj, rows[0]) if rows else None

    async def list(
        self,
        api_name: str,
        filters: dict | None = None,
        order_by: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
        include_properties: list[str] | None = None,
    ) -> dict:
        obj = self._obj(api_name)
        bind: dict[str, Any] = {}
        where = ""
        if filters:
            where = F.compile_filter(obj, filters, bind)
        if cursor:
            pk_val = cursor_decode(cursor)
            key = f"p{len(bind)}"
            bind[key] = _coerce_pk(obj, pk_val)
            cond = f'"{obj.pk.column}" > :{key}'
            where = f"({where}) AND {cond}" if where else cond
        rows = await self._execute(obj, M.select_columns(obj), where, bind, order_by or obj.pk.column, min(limit + 1, 200))
        has_more = len(rows) > limit
        objs = [M.to_object(obj, r) for r in rows[:limit]]
        return {
            "objects": objs,
            "nextPageToken": cursor_encode(objs[-1]["primaryKey"]) if (objs and has_more) else None,
            "hasMore": has_more,
        }

    async def search(self, api_name: str, term: str, limit: int = 20) -> dict:
        obj = self._obj(api_name)
        searchable = [p for p in obj.properties if p.searchable and not p.hidden]
        if not searchable:
            return {"objects": [], "message": f"{api_name} 无 searchable 字段"}
        bind: dict[str, Any] = {}
        clauses = []
        for i, p in enumerate(searchable):
            clauses.append(f"{p.name} ILIKE :p{i}")
            bind[f"p{i}"] = f"%{term}%"
        rows = await self._execute(obj, M.select_columns(obj), " OR ".join(clauses), bind, obj.pk.column, limit)
        return {"objects": [M.to_object(obj, r) for r in rows]}

    async def get_links(self, api_name: str, pk: Any, link_type: str, limit: int = 50, cursor: str | None = None) -> dict:
        obj = self._obj(api_name)
        link = self.registry.link_by_name(link_type)
        if link is None or not link.enabled:
            raise ValueError(f"unknown or disabled link type: {link_type}")
        if obj.api_name == link.source:
            forward, other = True, link.target
        elif obj.api_name == link.target:
            forward, other = False, link.source
        else:
            raise ValueError(f"link {link_type} does not involve {api_name}")
        tgt = self.registry.object_by_name(other)
        cur_table = obj.access.table or obj.access.table_name
        if link.join.type == "foreign_key":
            where = resolve_fk_where(link, cur_table, obj.pk.column, tgt.pk.column, forward)
            bind = {"p0": _coerce_pk(obj, pk)}
        else:
            cur = await self.get(api_name, pk)
            if cur is None:
                return {"objects": [], "nextPageToken": None, "hasMore": False}
            where, bind = rewrite_match_expression(link.join.expression or "true", cur_table, obj, cur)
        rows = await self._execute(tgt, M.select_columns(tgt), where, bind, tgt.pk.column, min(limit + 1, 200))
        has_more = len(rows) > limit
        objs = [M.to_object(tgt, r) for r in rows[:limit]]
        return {"objects": objs, "nextPageToken": cursor_encode(objs[-1]["primaryKey"]) if (objs and has_more) else None, "hasMore": has_more}

    async def aggregate(self, api_name: str, group_by: str | None = None, metric: dict | None = None, filters: dict | None = None) -> list[dict]:
        """Set-level aggregation (group_by + count/sum/avg/min/max/percentile_cont) — one query, no N+1."""
        obj = self._obj(api_name)
        bind: dict[str, Any] = {}
        where = F.compile_filter(obj, filters, bind) if filters else ""
        metric = metric or {}
        fn = str(metric.get("fn", "count"))
        if fn not in _AGG_FNS:
            raise ValueError(f"unsupported aggregate fn: {fn}")
        fcol = None
        if metric.get("field"):
            fprop = obj.property_by_api(metric["field"])
            if fprop is None:
                raise ValueError(f"unknown metric field: {metric['field']}")
            fcol = fprop.name
        if fn != "count" and fcol is None:
            raise ValueError(f"aggregate fn {fn} requires a metric field")
        if fn == "count":
            agg = "COUNT(*)"
        elif fn == "percentile_cont":
            agg = f"percentile_cont({float(metric.get('p', 0.5))}) WITHIN GROUP (ORDER BY {fcol})"
        else:
            agg = f"{fn.upper()}({fcol})"
        gcol = None
        if group_by:
            gprop = obj.property_by_api(group_by)
            if gprop is None:
                raise ValueError(f"unknown group_by: {group_by}")
            gcol = gprop.name
        table = obj.access.table or obj.access.table_name
        select_list = f"{agg} AS value" if gcol is None else f'"{gcol}" AS group_value, {agg} AS value'
        sql = f"SELECT {select_list} FROM {table}"
        if where:
            sql += f" WHERE {where}"
        if gcol:
            sql += f' GROUP BY "{gcol}"'
        sql += " ORDER BY 1 LIMIT 200"
        if obj.access.path == "postgres_ext":
            rows = await self.pg.run_raw_select(sql, bind)
        else:
            rows = await self.ds.run_raw_select(obj.access.source_id, sql, bind)
        return [{"group_value": M.jsonable(r.get("group_value")), "value": M.jsonable(r.get("value"))} for r in rows]

    async def traverse_path(self, api_name: str, pk: Any, path: str, limit: int = 50) -> dict:
        """Multi-hop walk along a dot-separated link path (single-hop get_links composed)."""
        hops = [h for h in path.split(".") if h]
        node = await self.get(api_name, pk)
        if node is None:
            return {"error": f"object not found: {api_name}/{pk}"}
        result: dict[str, Any] = dict(node)
        cur_api, cur_pk = api_name, node["primaryKey"]
        for hop in hops:
            link = self.registry.link_by_name(hop)
            if link is None or not link.enabled:
                raise ValueError(f"unknown or disabled link in path: {hop}")
            data = await self.get_links(cur_api, cur_pk, hop, limit)
            if not data["objects"]:
                result[f"via_{hop}"] = []
                break
            nxt = data["objects"][0]
            cur_api = link.target if link.source == cur_api else link.source
            cur_pk = nxt["primaryKey"]
            result[f"via_{hop}"] = nxt
        return result
