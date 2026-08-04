"""Task 12: project IDOR closure — require_project_member dependency tests.

These unit-test the membership-gate dependency logic without an async DB
fixture (mirrors the AsyncMock/MagicMock pattern in test_knowledge_data_access.py).
Asserts: superadmin bypasses, member passes, non-member → 403,
missing project_id → 400. Also locks the project_member data_scope template
to the OR(created_by, member_projects) shape.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.extensions.auth.unified_permissions import require_project_member


def _make_request(project_id=None):
    req = MagicMock()
    if project_id is None:
        req.path_params = {}
    else:
        req.path_params = {"project_id": str(project_id)}
    return req


def _make_user():
    u = MagicMock()
    u.id = uuid.uuid4()
    return u


def _mock_db_with_member(member_row):
    """AsyncMock session whose execute(...).scalar_one_or_none() returns member_row."""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = member_row
    db.execute.return_value = result
    return db


@pytest.mark.asyncio
async def test_superadmin_bypasses_membership(monkeypatch):
    """Superadmin passes without a ProjectMember row (membership query skipped)."""

    async def _true(db, user_id):
        return True

    monkeypatch.setattr("app.extensions.auth.admin.is_superadmin", _true)
    check = require_project_member()
    user = _make_user()
    db = _mock_db_with_member(None)  # no member row — would 403 a non-admin
    req = _make_request(uuid.uuid4())
    rv = await check(request=req, current_user=user, db=db)
    assert rv is user
    db.execute.assert_not_awaited()  # membership query skipped on admin bypass


@pytest.mark.asyncio
async def test_member_passes(monkeypatch):
    """A user with a ProjectMember row for the project passes."""

    async def _false(db, user_id):
        return False

    monkeypatch.setattr("app.extensions.auth.admin.is_superadmin", _false)
    check = require_project_member()
    user = _make_user()
    db = _mock_db_with_member(MagicMock())  # truthy member row
    req = _make_request(uuid.uuid4())
    rv = await check(request=req, current_user=user, db=db)
    assert rv is user


@pytest.mark.asyncio
async def test_non_member_is_forbidden(monkeypatch):
    """A user without a ProjectMember row gets HTTP 403."""

    async def _false(db, user_id):
        return False

    monkeypatch.setattr("app.extensions.auth.admin.is_superadmin", _false)
    check = require_project_member()
    user = _make_user()
    db = _mock_db_with_member(None)  # no member row
    req = _make_request(uuid.uuid4())
    with pytest.raises(HTTPException) as exc:
        await check(request=req, current_user=user, db=db)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_missing_project_id_returns_400(monkeypatch):
    """When project_id is absent from path_params, return 400 (not 403)."""

    async def _false(db, user_id):
        return False

    monkeypatch.setattr("app.extensions.auth.admin.is_superadmin", _false)
    check = require_project_member()
    user = _make_user()
    db = _mock_db_with_member(None)
    req = _make_request(None)  # no project_id key
    with pytest.raises(HTTPException) as exc:
        await check(request=req, current_user=user, db=db)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_invalid_project_id_returns_400(monkeypatch):
    """A malformed project_id is reported as 400, not 500."""

    async def _false(db, user_id):
        return False

    monkeypatch.setattr("app.extensions.auth.admin.is_superadmin", _false)
    check = require_project_member()
    user = _make_user()
    db = _mock_db_with_member(None)
    req = MagicMock()
    req.path_params = {"project_id": "not-a-uuid"}
    with pytest.raises(HTTPException) as exc:
        await check(request=req, current_user=user, db=db)
    assert exc.value.status_code == 400


def test_project_member_scope_includes_created_by():
    """project_member data_scope must OR created_by with member_projects.

    This matches the hand-rolled list_projects filter's semantics
    (created_by OR member) so a future with_data_scope("projects") wiring
    preserves creator visibility.
    """
    from app.extensions.auth.registry import get_permission_registry

    reg = get_permission_registry()
    ds = reg.get_data_scope("project_member")
    assert ds is not None, "project_member scope must be declared in permissions.yaml"
    tpl = ds.rule_template
    # New shape: { or: [ { id IN: member_projects }, { created_by: user_id } ] }
    assert "or" in tpl, f"project_member template must compose with 'or': {tpl}"
    # Both branches must be present
    rendered = str(tpl)
    assert "created_by" in rendered, f"created_by branch missing: {tpl}"
    assert "member_projects" in rendered, f"member_projects branch missing: {tpl}"
