"""动作写路径的 SQL 构造与守卫——**全库唯一的写路径标识符白名单与片段构造处**。

EAI-CUSTOM: 设计 §2。安全约定：
- 表名与列名只来自解析后的 ActionSpec（registry 声明），**绝不来自调用方 params**；
- 列名/表名一律过标识符白名单（``quote_ident``）并加引号；
- 值一律命名参数绑定。
语句骨架（``UPDATE ... SET ... WHERE ...``）由 executor 拼装、表名经 ``quote_ident``——
「唯一」限定在白名单与片段构造，**不含语句级拼装**。
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
    """前置条件合取（AND）。空列表 → TRUE（声明方未加前置条件，这是明确语义）。

    **不因「值退化」而产出恒真式**——`Precondition.value` 是 `Any | None` 且 registry 是
    热加载数据，故漏填与形状错都可达：
    - ``in`` / ``not_in`` **形状错**（str / 标量 / 映射）→ 拒绝：`list("rejected")` 会拆成
      字符，让「not_in rejected」放行它声明要拦的那一行（fail-open），标量则漏出裸 TypeError；
    - ``in`` 空 → 编译为 ``FALSE``（「不在空集里」没有行匹配，fail-closed）；
    - ``not_in`` 空 → **拒绝**（「不在空集里」字面等于「全部」，对守卫永远不是想要的）；
    - ``eq`` / ``ne`` 漏填 → 拒绝（``col = NULL`` 恒不成立，NULL 语义请用 ``is_null``）；
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
            # 这两个模板不含 {p}，故不喂占位符（喂了也是被丢弃的幽灵参数）。
            parts.append(tmpl.format(c=col))
            continue
        key = f"pre_{i}"
        if cond.op in ("in", "not_in"):
            # 形状守卫（与 F1 同一条 fail-open 线）：str 会被 list() 拆成字符，标量则抛
            # 裸 TypeError（不是本模块的错误契约，调用方 catch WriteGuardError 会放过它）。
            # None 不算形状错——它表示漏填，与空序列同走下面的「空值」语义。
            if cond.value is not None and not isinstance(cond.value, (list, tuple, set)):
                raise WriteGuardError(f"{cond.op} value must be a list on {cond.field!r}, got {type(cond.value).__name__}")
            if not cond.value:
                if cond.op == "not_in":
                    raise WriteGuardError(f"empty value set for not_in on {cond.field!r}")
                # 空集的「属于」恒假。追加恒假合取项而非提前 return：两者都 fail-closed，
                # 差别只在诊断一致性——提前 return 会让畸形标识符是否被拒取决于声明顺序。
                parts.append("FALSE")
                continue
            params[key] = list(cond.value)  # list() 兼作拷贝：绑定值不与调用方的 list 别名
        else:
            # eq / ne：必须给出值。`col = NULL` 恒不成立（NULL 该用 is_null），静默容忍会让
            # 前置条件永不满足、动作永不触发——与 F1/C1 同一类作者笔误。
            if cond.value is None:
                raise WriteGuardError(f"{cond.op} requires a value on {cond.field!r}; use is_null / not_null for NULL")
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
