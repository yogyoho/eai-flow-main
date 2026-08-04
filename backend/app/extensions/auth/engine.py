"""Unified ABAC-lite permission engine."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import false as sqlalchemy_false, true as sqlalchemy_true

from app.extensions.auth.identity import AttributeSet

logger = logging.getLogger(__name__)


@dataclass
class FilterRule:
    """Serializable filter rule tree. NONE_ALLOW = deny all (empty default)."""

    operator: str = "none_allow"
    field: str | None = None
    value: Any = None
    children: list["FilterRule"] | None = None

    @classmethod
    def from_template(cls, template: dict, identity: AttributeSet) -> "FilterRule":
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
                field = key[:key.rfind(" IN")].strip()
                resolved = cls._resolve(raw_value, identity)
                if resolved is None:
                    return cls(operator="none_allow")
                return cls(operator="in", field=field, value=resolved if isinstance(resolved, list) else [resolved])
            if " OVERLAP" in key:
                field = key[: key.rfind(" OVERLAP")].strip()
                resolved = cls._resolve(raw_value, identity)
                if not resolved:
                    return cls(operator="none_allow")  # identity has no such attr -> intersection empty -> deny
                coerced = [uuid.UUID(x) for x in resolved] if isinstance(resolved[0], str) else list(resolved)
                return cls(operator="overlap", field=field, value=coerced)
            else:
                resolved = cls._resolve(raw_value, identity)
                return cls(operator="eq", field=key, value=resolved)

        return cls(operator="none_allow")

    @staticmethod
    def _resolve(value: Any, identity: AttributeSet) -> Any:
        if isinstance(value, str) and value.startswith("$identity."):
            path = value[len("$identity."):]
            return identity.get_attr(path)
        return value

    def to_dict(self) -> dict:
        return {
            "operator": self.operator,
            "field": self.field,
            "value": self.value,
            "children": [c.to_dict() for c in self.children] if self.children else None,
        }

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

        # 1. Wildcard
        if "*" in role_perms:
            return True

        # 2. Direct match + module wildcard
        prefix = permission.split(":", 1)[0]
        if permission in role_perms or f"{prefix}:*" in role_perms:
            return True

        # 3. ABAC policies
        for policy in self._policies:
            if self._evaluate_conditions(policy.conditions, identity):
                if permission in (policy.grants.get("permissions") or []):
                    return True

        # 4. Deny
        return False

    def list_permissions(self, identity: AttributeSet) -> set[str]:
        role_code = identity.role_code or ""
        role_perms = self._role_permissions.get(role_code, set())

        if "*" in role_perms:
            return set(self._all_permission_ids)

        result = set(role_perms)

        for policy in self._policies:
            if self._evaluate_conditions(policy.conditions, identity):
                for p in policy.grants.get("permissions") or []:
                    result.add(p)

        return result

    def _evaluate_conditions(self, conditions: dict, identity: AttributeSet) -> bool:
        if not conditions:
            return True

        if "and" in conditions:
            return all(self._evaluate_conditions(c, identity) for c in conditions["and"])
        if "or" in conditions:
            return any(self._evaluate_conditions(c, identity) for c in conditions["or"])

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
