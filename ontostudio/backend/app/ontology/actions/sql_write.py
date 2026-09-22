"""动作写路径的 SQL 构造与守卫——**本模块是全库唯一拼接写语句的地方**。

EAI-CUSTOM: 设计 §2。安全约定：
- 表名与列名只来自解析后的 ActionSpec（registry 声明），**绝不来自调用方 params**；
- 列名一律过标识符白名单并加引号；
- 值一律命名参数绑定。
读路径的 sqlguard.assert_readonly_select 只放 SELECT，不能复用，故单独成模块。
"""

from __future__ import annotations

import re
from typing import Any

from app.ontology.schemas import Precondition, StateChange

_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

_PRE_SQL = {
    "eq": "{c} = {p}",
    "ne": "{c} <> {p}",
    "in": "{c} = ANY({p})",
    "not_in": "NOT ({c} = ANY({p}))",
    "is_null": "{c} IS NULL",
    "not_null": "{c} IS NOT NULL",
}


class WriteGuardError(ValueError):
    """动作声明不合法或试图构造越界语句。"""


def quote_ident(name: str) -> str:
    # fullmatch 而非 match：`$` 锚点容许尾部换行（`_IDENT.match("abc\n")` 通过），
    # 而白名单是"本模块唯一的注入防线"，锚点必须严格。同 Task 1 的 scope.py::_quote。
    if not isinstance(name, str) or not _IDENT.fullmatch(name):
        raise WriteGuardError(f"identifier rejected: {name!r}")
    return f'"{name}"'


def build_precondition_where(preconditions: list[Precondition]) -> tuple[str, dict[str, Any]]:
    """前置条件合取（AND）。空列表 → TRUE。

    **空值集合的语义按算子区分——守卫模块不产出恒真式**（`Precondition.value` 是
    `Any | None`，漏填即为 None，注册表 YAML 是热加载数据，可达）：
    - ``in`` 空 → 编译为 ``FALSE``（「不在空集里」没有行匹配，fail-closed）；
    - ``not_in`` 空 → **拒绝**（「不在空集里」字面等于「全部」，对守卫永远不是想要的：
      静默放行等于让前置条件形同不存在）；
    - ``is_null`` / ``not_null`` 不带 value，不受影响。
    """
    if not preconditions:
        return "TRUE", {}
    parts: list[str] = []
    params: dict[str, Any] = {}
    for i, cond in enumerate(preconditions):
        tmpl = _PRE_SQL.get(cond.op)
        if tmpl is None:
            raise WriteGuardError(f"unknown precondition op: {cond.op!r}")
        col = quote_ident(cond.field)
        if cond.op in ("is_null", "not_null"):
            parts.append(tmpl.format(c=col, p=""))
            continue
        key = f"pre_{i}"
        if cond.op in ("in", "not_in"):
            if not cond.value:
                if cond.op == "not_in":
                    raise WriteGuardError(f"empty value set for not_in on {cond.field!r}")
                # 空集的「属于」恒假。追加恒假合取项而非提前 return：后面的前置条件仍要过
                # 标识符白名单，校验结果不应依赖声明顺序。
                parts.append("FALSE")
                continue
            params[key] = list(cond.value)
        else:
            params[key] = cond.value
        parts.append(tmpl.format(c=col, p=f":{key}"))
    return " AND ".join(parts), params


def build_update_set(changes: list[StateChange]) -> tuple[str, dict[str, Any]]:
    """SET 子句。至少一条，否则拒绝（避免生成空 UPDATE）。"""
    if not changes:
        raise WriteGuardError("no state change declared")
    parts: list[str] = []
    params: dict[str, Any] = {}
    for i, ch in enumerate(changes):
        col = quote_ident(ch.field)
        if ch.now:
            parts.append(f"{col} = NOW()")
            continue
        key = f"set_{i}"
        params[key] = ch.set
        parts.append(f"{col} = :{key}")
    return ", ".join(parts), params
