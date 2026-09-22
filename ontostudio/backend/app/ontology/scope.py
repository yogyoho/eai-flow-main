"""数据范围规则树：wire 编解码 + 编译为参数化 SQL WHERE。

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-22-ontostudio-action-layer-design.md §3。
FilterRule 的字段形态**对齐** gateway backend/app/extensions/auth/engine.py::FilterRule——
两侧各自持有数据类（OntoStudio 是独立服务，无法 import app.*），wire 用同名字段。
gateway 侧字段或算子变更时，此处必须同步。

安全：字段名不经值绑定，故走标识符白名单 + 加引号；任何值一律命名参数绑定。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# 字段名白名单：SQL 标识符只允许字母/下划线开头，其余为字母数字下划线。
# 字段名无法走值绑定（列名不是值），因此这是本模块唯一的注入防线，不得放宽。
_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# 叶子算子 → SQL 模板（{c}=列占位，{p}=参数占位）
_LEAF_SQL = {
    "eq": "{c} = {p}",
    "ne": "{c} <> {p}",
    "in": "{c} = ANY({p})",
    "not_in": "NOT ({c} = ANY({p}))",
    "overlap": "{c} && {p}",
}


class ScopeCompileError(ValueError):
    """规则树不合法（未知算子 / 未绑定字段 / 非法标识符）。"""


@dataclass
class FilterRule:
    operator: str = "none_allow"  # allow_all|none_allow|and|or|not|eq|ne|in|not_in|overlap
    field: str | None = None
    value: Any = None
    children: list[FilterRule] | None = None

    def to_wire(self) -> dict[str, Any]:
        out: dict[str, Any] = {"operator": self.operator}
        if self.field is not None:
            out["field"] = self.field
        if self.value is not None:
            out["value"] = self.value
        if self.children is not None:
            out["children"] = [c.to_wire() for c in self.children]
        return out

    @classmethod
    def from_wire(cls, data: dict[str, Any]) -> FilterRule:
        return cls(
            operator=data["operator"],
            field=data.get("field"),
            value=data.get("value"),
            children=[cls.from_wire(c) for c in data["children"]] if data.get("children") else None,
        )


def _quote(field_name: str, bindings: dict[str, str] | None) -> str:
    """把模板字段名解析为物理列名并加引号。

    ``bindings=None`` 表示不做映射（恒等：模板字段名即列名）；
    ``bindings={...}`` 表示显式映射表——此时**每个**字段都必须命中，未命中即报错。
    两者语义不同（None=恒等，{}=全未绑定），这是刻意的：显式映射下静默退回恒等会让
    registry 里漏配的 scope_bindings 变成"看起来能用"的越权读，故宁可直接失败。
    """
    if bindings is None:
        physical = field_name
    else:
        if field_name not in bindings:
            raise ScopeCompileError(f"unbound field in scope bindings: {field_name!r}")
        physical = bindings[field_name]
    if not _IDENT.match(physical):
        raise ScopeCompileError(f"illegal identifier for scope field {field_name!r}: {physical!r}")
    return f'"{physical}"'


def rule_to_sql(rule: FilterRule, bindings: dict[str, str] | None = None) -> tuple[str, dict[str, Any]]:
    """编译为 (WHERE 片段, 命名参数)。bindings=None 表示不做字段名映射（恒等）。"""
    params: dict[str, Any] = {}
    counter = [0]  # 闭包内自增用列表，避免 nonlocal 声明

    def walk(node: FilterRule) -> str:
        op = node.operator
        if op == "allow_all":
            return "TRUE"
        if op == "none_allow":
            return "FALSE"
        if op in ("and", "or"):
            kids = node.children or []
            # 空 AND 是全真、空 OR 是全假——按布尔恒等式取，不用 fail-open 或 fail-closed 例外。
            if not kids:
                return "TRUE" if op == "and" else "FALSE"
            joiner = " AND " if op == "and" else " OR "
            return "(" + joiner.join(walk(k) for k in kids) + ")"
        if op == "not":
            kids = node.children or []
            if not kids:
                return "TRUE"
            return "NOT (" + walk(kids[0]) + ")"
        if op in _LEAF_SQL:
            if node.field is None:
                raise ScopeCompileError(f"operator {op!r} requires a field")
            key = f"scope_{counter[0]}"
            counter[0] += 1
            params[key] = node.value if op not in ("in", "not_in") else list(node.value or [])
            return _LEAF_SQL[op].format(c=_quote(node.field, bindings), p=f":{key}")
        raise ScopeCompileError(f"unknown operator: {op!r}")

    return walk(rule), params
