"""Tests for project FastAPI routers: endpoint wiring and status codes."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.extensions.auth.middleware import get_current_user
from app.extensions.database import get_db
from app.extensions.project.routers import router
from app.extensions.schemas import CurrentUser


def _make_user():
    user = MagicMock(spec=CurrentUser)
    user.id = uuid4()
    user.username = "testuser"
    user.email = "test@example.com"
    user.full_name = "Test User"
    user.role_id = uuid4()
    user.role_name = "Super Admin"
    user.dept_id = None
    user.dept_name = None
    user.status = "active"
    return user


def _make_admin_role():
    role = MagicMock()
    role.is_system = True
    role.permissions = ["*"]
    return role


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)

    mock_user = _make_user()
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=_make_admin_role())

    async def _override_get_current_user():
        return mock_user

    async def _override_get_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = _override_get_current_user
    app.dependency_overrides[get_db] = _override_get_db

    tc = TestClient(app, raise_server_exceptions=False)
    tc._mock_db = mock_db
    tc._mock_user = mock_user
    return tc


# ── GET /projects ──


class TestListProjects:
    def test_returns_paginated_response(self, client):
        from app.extensions.project.schemas import ProjectListItem

        uid = uuid4()
        items = [ProjectListItem(id=uid, name="Test", report_type="other")]

        with patch("app.extensions.project.service.list_projects", new_callable=AsyncMock, return_value=(items, 1)):
            response = client.get("/api/extensions/project/projects")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_passes_filter_params(self, client):
        with patch("app.extensions.project.service.list_projects", new_callable=AsyncMock, return_value=([], 0)) as mock:
            response = client.get(
                "/api/extensions/project/projects?status=active&report_type=other&search=test&skip=5&limit=10",
            )
            assert response.status_code == 200
            call_kwargs = mock.call_args[1]
            assert call_kwargs["status"] == "active"
            assert call_kwargs["report_type"] == "other"
            assert call_kwargs["search"] == "test"
            assert call_kwargs["skip"] == 5
            assert call_kwargs["limit"] == 10


# ── GET /projects/{id} ──


class TestGetProject:
    def test_returns_project(self, client):
        from app.extensions.project.schemas import ProjectOut

        pid = uuid4()
        project = ProjectOut(id=pid, name="Test", report_type="other")
        with patch("app.extensions.project.service.get_project", new_callable=AsyncMock, return_value=project):
            response = client.get(f"/api/extensions/project/projects/{pid}")

        assert response.status_code == 200
        assert response.json()["id"] == str(pid)

    def test_returns_404_for_missing(self, client):
        pid = uuid4()
        with patch("app.extensions.project.service.get_project", new_callable=AsyncMock, return_value=None):
            response = client.get(f"/api/extensions/project/projects/{pid}")

        assert response.status_code == 404


# ── POST /projects ──


class TestCreateProject:
    def test_creates_project(self, client):
        from app.extensions.project.schemas import ProjectOut

        pid = uuid4()
        project = ProjectOut(id=pid, name="New", report_type="other")
        with patch("app.extensions.project.service.create_project", new_callable=AsyncMock, return_value=project):
            response = client.post(
                "/api/extensions/project/projects",
                json={"name": "New", "report_type": "other"},
            )

        assert response.status_code == 201
        assert response.json()["id"] == str(pid)


# ── PATCH /projects/{id} ──


class TestUpdateProject:
    def test_updates_project(self, client):
        from app.extensions.project.schemas import ProjectOut

        pid = uuid4()
        project = ProjectOut(id=pid, name="Updated", report_type="other", status="completed")
        with patch("app.extensions.project.permissions.get_project_role", new_callable=AsyncMock, return_value="owner"), \
             patch("app.extensions.project.service.update_project", new_callable=AsyncMock, return_value=project):
            response = client.patch(
                f"/api/extensions/project/projects/{pid}",
                json={"status": "completed"},
            )

        assert response.status_code == 200

    def test_returns_404_for_missing(self, client):
        pid = uuid4()
        with patch("app.extensions.project.permissions.get_project_role", new_callable=AsyncMock, return_value="owner"), \
             patch("app.extensions.project.service.update_project", new_callable=AsyncMock, return_value=None):
            response = client.patch(
                f"/api/extensions/project/projects/{pid}",
                json={"status": "completed"},
            )

        assert response.status_code == 404


# ── DELETE /projects/{id} ──


class TestDeleteProject:
    def test_deletes_existing(self, client):
        pid = uuid4()
        with patch("app.extensions.project.permissions.get_project_role", new_callable=AsyncMock, return_value="owner"), \
             patch("app.extensions.project.service.delete_project", new_callable=AsyncMock, return_value=True):
            response = client.delete(f"/api/extensions/project/projects/{pid}")

        assert response.status_code == 204

    def test_returns_404_for_missing(self, client):
        pid = uuid4()
        with patch("app.extensions.project.permissions.get_project_role", new_callable=AsyncMock, return_value="owner"), \
             patch("app.extensions.project.service.delete_project", new_callable=AsyncMock, return_value=False):
            response = client.delete(f"/api/extensions/project/projects/{pid}")

        assert response.status_code == 404


# ── POST /projects/{id}/enter ──


class TestEnterProject:
    def test_enters_project_and_returns_thread(self, client):
        pid = uuid4()
        tid = str(uuid4())
        with patch("app.extensions.project.service.enter_project", new_callable=AsyncMock, return_value={"thread_id": tid, "project_id": str(pid)}):
            response = client.post(f"/api/extensions/project/projects/{pid}/enter")

        assert response.status_code == 200
        data = response.json()
        assert data["thread_id"] == tid
        assert data["project_id"] == str(pid)

    def test_returns_403_for_non_member(self, client):
        pid = uuid4()
        with patch("app.extensions.project.service.enter_project", new_callable=AsyncMock, side_effect=ValueError("Not a project member")):
            response = client.post(f"/api/extensions/project/projects/{pid}/enter")

        assert response.status_code == 403

    def test_returns_403_for_project_not_found(self, client):
        pid = uuid4()
        with patch("app.extensions.project.service.enter_project", new_callable=AsyncMock, side_effect=ValueError("Project not found")):
            response = client.post(f"/api/extensions/project/projects/{pid}/enter")

        assert response.status_code == 403


# ── GET /projects/{id}/files ──


class TestGetProjectFiles:
    def test_returns_aggregated_files(self, client):
        pid = uuid4()
        files = [{"name": "report.docx", "thread_id": "t1", "member": "alice"}]
        with patch("app.extensions.project.service.get_project_files", new_callable=AsyncMock, return_value=files):
            response = client.get(f"/api/extensions/project/projects/{pid}/files")

        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["name"] == "report.docx"

    def test_returns_empty_for_no_files(self, client):
        pid = uuid4()
        with patch("app.extensions.project.service.get_project_files", new_callable=AsyncMock, return_value=[]):
            response = client.get(f"/api/extensions/project/projects/{pid}/files")

        assert response.status_code == 200
        assert response.json() == []


# ── POST /projects/{id}/members ──


class TestAddMember:
    def test_adds_member(self, client):
        pid = uuid4()
        uid = uuid4()
        with patch("app.extensions.project.permissions.get_project_role", new_callable=AsyncMock, return_value="owner"), \
             patch("app.extensions.project.service.add_member", new_callable=AsyncMock, return_value=True):
            response = client.post(
                f"/api/extensions/project/projects/{pid}/members",
                json={"user_id": str(uid), "role": "member"},
            )

        assert response.status_code == 204

    def test_returns_404_for_missing_project(self, client):
        pid = uuid4()
        uid = uuid4()
        with patch("app.extensions.project.permissions.get_project_role", new_callable=AsyncMock, return_value="owner"), \
             patch("app.extensions.project.service.add_member", new_callable=AsyncMock, return_value=False):
            response = client.post(
                f"/api/extensions/project/projects/{pid}/members",
                json={"user_id": str(uid), "role": "member"},
            )

        assert response.status_code == 404


# ── DELETE /projects/{id}/members/{user_id} ──


class TestRemoveMember:
    def test_removes_member(self, client):
        pid = uuid4()
        uid = uuid4()
        with patch("app.extensions.project.permissions.get_project_role", new_callable=AsyncMock, return_value="owner"), \
             patch("app.extensions.project.service.remove_member", new_callable=AsyncMock, return_value=True):
            response = client.delete(f"/api/extensions/project/projects/{pid}/members/{uid}")

        assert response.status_code == 204

    def test_returns_404_for_missing(self, client):
        pid = uuid4()
        uid = uuid4()
        with patch("app.extensions.project.permissions.get_project_role", new_callable=AsyncMock, return_value="owner"), \
             patch("app.extensions.project.service.remove_member", new_callable=AsyncMock, return_value=False):
            response = client.delete(f"/api/extensions/project/projects/{pid}/members/{uid}")

        assert response.status_code == 404


# ── Permission denial tests ──


class TestPermissionDenied:
    """Verify endpoints return 403 when user is not a project member."""

    def _make_non_admin_setup(self, client):
        non_admin_role = MagicMock()
        non_admin_role.is_system = False
        non_admin_role.permissions = ["system:access"]
        client._mock_db.get = AsyncMock(return_value=non_admin_role)

    def test_update_project_denied(self, client):
        pid = uuid4()
        self._make_non_admin_setup(client)
        with patch("app.extensions.project.permissions.get_project_role", new_callable=AsyncMock, return_value=None):
            response = client.patch(f"/api/extensions/project/projects/{pid}", json={"status": "completed"})
        assert response.status_code == 403

    def test_delete_project_denied(self, client):
        pid = uuid4()
        self._make_non_admin_setup(client)
        with patch("app.extensions.project.permissions.get_project_role", new_callable=AsyncMock, return_value=None):
            response = client.delete(f"/api/extensions/project/projects/{pid}")
        assert response.status_code == 403

    def test_add_member_denied(self, client):
        pid = uuid4()
        uid = uuid4()
        self._make_non_admin_setup(client)
        with patch("app.extensions.project.permissions.get_project_role", new_callable=AsyncMock, return_value=None):
            response = client.post(
                f"/api/extensions/project/projects/{pid}/members",
                json={"user_id": str(uid), "role": "member"},
            )
        assert response.status_code == 403

    def test_remove_member_denied(self, client):
        pid = uuid4()
        uid = uuid4()
        self._make_non_admin_setup(client)
        with patch("app.extensions.project.permissions.get_project_role", new_callable=AsyncMock, return_value=None):
            response = client.delete(f"/api/extensions/project/projects/{pid}/members/{uid}")
        assert response.status_code == 403

    def test_member_cannot_delete_project(self, client):
        pid = uuid4()
        self._make_non_admin_setup(client)
        with patch("app.extensions.project.permissions.get_project_role", new_callable=AsyncMock, return_value="member"):
            response = client.delete(f"/api/extensions/project/projects/{pid}")
        assert response.status_code == 403

    def test_member_cannot_add_members(self, client):
        pid = uuid4()
        uid = uuid4()
        self._make_non_admin_setup(client)
        with patch("app.extensions.project.permissions.get_project_role", new_callable=AsyncMock, return_value="member"):
            response = client.post(
                f"/api/extensions/project/projects/{pid}/members",
                json={"user_id": str(uid), "role": "member"},
            )
        assert response.status_code == 403


# ── Role-based access tests ──


class TestRoleBasedAccess:
    """Verify owner and member roles access their permitted endpoints."""

    def test_member_can_review_approval(self, client):
        pid = uuid4()
        wid = uuid4()
        with patch("app.extensions.project.permissions.get_project_role", new_callable=AsyncMock, return_value="member"), \
             patch("app.extensions.project.service.approval_action", new_callable=AsyncMock, return_value={"status": "approved"}):
            response = client.post(
                f"/api/extensions/project/projects/{pid}/approval-action",
                json={"workflow_id": str(wid), "action": "approve"},
            )
        assert response.status_code == 410  # endpoint deprecated — returns 410 Gone

    def test_member_can_view_approval_status(self, client):
        pid = uuid4()
        with patch("app.extensions.project.permissions.get_project_role", new_callable=AsyncMock, return_value="member"), \
             patch("app.extensions.project.service.get_approval_status", new_callable=AsyncMock, return_value={"project_id": str(pid), "current_step": None, "total_steps": 0, "steps": [], "all_approved": False}):
            response = client.get(f"/api/extensions/project/projects/{pid}/approval-status")
        assert response.status_code == 410  # endpoint deprecated — returns 410 Gone

    def test_member_cannot_submit_approval(self, client):
        pid = uuid4()
        non_admin_role = MagicMock()
        non_admin_role.is_system = False
        non_admin_role.permissions = ["system:access"]
        client._mock_db.get = AsyncMock(return_value=non_admin_role)
        with patch("app.extensions.project.permissions.get_project_role", new_callable=AsyncMock, return_value="member"):
            response = client.post(
                f"/api/extensions/project/projects/{pid}/submit-approval",
                json={"steps": []},
            )
        assert response.status_code == 403

    def test_owner_can_submit_approval(self, client):
        pid = uuid4()
        with patch("app.extensions.project.permissions.get_project_role", new_callable=AsyncMock, return_value="owner"), \
             patch("app.extensions.project.service.submit_approval", new_callable=AsyncMock, return_value={"project_id": str(pid), "status": "approval", "step_count": 1}):
            response = client.post(
                f"/api/extensions/project/projects/{pid}/submit-approval",
                json={"steps": [{"step_order": 1, "step_name": "Review", "reviewer_id": str(uuid4())}]},
            )
        assert response.status_code == 410  # endpoint deprecated — returns 410 Gone
