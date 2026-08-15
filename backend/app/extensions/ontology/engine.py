"""Ontology 查询引擎（declared-only / 绑定参数 / keyset 分页 / 引擎级归一化）.

契约（plan D6/D11/D13）：
- ① filter/search 值一律绑定参数（:named），列与操作符 declared-only 显式拒绝未声明项
- ② keyset 分页 + pk tiebreaker（排序值相同行集不丢行）
- ③ traverse ≤ MAX_HOPS 跳；跨 connector 跳 = 分块应用侧 join（≤ CHUNK=200/批，超出报错不静默丢）
- hidden 列：SELECT 投影仅含非 hidden 属性（引擎层零透出）
- 归一化标准：LOWER(BTRIM(col)) + 两侧非空守卫（引擎强制，非 per-link 表达式）
- stub 链接（enabled:false）：describe 可见，遍历显式拒绝

执行器注入：引擎不直接连库——ConnectorResolver（T4 connectors.py）解析 AccessConfig 并执行。
"""

from __future__ import annotations

import base64
import json
from typing import Any, Protocol

from app.extensions.ontology.schemas import AccessConfig, JoinConfig, ObjectType, PropertySchema

MAX_LIMIT = 200
DEFAULT_LIMIT = 50
MAX_HOPS = 5
CHUNK = 200  # D11: 跨 connector 键集分批上限

