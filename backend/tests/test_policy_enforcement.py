"""Composition tests: the deny pipeline end-to-end at the engine layer (DB mocked).

These tests exercise the full deny pipeline as it is wired in production:

    load_active_policies(db) -> UnifiedPermissionEngine -> check / list_permissions / find_deny_policy_name
    AND
    DataScopeEngine.get_data_scope(..., deny_scope_ids) composing ``allow AND NOT deny``

The DB session is mocked to the exact shape ``load_active_policies`` requires
(``await db.execute(select(...)).scalars().all()`` over PolicyModel rows), so we
verify the loader output plugs into the engine without a live PG schema.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.extensions.auth.engine import Policy, UnifiedPermissionEngine
from app.extensions.auth.identity import AttributeSet


def _policy(name, priority=0, conditions=None, grants=None):
    return Policy(name=name, priority=priority, conditions=conditions or {}, grants=grants or {})


def _mock_db(rows):
    """Build a mocked AsyncSession whose execute().scalars().all() yields ``rows``."""
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    db.execute.return_value = result
    return db


def _row(name, priority, conditions, grants):
    """A duck-typed PolicyModel row — load_active_policies only reads these attrs."""
    return SimpleNamespace(name=name, priority=priority, conditions=conditions, grants=grants)


@pytest.mark.asyncio
async def test_load_active_policies_feeds_engine_check_deny():
    """A policy loaded via load_active_policies denies a permission the role otherwise has."""
    from app.extensions.auth import policy_loader

    deny_policy = _policy("block_delete", grants={"deny_permissions": ["kb:delete"]})
    # mock the DB execute path load_active_policies uses:
    #   rows = (await db.execute(select(PolicyModel)...)).scalars().all()
    db = _mock_db([_row(deny_policy.name, deny_policy.priority, deny_policy.conditions, deny_policy.grants)])
    policies = await policy_loader.load_active_policies(db)
    assert len(policies) == 1
    assert policies[0].grants.get("deny_permissions") == ["kb:delete"]
    assert policies[0].name == "block_delete"

    engine = UnifiedPermissionEngine(
        role_permissions={"r": {"kb:read", "kb:delete"}},
        all_permission_ids={"kb:read", "kb:delete"},
        policies=policies,
    )
    idn = AttributeSet(user_id="u", username="u", role_code="r")

    # not denied — role perm intact
    assert engine.check(idn, "kb:read") is True
    # denied by policy despite role having the perm
    assert engine.check(idn, "kb:delete") is False
    assert engine.find_deny_policy_name(idn, "kb:delete") == "block_delete"
    assert engine.find_deny_policy_name(idn, "kb:read") is None

    perms = engine.list_permissions(idn)
    assert "kb:read" in perms
    assert "kb:delete" not in perms


@pytest.mark.asyncio
async def test_load_active_policies_orders_by_priority_and_engine_respects_deny():
    """Multiple policies: loader returns them priority-sorted by the query; deny overrides an allow-policy grant."""
    from app.extensions.auth import policy_loader

    allow_p = _policy("allow_write", priority=10, grants={"permissions": ["kb:write"]})
    deny_p = _policy("deny_write", priority=20, grants={"deny_permissions": ["kb:write"]})
    db = _mock_db([
        _row(allow_p.name, allow_p.priority, allow_p.conditions, allow_p.grants),
        _row(deny_p.name, deny_p.priority, deny_p.conditions, deny_p.grants),
    ])
    policies = await policy_loader.load_active_policies(db)
    assert [p.name for p in policies] == ["allow_write", "deny_write"]

    engine = UnifiedPermissionEngine(
        role_permissions={"r": {"kb:read"}},
        all_permission_ids={"kb:read", "kb:write"},
        policies=policies,
    )
    idn = AttributeSet(user_id="u", username="u", role_code="r")
    # allow-policy grants kb:write but deny-policy revokes it -> deny-overrides
    assert engine.check(idn, "kb:read") is True
    assert engine.check(idn, "kb:write") is False
    assert engine.find_deny_policy_name(idn, "kb:write") == "deny_write"
    perms = engine.list_permissions(idn)
    assert "kb:write" not in perms


def test_data_scope_deny_composes_and_not():
    """DataScopeEngine: allow scopes minus a deny scope = allow AND NOT deny."""
    from app.extensions.auth.datascope import DataScopeEngine
    from app.extensions.auth.registry import DataScope

    scopes = {"knowledge": [
        DataScope(id="knowledge_owner", display_name="o",
                  rule_template={"owner_id": "$identity.user_id"}, module="knowledge"),
        DataScope(id="knowledge_public", display_name="p",
                  rule_template={"access_type": "public"}, module="knowledge"),
    ]}
    idn = AttributeSet(user_id="u1", username="u1", role_code="r")
    eng = DataScopeEngine(scopes, role_data_scopes={"r": ["knowledge_owner", "knowledge_public"]})

    rule = eng.get_data_scope(idn, "knowledge", deny_scope_ids={"knowledge_public"})
    # composed: allow-union AND NOT deny-scope
    assert rule.operator == "and"
    assert rule.children[1].operator == "not"
    # allow side is an OR of the two scopes
    assert rule.children[0].operator == "or"
    # deny side wraps the single denied scope
    assert rule.children[1].children[0].operator == "eq"
    assert rule.children[1].children[0].field == "access_type"


def test_data_scope_no_deny_returns_plain_allow_union():
    """When deny_scope_ids is empty, get_data_scope returns the allow union unchanged."""
    from app.extensions.auth.datascope import DataScopeEngine
    from app.extensions.auth.registry import DataScope

    scopes = {"knowledge": [
        DataScope(id="knowledge_owner", display_name="o",
                  rule_template={"owner_id": "$identity.user_id"}, module="knowledge"),
    ]}
    idn = AttributeSet(user_id="u1", username="u1", role_code="r")
    eng = DataScopeEngine(scopes, role_data_scopes={"r": ["knowledge_owner"]})

    rule = eng.get_data_scope(idn, "knowledge", deny_scope_ids=None)
    assert rule.operator == "eq"
    assert rule.field == "owner_id"
    assert rule.value == "u1"


def test_superadmin_immune_across_pipeline():
    """Superadmin: check returns True, list_permissions returns all, deny never applies."""
    deny = _policy("block", grants={"deny_permissions": ["kb:read"]})
    engine = UnifiedPermissionEngine(
        role_permissions={"super": {"*"}},
        all_permission_ids={"kb:read", "kb:write"},
        policies=[deny],
    )
    sup = AttributeSet(user_id="s", username="s", role_code="super")

    # wildcard short-circuits before deny evaluation
    assert engine.check(sup, "kb:read") is True
    assert engine.check(sup, "kb:write") is True
    # list_permissions returns the full universe, deny ignored
    assert engine.list_permissions(sup) == {"kb:read", "kb:write"}
