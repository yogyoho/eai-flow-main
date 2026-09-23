"""Unified ABAC-lite permission engine."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import false as sqlalchemy_false
from sqlalchemy import true as sqlalchemy_true

from app.extensions.auth.identity import AttributeSet

logger = logging.getLogger(__name__)


def _wire_value(value: Any) -> Any:
    """把 ``value`` 里的 ``uuid.UUID`` 归一为 ``str``——线格式（JSON）里没有 UUID 类型。

    EAI-CUSTOM (2026-09-23, M-4)：为什么在 ``to_wire`` 内做而不是交给调用方——
    ``overlap`` 的 value 由 ``from_template`` 强转成 ``list[uuid.UUID]``（见该处 M3 防御性
    强转）。经 FastAPI 返回时 ``jsonable_encoder`` 会顺手转字符串，于是**任何非 FastAPI
    消费点拿到的仍是 UUID 对象**：同一个函数在不同调用路径下产出不同类型的线格式，
    对端（OntoStudio 的 ``from_wire``，只做 JSON 反序列化）行为不一致。函数自身必须自洽。

    只转 UUID，**不**做成 ``str(value)`` 一把梭：``eq`` 的值可以是 int/bool，一刀切会把
    它们变成字符串，对端按字符串绑定到整型列会直接报类型错（那是引入新故障，不是归一）。
    """
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [str(v) if isinstance(v, uuid.UUID) else v for v in value]
    return value


@dataclass
class FilterRule:
    """Serializable filter rule tree. NONE_ALLOW = deny all (empty default)."""

    operator: str = "none_allow"
    field: str | None = None
    value: Any = None
    children: list[FilterRule] | None = None

    @classmethod
    def from_template(cls, template: dict, identity: AttributeSet) -> FilterRule:
        if template is None:
            return cls(operator="none_allow")

        if isinstance(template, dict) and not template:
            return cls(operator="allow_all")  # 空模板 = 全量访问

        if "or" in template:
            return cls(
                operator="or",
                children=[cls.from_template(child, identity) for child in template["or"]],
            )
        if "and" in template:
            return cls(
                operator="and",
                children=[cls.from_template(child, identity) for child in template["and"]],
            )

        for key, raw_value in template.items():
            if " IN" in key:
                field = key[: key.rfind(" IN")].strip()
                resolved = cls._resolve(raw_value, identity)
                if resolved is None:
                    return cls(operator="none_allow")
                return cls(operator="in", field=field, value=resolved if isinstance(resolved, list) else [resolved])
            if " OVERLAP" in key:
                field = key[: key.rfind(" OVERLAP")].strip()
                resolved = cls._resolve(raw_value, identity)
                if not resolved:
                    return cls(operator="none_allow")  # identity has no such attr -> intersection empty -> deny
                # EAI-CUSTOM (M3): defensive UUID coercion. ``identity.dept_ids`` is
                # always populated with UUID-strings today (identity.py), but a
                # malformed value would otherwise raise ValueError → HTTP 500.
                # Fall back to deny (none_allow) — the safe default — instead.
                try:
                    coerced = [uuid.UUID(x) for x in resolved] if isinstance(resolved[0], str) else list(resolved)
                except (ValueError, TypeError):
                    return cls(operator="none_allow")
                return cls(operator="overlap", field=field, value=coerced)
            else:
                resolved = cls._resolve(raw_value, identity)
                return cls(operator="eq", field=key, value=resolved)

        return cls(operator="none_allow")

    @staticmethod
    def _resolve(value: Any, identity: AttributeSet) -> Any:
        if isinstance(value, str) and value.startswith("$identity."):
            path = value[len("$identity.") :]
            return identity.get_attr(path)
        return value

    def to_dict(self) -> dict:
        return {
            "operator": self.operator,
            "field": self.field,
            "value": self.value,
            "children": [c.to_dict() for c in self.children] if self.children else None,
        }

    def to_wire(self) -> dict[str, Any]:
        """序列化给 OntoStudio（独立服务，无法 import 本模块）。

        EAI-CUSTOM (2026-09-22): 形态必须与 ontostudio/backend/app/ontology/scope.py::FilterRule.to_wire
        逐字段一致（那边有 33 条测试守着 `from_wire` 回读）。
        M-4 (2026-09-23): ``value`` 内的 ``uuid.UUID`` 在本方法内归一为字符串（见
        ``_wire_value``）——此前依赖 FastAPI 的 jsonable_encoder，非 FastAPI 消费点会拿到
        UUID 对象，同一函数产出两种线格式。
        与 ``to_dict`` 的差别：``to_dict`` 恒带 field/value/children（缺失为 null），
        ``to_wire`` 省略 None 字段——对端 ``from_wire`` 两种形态都能吃，但线格式以本方法为准。
        **跨服务契约由 backend/tests/data/permissions_scope_wire_golden.json 钉住**
        （产出侧断 to_wire == golden，消费侧断 from_wire(golden) 可编译）。
        """
        out: dict[str, Any] = {"operator": self.operator}
        if self.field is not None:
            out["field"] = self.field
        if self.value is not None:
            out["value"] = _wire_value(self.value)
        if self.children is not None:
            out["children"] = [c.to_wire() for c in self.children]
        return out

    def to_sqlalchemy(self, model, column_map: dict | None = None):
        """Convert FilterRule to SQLAlchemy BinaryExpression.

        Uses column_map for explicit field-to-column mapping; falls back to
        getattr(model, field) for auto-resolution.
        """
        from sqlalchemy import and_, not_, or_

        column_map = column_map or {}

        # Composite operators — no field, recurse into children (must precede column resolution)
        if self.operator == "and" and self.children:
            return and_(*[c.to_sqlalchemy(model, column_map) for c in self.children])
        if self.operator == "or" and self.children:
            return or_(*[c.to_sqlalchemy(model, column_map) for c in self.children])
        if self.operator == "not" and self.children:
            return not_(self.children[0].to_sqlalchemy(model, column_map))

        # Leaf operators
        if self.operator == "none_allow":
            return sqlalchemy_false()  # WHERE FALSE
        if self.operator == "allow_all":
            return sqlalchemy_true()  # WHERE TRUE

        # Resolve column for field-based leaves
        col = None
        if column_map and self.field in column_map:
            col = column_map[self.field]
        elif self.field and hasattr(model, self.field):
            col = getattr(model, self.field)
        if col is None:
            return sqlalchemy_false()  # Unknown field — deny by default

        if self.operator == "eq":
            return col == self.value
        if self.operator == "in":
            if not self.value:
                return sqlalchemy_false()
            return col.in_(self.value)
        if self.operator == "overlap":
            if not self.value:
                return sqlalchemy_false()
            return col.overlap(self.value)  # PG && ; col must be an ARRAY column

        return sqlalchemy_false()


@dataclass
class Policy:
    """A stored ABAC policy."""

    name: str
    priority: int
    conditions: dict
    grants: dict


def evaluate_policy_conditions(conditions: dict, identity: AttributeSet) -> bool:
    """Evaluate an ABAC policy condition tree against an identity.

    Shared single-source evaluator used by UnifiedPermissionEngine, require_permission,
    /me, and with_data_scope. Empty conditions = match all (True).
    """
    if not conditions:
        return True

    if "and" in conditions:
        return all(evaluate_policy_conditions(c, identity) for c in conditions["and"])
    if "or" in conditions:
        return any(evaluate_policy_conditions(c, identity) for c in conditions["or"])

    attr_name = conditions.get("attr", "")
    op = conditions.get("op", "eq")
    expected = conditions.get("value")

    attr_value = identity.get_attr(attr_name)

    operators = {
        "eq": lambda a, v: a == v,
        "neq": lambda a, v: a != v,
        "gt": lambda a, v: a is not None and a > v,
        "gte": lambda a, v: a is not None and a >= v,
        "lt": lambda a, v: a is not None and a < v,
        "lte": lambda a, v: a is not None and a <= v,
        "contains": lambda a, v: v in a if isinstance(a, (list, str)) else False,
        "not_contains": lambda a, v: v not in a if isinstance(a, (list, str)) else False,
        "in": lambda a, v: a in v if isinstance(v, (list, tuple)) else False,
        "not_in": lambda a, v: a not in v if isinstance(v, (list, tuple)) else False,
    }

    evaluator = operators.get(op)
    if evaluator is None:
        logger.warning("Unknown operator '%s' in policy condition", op)
        return False

    return evaluator(attr_value, expected)


class UnifiedPermissionEngine:
    """ABAC-lite engine. Evaluation order: * wildcard -> direct role perm -> ABAC policies -> deny."""

    def __init__(
        self,
        role_permissions: dict[str, set[str]] | None = None,
        all_permission_ids: set[str] | None = None,
        policies: list[Policy] | None = None,
    ):
        self._role_permissions: dict[str, set[str]] = role_permissions or {}
        self._all_permission_ids: set[str] = all_permission_ids or set()
        self._policies: list[Policy] = sorted(policies or [], key=lambda p: p.priority)

    def check(self, identity: AttributeSet, permission: str) -> bool:
        role_code = identity.role_code or ""
        role_perms = self._role_permissions.get(role_code, set())

        # 1. Superadmin wildcard — deny never applies
        if "*" in role_perms:
            return True

        prefix = permission.split(":", 1)[0]
        # 2. Collect allow: role perms + matching policy allow-grants
        allowed = set(role_perms)
        for p in self._policies:
            if evaluate_policy_conditions(p.conditions, identity):
                allowed.update(p.grants.get("permissions") or [])
        if not (permission in allowed or f"{prefix}:*" in allowed):
            return False
        # 3. deny-overrides: any matching policy that denies this exact perm or the module wildcard
        if self.find_deny_policy_name(identity, permission) is not None:
            return False
        return True

    def find_deny_policy_name(self, identity: AttributeSet, permission: str) -> str | None:
        """Return the name of the first matching policy that denies this permission (exact or module-wildcard), else None."""
        prefix = permission.split(":", 1)[0]
        for p in self._policies:
            if evaluate_policy_conditions(p.conditions, identity):
                denied = p.grants.get("deny_permissions") or []
                if permission in denied or f"{prefix}:*" in denied:
                    return p.name
        return None

    def list_permissions(self, identity: AttributeSet) -> set[str]:
        role_code = identity.role_code or ""
        role_perms = self._role_permissions.get(role_code, set())

        # Superadmin — deny never applies
        if "*" in role_perms:
            return set(self._all_permission_ids)

        def expand(perms):
            out = set()
            for p in perms:
                if p == "*":
                    out |= set(self._all_permission_ids)
                elif p.endswith(":*"):
                    prefix = p[:-1]  # keep trailing ':' so 'kb:*' -> prefix 'kb:'
                    out |= {x for x in self._all_permission_ids if x.startswith(prefix)}
                else:
                    out.add(p)
            return out

        allowed = expand(role_perms)
        denied = set()
        for pol in self._policies:
            if evaluate_policy_conditions(pol.conditions, identity):
                allowed |= expand(pol.grants.get("permissions") or [])
                denied |= expand(pol.grants.get("deny_permissions") or [])
        return allowed - denied