FILTER_OPS = {"eq": "=", "ne": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
AGG_FNS = {"count", "sum", "avg", "min", "max"}


class OntologyError(Exception):
    """引擎层显式错误（用户可见，不静默）。"""


class UnknownObjectError(OntologyError):
    pass


class UnknownLinkError(OntologyError):
    pass


class LinkDisabledError(OntologyError):
    """stub 链接（enabled:false）——describe 可见并标注，遍历拒绝。"""


class UnknownColumnError(OntologyError):
    pass


class ColumnNotFilterableError(OntologyError):
    pass


class InvalidFilterError(OntologyError):
    pass


class TraverseTooDeepError(OntologyError):
    pass


class ConnectorResolver(Protocol):
    """执行器协议（T4 connectors.py 实现）。same() 判定两侧是否可单 SQL join。"""

    async def fetch(self, access: AccessConfig, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...

    def same(self, a: AccessConfig, b: AccessConfig) -> bool: ...


def _norm(col: str) -> str:
    """引擎级归一化标准（D6/R4）：LOWER(BTRIM(col))。"""
    return f"LOWER(BTRIM({col}))"


def _empty_guard(col: str) -> str:
    return f"{_norm(col)} IS NOT NULL AND {_norm(col)} <> ''"


class Engine:
    def __init__(self, registry_fn, resolver: ConnectorResolver) -> None:
        """registry_fn: () -> Registry（逐调用取最新快照，D4 指纹一致性）。"""
        self._registry_fn = registry_fn
        self._resolver = resolver

    # ---------- 对象查询 ----------

    async def list_objects(
        self,
        object_type: str,
        filters: list[dict[str, Any]] | None = None,
        q: str | None = None,
        limit: int = DEFAULT_LIMIT,
        cursor: str | None = None,
        order: str | None = None,
        desc: bool = False,
    ) -> dict[str, Any]:
        obj = self._object(object_type)
        limit = max(1, min(limit, MAX_LIMIT))
        props = obj.visible_properties()
        select_cols = ", ".join(f'"{p.name}"' for p in props)
        params: dict[str, Any] = {}
        where = self._build_filters(obj, filters, params)
        if q:
            searchable = [p for p in props if p.searchable]
            if not searchable:
                raise InvalidFilterError(f"{object_type} 无 searchable 属性, 不支持全文搜索")
            like = f"%{q}%"
            terms = []
            for i, p in enumerate(searchable):
                params[f"q{i}"] = like
                terms.append(f'"{p.name}" ILIKE :q{i}')
            where.append("(" + " OR ".join(terms) + ")")

        # 排序: 声明列或 pk；pk 恒为 tiebreaker
        order_col = obj.pk.column
        if order:
            order_col = self._declared_column(obj, order).name
        direction = "DESC" if desc else "ASC"
        if cursor:
            cv, cpk = self._decode_cursor(cursor)
            params["_cv"], params["_cpk"] = cv, cpk
            op = "<" if desc else ">"
            where.append(f'("{order_col}", "{obj.pk.column}") {op} (:_cv, :_cpk)')

        w = ("WHERE " + " AND ".join(where)) if where else ""
        sql = f'SELECT {select_cols} FROM "{self._table(obj)}" {w} ORDER BY "{order_col}" {direction}, "{obj.pk.column}" {direction} LIMIT {limit + 1}'
        rows = await self._resolver.fetch(obj.access, sql, params)
        has_more = len(rows) > limit
        rows = rows[:limit]
        out = [self._serialize(obj, r) for r in rows]
        next_cursor = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = self._encode_cursor(last.get(order_col), last[obj.pk.column])
        return {"data": out, "next_cursor": next_cursor, "object_type": object_type}

    async def get_object(self, object_type: str, pk: Any) -> dict[str, Any] | None:
        obj = self._object(object_type)
        props = obj.visible_properties()
        select_cols = ", ".join(f'"{p.name}"' for p in props)
        sql = f'SELECT {select_cols} FROM "{self._table(obj)}" WHERE "{obj.pk.column}" = :pk LIMIT 1'
        rows = await self._resolver.fetch(obj.access, sql, {"pk": self._coerce_pk(obj, pk)})
        return self._serialize(obj, rows[0]) if rows else None

    async def aggregate(
        self,
        object_type: str,
        group_by: str,
        metric: str = "count",
        metric_column: str | None = None,
        filters: list[dict[str, Any]] | None = None,
        limit: int = MAX_LIMIT,
    ) -> dict[str, Any]:
        obj = self._object(object_type)
        if metric not in AGG_FNS:
            raise InvalidFilterError(f"聚合函数必须是 {sorted(AGG_FNS)}, 得到 '{metric}'")
        gcol = self._declared_column(obj, group_by)
        if gcol.hidden:
            raise UnknownColumnError(f"列 '{group_by}' 不可见")
        params: dict[str, Any] = {}
        where = self._build_filters(obj, filters, params)
        if metric == "count":
            agg = "COUNT(*)"
        else:
            if not metric_column:
                raise InvalidFilterError(f"{metric} 需要 metric_column")
            mcol = self._declared_column(obj, metric_column)
            if mcol.type not in ("integer", "number"):
                raise InvalidFilterError(f"聚合列 '{metric_column}' 类型 {mcol.type} 非数值")
            agg = f'{metric.upper()}("{mcol.name}")'
        w = ("WHERE " + " AND ".join(where)) if where else ""
        sql = f'SELECT "{gcol.name}" AS "group", {agg} AS "value" FROM "{self._table(obj)}" {w} GROUP BY "{gcol.name}" ORDER BY 2 DESC LIMIT {max(1, min(limit, MAX_LIMIT))}'
        rows = await self._resolver.fetch(obj.access, sql, params)
        return {"data": [dict(r) for r in rows], "object_type": object_type, "group_by": group_by, "metric": metric}

    # ---------- 链接遍历 ----------

    async def get_links(self, object_type: str, pk: Any, link_type: str, limit: int = MAX_LIMIT) -> dict[str, Any]:
        """从实例沿链接取对侧行。link 以 source→target 声明; object_type 在哪侧决定方向。"""
        lt = self._link(link_type)
        if not lt.enabled:
            raise LinkDisabledError(f"链接 '{link_type}' 为 stub（enabled:false）——{lt.note or '召回未达标'}")
        if object_type == lt.source:
            rows = await self._follow(lt, forward=True, pks=[pk], limit=limit)
        elif object_type == lt.target:
            rows = await self._follow(lt, forward=False, pks=[pk], limit=limit)
        else:
            raise UnknownLinkError(f"链接 '{link_type}' 不连接对象类型 '{object_type}'")
        return {"data": rows, "link_type": link_type, "from": {"object_type": object_type, "pk": pk}}

    async def traverse(self, object_type: str, pk: Any, steps: list[str], limit: int = MAX_LIMIT) -> dict[str, Any]:
        """多跳遍历（≤ MAX_HOPS）。每跳 fan-out 上限 CHUNK，超出显式报错。"""
        if not steps:
            raise InvalidFilterError("traverse 需要至少一步链接")
        if len(steps) > MAX_HOPS:
            raise TraverseTooDeepError(f"遍历深度 {len(steps)} 超上限 {MAX_HOPS}")
        reg = self._registry_fn()
        current_type = object_type
        current_pks: list[Any] = [pk]
        path: list[dict[str, Any]] = []
        for step in steps:
            lt = reg.link_types.get(step)
            if lt is None:
                raise UnknownLinkError(f"链接类型 '{step}' 未注册")
            if not lt.enabled:
                raise LinkDisabledError(f"链接 '{step}' 为 stub（enabled:false）——{lt.note or '召回未达标'}")
            forward = current_type == lt.source
            if not forward and current_type != lt.target:
                raise UnknownLinkError(f"链接 '{step}' 不连接当前对象类型 '{current_type}'")
            rows = await self._follow(lt, forward=forward, pks=current_pks, limit=MAX_LIMIT)
            current_type = lt.target if forward else lt.source
            current_pks = [r[reg.object_types[current_type].pk.api_name] for r in rows]
            if len(current_pks) > CHUNK:
                raise OntologyError(f"跳 '{step}' fan-out {len(current_pks)} 超上限 {CHUNK}——请缩小起点集合")
            path.append({"link_type": step, "object_type": current_type, "count": len(rows)})
            if not current_pks:
                break
        # 终点对象完整行
        final = []
        if current_pks:
            target_obj = reg.object_types[current_type]
            pk_col = target_obj.pk.column
            for i in range(0, len(current_pks), CHUNK):
                batch = current_pks[i : i + CHUNK]
                ph = ", ".join(f":pk{i}" for i in range(len(batch)))
                params = {f"pk{i}": v for i, v in enumerate(batch)}
                props = target_obj.visible_properties()
                select_cols = ", ".join(f'"{p.name}"' for p in props)
                rows = await self._resolver.fetch(target_obj.access, f'SELECT {select_cols} FROM "{self._table(target_obj)}" WHERE "{pk_col}" IN ({ph})', params)
                final.extend(self._serialize(target_obj, r) for r in rows)
        return {"data": final[:limit], "path": path, "end_object_type": current_type}

    # ---------- 内部: 链接执行 ----------

    async def _follow(self, lt, forward: bool, pks: list[Any], limit: int) -> list[dict[str, Any]]:
        reg = self._registry_fn()
        src_obj = reg.object_types[lt.source]
        tgt_obj = reg.object_types[lt.target]
        j = lt.join
        # 方向语义: forward = 从 source 实例找 target 行; reverse = 从 target 实例找 source 行
        near_obj, far_obj = (src_obj, tgt_obj) if forward else (tgt_obj, src_obj)
        near_pks = [self._coerce_pk(src_obj if forward else tgt_obj, p) for p in pks]

        if self._resolver.same(src_obj.access, tgt_obj.access):
            return await self._follow_same_connector(j, src_obj, tgt_obj, near_pks, forward, limit, lt)

        # 跨 connector（D11）: 取近侧键集 → 分块对侧 IN 查询（基数可断言）
        key_rows = await self._near_keys(j, near_obj, forward, near_pks, lt)
        keys: list[tuple[Any, ...]] = [tuple(r.values()) for r in key_rows]
        return await self._far_rows(j, far_obj, forward, keys, limit)

    async def _follow_same_connector(self, j: JoinConfig, src_obj: ObjectType, tgt_obj: ObjectType, near_pks: list[Any], forward: bool, limit: int, lt) -> list[dict[str, Any]]:
        """同 connector: 单 SQL。"""
        near_obj, far_obj = (src_obj, tgt_obj) if forward else (tgt_obj, src_obj)
        far_props = far_obj.visible_properties()
        select_cols = ", ".join(f't."{p.name}"' for p in far_props)
        params: dict[str, Any] = {}
        ph = ", ".join(f":n{i}" for i in range(len(near_pks)))
        params.update({f"n{i}": v for i, v in enumerate(near_pks)})

        if j.type == "foreign_key":
            s_col, t_col = j.source_column, j.target_column
            # forward: far=target(t), near=source(s) → t.target_col = s.source_fk
            # reverse: far=source(t), near=target(s) → t.source_fk = s.target_col(=near pk)
            cond = f't."{t_col}" = s."{s_col}"' if forward else f't."{s_col}" = s."{t_col}"'
            sf = ""
            if j.source_filter:
                sf = " AND " + " AND ".join(f's."{k}" = :sf_{k}' for k in j.source_filter)
                params.update({f"sf_{k}": v for k, v in j.source_filter.items()})
            sql = f'SELECT {select_cols} FROM "{self._table(far_obj)}" t JOIN "{self._table(near_obj)}" s ON {cond} WHERE s."{near_obj.pk.column}" IN ({ph}){sf} LIMIT {limit}'
        else:
            # normalized_key_match: any-of key_pairs, 引擎级归一化 + 两侧非空守卫
            conds = []
            for idx, (s_col, t_col) in enumerate(j.key_pairs or []):
                conds.append(f"{_norm(f's."{s_col}"')} = {_norm(f't."{t_col}"')}")
            cond = " OR ".join(conds)
            guard = " AND ".join([_empty_guard(f's."{sc}"') for sc, _ in (j.key_pairs or [])])
            tguard = " AND ".join([_empty_guard(f't."{tc}"') for _, tc in (j.key_pairs or [])])
            sf = ""
            if j.source_filter:
                sf = " AND " + " AND ".join(f's."{k}" = :sf_{k}' for k in j.source_filter)
                params.update({f"sf_{k}": v for k, v in j.source_filter.items()})
            # forward: near=source; reverse: near=target（s/t 别名按声明方向固定, IN 侧换）
            near_alias_col = f's."{src_obj.pk.column}"' if forward else f't."{tgt_obj.pk.column}"'
            sql = f'SELECT {select_cols} FROM "{self._table(tgt_obj)}" t JOIN "{self._table(src_obj)}" s ON ({cond}) WHERE {near_alias_col} IN ({ph}) AND {guard} AND {tguard}{sf} LIMIT {limit}'
        rows = await self._resolver.fetch(far_obj.access, sql, params)
        return [self._serialize(far_obj, r) for r in rows]

    async def _near_keys(self, j: JoinConfig, near_obj: ObjectType, forward: bool, near_pks: list[Any], lt) -> list[dict[str, Any]]:
        """跨 connector 第一步: 近侧实例的 join 键值（归一化后, 带守卫与 source_filter）。"""
        if j.type == "foreign_key":
            cols = [j.source_column] if forward else [j.target_column]
            col_sql = ", ".join(f'"{c}"' for c in cols)
            guards = " AND ".join(f'"{c}" IS NOT NULL' for c in cols)
        else:
            pairs = j.key_pairs or []
            cols = [sc for sc, _ in pairs] if forward else [tc for _, tc in pairs]
            col_sql = ", ".join(_norm(f'"{c}"') for c in cols)
            guards = " AND ".join(f"({_norm(f'"{c}"')} IS NOT NULL AND {_norm(f'"{c}"')} <> '')" for c in cols)
        params: dict[str, Any] = {}
        ph = ", ".join(f":n{i}" for i in range(len(near_pks)))
        params.update({f"n{i}": v for i, v in enumerate(near_pks)})
        extra = ""
        if j.source_filter and forward:
            extra = " AND " + " AND ".join(f'"{k}" = :sf_{k}' for k in j.source_filter)
            params.update({f"sf_{k}": v for k, v in j.source_filter.items()})
        sql = f'SELECT {col_sql} FROM "{self._table(near_obj)}" WHERE "{near_obj.pk.column}" IN ({ph}) AND {guards}{extra} LIMIT {min(len(near_pks), CHUNK)}'
        return await self._resolver.fetch(near_obj.access, sql, params)

    async def _far_rows(self, j: JoinConfig, far_obj: ObjectType, forward: bool, keys: list[tuple[Any, ...]], limit: int) -> list[dict[str, Any]]:
        """跨 connector 第二步: 键集分块（≤CHUNK）对侧 IN 查询。"""
        if j.type == "foreign_key":
            far_col = j.target_column if forward else j.source_column

            def norm(c: str) -> str:
                return f'"{c}"'

        else:
            pairs = j.key_pairs or []
            far_col = (tc if forward else sc for sc, tc in pairs)

            def norm(c: str) -> str:
                return _norm(f'"{c}"')

        far_props = far_obj.visible_properties()
        select_cols = ", ".join(f'"{p.name}"' for p in far_props)
        out: list[dict[str, Any]] = []
        for i in range(0, len(keys), CHUNK):
            batch = keys[i : i + CHUNK]
            if len(batch) > CHUNK:
                raise OntologyError(f"键集分块超上限 {CHUNK}")
            if j.type == "foreign_key":
                vals = [k[0] for k in batch if k[0] is not None]
                ph = ", ".join(f":k{i}" for i in range(len(vals)))
                params = {f"k{i}": v for i, v in enumerate(vals)}
                cond = f"{norm(far_col)} IN ({ph})" if ph else "FALSE"
            else:
                # any-of: 任一 key 列命中任一批值
                conds = []
                params: dict[str, Any] = {}
                n = 0
                for col_idx, col in enumerate(far_col):
                    vals = [k[col_idx] for k in batch if len(k) > col_idx and k[col_idx] not in (None, "")]
                    if not vals:
                        continue
                    ph = ", ".join(f":k{n + x}" for x in range(len(vals)))
                    params.update({f"k{n + x}": v for x, v in enumerate(vals)})
                    n += len(vals)
                    conds.append(f"{norm(col)} IN ({ph}) AND {_empty_guard(f'"{col}"')}")
                cond = "(" + " OR ".join(conds) + ")" if conds else "FALSE"
            rows = await self._resolver.fetch(far_obj.access, f'SELECT {select_cols} FROM "{self._table(far_obj)}" WHERE {cond} LIMIT {min(limit, MAX_LIMIT)}', params)
            out.extend(self._serialize(far_obj, r) for r in rows)
            if len(out) >= limit:
                break
        return out[:limit]

    # ---------- 内部: 过滤/序列化 ----------

    def _build_filters(self, obj: ObjectType, filters: list[dict[str, Any]] | None, params: dict[str, Any]) -> list[str]:
        where: list[str] = []
        for i, f in enumerate(filters or []):
            if not isinstance(f, dict) or set(f) - {"column", "op", "value"}:
                raise InvalidFilterError(f"过滤器必须是 {{column, op, value}}, 得到 {f!r}")
            col = f.get("column")
            op = f.get("op", "eq")
            val = f.get("value")
            if op not in FILTER_OPS:
                raise InvalidFilterError(f"操作符 '{op}' 未声明（允许: {sorted(FILTER_OPS)}）")
            p = self._declared_column(obj, col)
            if not p.filterable:
                raise ColumnNotFilterableError(f"列 '{col}' 未声明 filterable")
            name = f"f{i}"
            params[name] = val
            where.append(f'"{p.name}" {FILTER_OPS[op]} :{name}')
        return where

    def _serialize(self, obj: ObjectType, row: dict[str, Any]) -> dict[str, Any]:
        """物理列名 → api_name（camelCase）；hidden 列不在 SELECT 投影中，双保险再剔一次。"""
        visible = {p.name: p.api_name for p in obj.visible_properties()}
        return {visible[k]: v for k, v in row.items() if k in visible}

    @staticmethod
    def _encode_cursor(v: Any, pk: Any) -> str:
        raw = json.dumps([v, pk], default=str).encode()
        return base64.urlsafe_b64encode(raw).decode()

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[Any, Any]:
        try:
            v, pk = json.loads(base64.urlsafe_b64decode(cursor))
            return v, pk
        except Exception as e:
            raise InvalidFilterError(f"游标损坏: {cursor[:32]}…") from e

    def _object(self, object_type: str) -> ObjectType:
        obj = self._registry_fn().object_types.get(object_type)
        if obj is None:
            raise UnknownObjectError(f"对象类型 '{object_type}' 未注册")
        if not obj.enabled:
            raise UnknownObjectError(f"对象类型 '{object_type}' 已停用")
        return obj

    def _link(self, link_type: str):
        lt = self._registry_fn().link_types.get(link_type)
        if lt is None:
            raise UnknownLinkError(f"链接类型 '{link_type}' 未注册")
        return lt

    def _declared_column(self, obj: ObjectType, name: str) -> PropertySchema:
        for p in obj.properties:
            if p.name == name or p.api_name == name:
                return p
        raise UnknownColumnError(f"列 '{name}' 未在 {obj.api_name} 属性中声明（declared-only）")

    @staticmethod
    def _table(obj: ObjectType) -> str:
        # 物理表名来自受信注册表 YAML（lint 层校验存在性）; 引号防保留字
        return obj.access.table or obj.access.table_name or ""

    def _coerce_pk(self, obj: ObjectType, pk: Any) -> Any:
        if obj.pk.type == "uuid":
            import uuid as _uuid

            if isinstance(pk, str):
                return _uuid.UUID(pk)
        if obj.pk.type == "integer":
            return int(pk)
        return str(pk)
