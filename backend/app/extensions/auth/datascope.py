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

    def build_scope_union(
        self,
        identity: AttributeSet,
        resource_type: str,
        scope_ids,
    ) -> FilterRule:
        """Build an OR-union of FilterRules for the given scope_ids.

        Shared combiner used by both the allow path (scopes granted to the
        identity's role) and the deny path (scopes blocked by active policies).
        ``scope_ids`` is an explicit iterable of DataScope ids; it replaces the
        old inline read of ``self._role_data_scopes`` so allow and deny share
        identical union semantics.
        """
        scopes = self._scopes_by_resource.get(resource_type)
        if not scopes:
            return FilterRule(operator="none_allow")

        scope_id_set = set(scope_ids or [])
        applicable = [s for s in scopes if s.id in scope_id_set]
        if not applicable:
            return FilterRule(operator="none_allow")

        if len(applicable) == 1:
            return FilterRule.from_template(applicable[0].rule_template, identity)

        children = [FilterRule.from_template(s.rule_template, identity) for s in applicable]
        if any(c.operator == "allow_all" for c in children):
            return FilterRule(operator="allow_all")
        children = [c for c in children if c.operator != "none_allow"]
        if not children:
            return FilterRule(operator="none_allow")
        if len(children) == 1:
            return children[0]
        return FilterRule(operator="or", children=children)

    def get_data_scope(
        self,
        identity: AttributeSet,
        resource_type: str,
        deny_scope_ids=None,
    ) -> FilterRule:
        """Return a FilterRule for what this identity can see of resource_type.

        When ``deny_scope_ids`` resolves to a non-empty deny rule, the result
        is ``allow_rule AND NOT deny_rule``. Empty / unset deny returns the
        plain allow union unchanged. A deny that matches an empty-template
        (allow_all) scope collapses to ``none_allow`` (deny everything).
        """
        deny_scope_ids = deny_scope_ids or set()
        allow_rule = self.build_scope_union(
            identity,
            resource_type,
            self._role_data_scopes.get(identity.role_code or "", []),
        )
        deny_rule = self.build_scope_union(identity, resource_type, deny_scope_ids)
        if deny_rule.operator == "none_allow":
            return allow_rule                       # no applicable deny
        if deny_rule.operator == "allow_all":
            return FilterRule(operator="none_allow")  # deny matched empty-template scope = deny all
        return FilterRule(
            operator="and",
            children=[allow_rule, FilterRule(operator="not", children=[deny_rule])],
        )
