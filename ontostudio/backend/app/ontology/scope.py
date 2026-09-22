"""数据范围规则树：wire 编解码 + 编译为参数化 SQL WHERE。

EAI-CUSTOM: 设计 docs/superpowers/specs/2026-09-22-ontostudio-action-layer-design.md §3。
FilterRule 的字段形态**对齐** gateway backend/app/extensions/auth/engine.py::FilterRule——
两侧各自持有数据类（OntoStudio 是独立服务，无法 import app.*），wire 用同名字段。
gateway 侧字段或算子变更时，此处必须同步。

注意本侧算子集是 gateway 的**超集**：网关只产出/处理 eq / in / overlap（+ and / or /
allow_all / none_allow），**没有** ne / not_in / not。故不可假设网关会下发 ne/not_in；
反向（本侧新增算子）才需要在此与 engine.py 对齐。

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
    """规则树不合法（wire 畸形 / 未知算子 / 未绑定字段 / 非法标识符）。

    本模块自己拥有 wire 解码与标识符校验，故所有畸形输入都归一到这里——
    调用方（executor）只需捕获本异常映射 4xx，不会漏出 KeyError/TypeError/AttributeError。
    """


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
        # 数据源是外部 JSON，缺键/类型错都归一为 ScopeCompileError（契约见类 docstring）。
        # 递归解码器必须校验自身输入形状，否则 children 类型错会漏出
        # AttributeError('str' has no 'get') / TypeError(int not iterable)，executor 变 500。
        if not isinstance(data, dict):
            raise ScopeCompileError(f"malformed wire rule: expected object, got {type(data).__name__}")
        op = data.get("operator")
        if not isinstance(op, str):
            raise ScopeCompileError(f"malformed wire rule: operator={op!r}")
        children = data.get("children")
        if children is not None and not isinstance(children, list):
            raise ScopeCompileError(f"malformed wire rule: children must be a list, got {type(children).__name__}")
        # children=[] 与 children=null 都折叠为 None——二者编译期等价（三种复合算子走同一
        # 分支），故此处归一化是 wire 契约的一部分，而非信息丢失。
        # 注意：旧形态 gateway to_dict 输出的是 "children": null（engine.py:34-36 可产出
        # children=[]，序列化后成 null），归一化正是为兼容该形态。
        return cls(
            operator=op,
            field=data.get("field"),
            value=data.get("value"),
            children=[cls.from_wire(c) for c in children] if children else None,
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
    # fullmatch 而非 match：re 的 `$` 锚点允许尾部换行（"abc\n" 会通过），而白名单是本模块
    # 唯一的注入防线，锚点必须严格。isinstance 检查则挡下 scope_bindings 来自手写 YAML 的
    # 类型错（{user_id: 1} 漏引号 -> int），否则会漏出 TypeError。
    if not isinstance(physical, str) or not _IDENT.fullmatch(physical):
        raise ScopeCompileError(f"illegal identifier for scope field {field_name!r}: {physical!r}")
    return f'"{physical}"'


def rule_to_sql(rule: FilterRule, bindings: dict[str, str] | None = None) -> tuple[str, dict[str, Any]]:
    """编译为 (WHERE 片段, 命名参数)。bindings=None 表示不做字段名映射（恒等）。"""
    params: dict[str, Any] = {}
    counter = [0]  # 闭包内自增用列表，避免 nonlocal 声明

    def walk(node: FilterRule) -> str:
        # 子节点可能来自未经 from_wire 的裸 JSON（调用方直接构造/反序列化），
        # 归一为 ScopeCompileError 而非漏出 AttributeError。
        if not isinstance(node, FilterRule):
            raise ScopeCompileError(f"rule node must be a FilterRule, got {type(node).__name__}")
        op = node.operator
        if op == "allow_all":
            return "TRUE"
        if op == "none_allow":
            return "FALSE"
        if op in ("and", "or"):
            kids = node.children or []
            if not kids:
                # 空 or = FALSE，与网关 to_sqlalchemy 同向（deny），无害。
                # 空 and 在布尔恒等式下是 TRUE，即**静默放行全域**，与参考实现判定正相反；
                # allow_all 已有独立算子表达全量，故空 and 无合法含义 -> 拒绝而非放行。
                if op == "or":
                    return "FALSE"
                raise ScopeCompileError("empty composite rule: and")
            joiner = " AND " if op == "and" else " OR "
            return "(" + joiner.join(walk(k) for k in kids) + ")"
        if op == "not":
            kids = node.children or []
            # not 是严格一元算子：空 -> 拒绝（同 and，绝不静默放行全域）；
            # 多于一个 -> 拒绝而非静默丢弃多余子树（丢弃会让判定与规则作者意图不符）。
            if not kids:
                raise ScopeCompileError("empty composite rule: not")
            if len(kids) > 1:
                raise ScopeCompileError(f"not expects exactly one child, got {len(kids)}")
            return "NOT (" + walk(kids[0]) + ")"
        if op in _LEAF_SQL:
            if node.field is None:
                raise ScopeCompileError(f"operator {op!r} requires a field")
            key = f"scope_{counter[0]}"
            counter[0] += 1
            raw = node.value
            if op in ("in", "not_in"):
                # 集合算子：裸字符串 = 单元素集合（与 gateway from_template 的
                # "resolved if isinstance(resolved, list) else [resolved]" 同义），
                # 绝不按字符拆开——"abc" 拆成 ["a","b","c"] 是静默的错误语义，且 in 方向会放宽。
                # 只特判 str：其余非 list 序列沿用 list() 归一，不包成 [tuple]。
                # 标量算子（eq/ne/overlap）不走此归一，否则 "d1" 会被包成 ["d1"]。
                if isinstance(raw, str):
                    raw = [raw]
                raw = list(raw or [])
            params[key] = raw
            return _LEAF_SQL[op].format(c=_quote(node.field, bindings), p=f":{key}")
        raise ScopeCompileError(f"unknown operator: {op!r}")

    return walk(rule), params
