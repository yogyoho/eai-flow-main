"""Pure capability tests for the workflow-platform approval projection."""

from __future__ import annotations

from types import SimpleNamespace

from app.auth import Identity
from app.platform_approval import _capabilities


def _identity(*, user_id: str, is_admin: bool = False) -> Identity:
    return Identity(
        user_id=user_id,
        username=user_id,
        display_name=user_id,
        role_code="admin" if is_admin else "sales_rep",
        sales_role="sales_admin" if is_admin else "sales_rep",
        is_admin=is_admin,
    )


def _request(*, status: str = "returned", requested_by: str = "applicant") -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        engine="workflow_platform",
        requested_by=requested_by,
        steps=[],
    )


def test_resubmit_is_reserved_for_the_applicant() -> None:
    request = _request()
    assert _capabilities(request, _identity(user_id="applicant"))["can_resubmit"] is True


def test_admin_cannot_resubmit_someone_elses_returned_request() -> None:
    request = _request()
    capabilities = _capabilities(request, _identity(user_id="admin", is_admin=True))
    assert capabilities["can_resubmit"] is False


def test_admin_who_owns_the_request_can_resubmit() -> None:
    request = _request(requested_by="admin")
    capabilities = _capabilities(request, _identity(user_id="admin", is_admin=True))
    assert capabilities["can_resubmit"] is True


def test_running_request_cannot_resubmit() -> None:
    request = _request(status="running")
    assert _capabilities(request, _identity(user_id="applicant"))["can_resubmit"] is False
