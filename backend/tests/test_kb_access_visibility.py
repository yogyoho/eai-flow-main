"""Tests for knowledge base three-tier access visibility (private / dept / public)."""

from uuid import uuid4

import pytest

from app.extensions.knowledge.routers import _can_access_kb
from app.extensions.schemas import CurrentUser


def _make_user(user_id=None, dept_id=None, role_name="user") -> CurrentUser:
    return CurrentUser(
        id=user_id or uuid4(),
        username="test",
        email="test@test.com",
        full_name="Test",
        role_name=role_name,
        dept_id=dept_id,
        status="active",
    )


def _make_kb(owner_id=None, access_type="private", allowed_depts=None):
    """Minimal KB-like object with the fields _can_access_kb checks."""

    class _KB:
        pass

    kb = _KB()
    kb.owner_id = owner_id or uuid4()
    kb.access_type = access_type
    kb.allowed_depts = allowed_depts
    return kb


# ── _can_access_kb unit tests ──────────────────────────────────────────────


class TestCanAccessKb:
    """Test the _can_access_kb visibility check."""

    def test_owner_can_see_private(self):
        uid = uuid4()
        user = _make_user(user_id=uid)
        kb = _make_kb(owner_id=uid, access_type="private")
        assert _can_access_kb(kb, user) is True

    def test_non_owner_cannot_see_private(self):
        user = _make_user()
        kb = _make_kb(owner_id=uuid4(), access_type="private")
        assert _can_access_kb(kb, user) is False

    def test_anyone_can_see_public(self):
        user = _make_user()
        kb = _make_kb(owner_id=uuid4(), access_type="public")
        assert _can_access_kb(kb, user) is True

    def test_same_dept_can_see_dept_kb(self):
        dept_id = uuid4()
        user = _make_user(dept_id=dept_id)
        kb = _make_kb(owner_id=uuid4(), access_type="dept", allowed_depts=[dept_id])
        assert _can_access_kb(kb, user) is True

    def test_different_dept_cannot_see_dept_kb(self):
        user = _make_user(dept_id=uuid4())
        kb = _make_kb(owner_id=uuid4(), access_type="dept", allowed_depts=[uuid4()])
        assert _can_access_kb(kb, user) is False

    def test_no_dept_user_cannot_see_dept_kb(self):
        user = _make_user(dept_id=None)
        kb = _make_kb(owner_id=uuid4(), access_type="dept", allowed_depts=[uuid4()])
        assert _can_access_kb(kb, user) is False

    def test_dept_kb_with_empty_allowed_depts(self):
        user = _make_user(dept_id=uuid4())
        kb = _make_kb(owner_id=uuid4(), access_type="dept", allowed_depts=[])
        assert _can_access_kb(kb, user) is False

    def test_dept_kb_with_none_allowed_depts(self):
        user = _make_user(dept_id=uuid4())
        kb = _make_kb(owner_id=uuid4(), access_type="dept", allowed_depts=None)
        assert _can_access_kb(kb, user) is False

    def test_owner_in_different_dept_can_see_own_dept_kb(self):
        """Owner should always see their own KB regardless of dept settings."""
        uid = uuid4()
        user = _make_user(user_id=uid, dept_id=uuid4())
        kb = _make_kb(owner_id=uid, access_type="dept", allowed_depts=[uuid4()])
        assert _can_access_kb(kb, user) is True

    def test_user_in_multiple_allowed_depts(self):
        dept_a, dept_b = uuid4(), uuid4()
        user = _make_user(dept_id=dept_a)
        kb = _make_kb(owner_id=uuid4(), access_type="dept", allowed_depts=[dept_b, dept_a])
        assert _can_access_kb(kb, user) is True
