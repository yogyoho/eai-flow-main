"""Data scope engine - resolves role data_scopes to FilterRules."""
from __future__ import annotations

from app.extensions.auth.engine import FilterRule
from app.extensions.auth.identity import AttributeSet
from app.extensions.auth.registry import DataScope, get_permission_registry


class DataScopeEngine:
    """Resolves data scope configurations to executable FilterRules."""

    def __init__(
        self,
        scopes_by_resource: dict[str, list[DataScope]] | None = None,
        role_data_scopes: dict[str, list[str]] | None = None,
    ):
        self._scopes_by_resource = scopes_by_resource or {}
        self._role_data_scopes = role_data_scopes or {}

    @classmethod
    def from_registry(cls) -> "DataScopeEngine":
        """Build engine from the global PermissionRegistry."""
        return cls.from_registry_with(get_permission_registry())

    @classmethod
    def from_registry_with(cls, registry) -> "DataScopeEngine":
        """Build engine from a given PermissionRegistry (supports overlay in tests)."""
        scopes_by_resource: dict[str, list[DataScope]] = {}
        for module_key, mp in registry.list_modules():
            if mp.data_scopes:
                scopes_by_resource[module_key] = mp.data_scopes

        role_data_scopes: dict[str, list[str]] = {}
        for code in registry.list_role_codes():
            role_data_scopes[code] = registry.get_data_scopes_for_role(code)

        return cls(scopes_by_resource, role_data_scopes)

    def get_data_scope(self, identity: AttributeSet, resource_type: str) -> FilterRule:
        """Return a FilterRule for what this identity can see of resource_type."""
        scopes = self._scopes_by_resource.get(resource_type)
        if not scopes:
            return FilterRule(operator="none_allow")

        role_code = identity.role_code or ""
        allowed_scope_ids = self._role_data_scopes.get(role_code, [])

        applicable = [s for s in scopes if s.id in allowed_scope_ids]
        if not applicable:
            return FilterRule(operator="none_allow")

        if len(applicable) == 1:
            return FilterRule.from_template(applicable[0].rule_template, identity)

        children = [FilterRule.from_template(s.rule_template, identity) for s in applicable]
        children = [c for c in children if c.operator != "none_allow"]
        if not children:
            return FilterRule(operator="none_allow")
        if len(children) == 1:
            return children[0]
        return FilterRule(operator="or", children=children)
