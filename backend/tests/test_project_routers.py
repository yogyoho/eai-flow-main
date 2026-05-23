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
    """Create a mock CurrentUser with superadmin-like role."""
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


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)

    mock_user = _make_user()
    mock_db = AsyncMock()

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
        from app.extensions.project.schemas import ProjectListItem, ProjectListResponse

        uid = uuid4()
        items = [ProjectListItem(id=uid, name="Test", report_type="other")]
        resp = ProjectListResponse(items=items, total=1)

        with patch("app.extensions.project.service.list_projects", new_callable=AsyncMock, return_value=(items, 1)):
            response = client.get("/api/extensions/project/projects")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_passes_filter_params(self, client):
        with patch("app.extensions.project.service.list_projects", new_callable=AsyncMock, return_value=([], 0)) as mock:
            response = client.get(
                "/api/extensions/project/projects?status=writing&report_type=other&search=test&skip=5&limit=10",
            )
            assert response.status_code == 200
            call_kwargs = mock.call_args[1]
            assert call_kwargs["status"] == "writing"
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
        project = ProjectOut(id=pid, name="Updated", report_type="other", status="writing")
        with patch("app.extensions.project.service.update_project", new_callable=AsyncMock, return_value=project):
            response = client.patch(
                f"/api/extensions/project/projects/{pid}",
                json={"status": "writing"},
            )

        assert response.status_code == 200

    def test_returns_404_for_missing(self, client):
        pid = uuid4()
        with patch("app.extensions.project.service.update_project", new_callable=AsyncMock, return_value=None):
            response = client.patch(
                f"/api/extensions/project/projects/{pid}",
                json={"status": "writing"},
            )

        assert response.status_code == 404


# ── DELETE /projects/{id} ──


class TestDeleteProject:
    def test_deletes_existing(self, client):
        pid = uuid4()
        with patch("app.extensions.project.service.delete_project", new_callable=AsyncMock, return_value=True):
            response = client.delete(f"/api/extensions/project/projects/{pid}")

        assert response.status_code == 204

    def test_returns_404_for_missing(self, client):
        pid = uuid4()
        with patch("app.extensions.project.service.delete_project", new_callable=AsyncMock, return_value=False):
            response = client.delete(f"/api/extensions/project/projects/{pid}")

        assert response.status_code == 404


# ── GET /projects/{id}/outline ──


class TestGetOutline:
    def test_returns_outline(self, client):
        from app.extensions.project.schemas import ChapterOut

        pid = uuid4()
        chapters = [ChapterOut(id=uuid4(), project_id=pid, title="Ch1")]
        with patch("app.extensions.project.service.get_outline_tree", new_callable=AsyncMock, return_value=chapters):
            response = client.get(f"/api/extensions/project/projects/{pid}/outline")

        assert response.status_code == 200
        assert len(response.json()) == 1


# ── PUT /projects/{id}/outline ──


class TestReplaceOutline:
    def test_replaces_outline(self, client):
        from app.extensions.project.schemas import ChapterOut

        pid = uuid4()
        chapters = [ChapterOut(id=uuid4(), project_id=pid, title="New Ch")]
        with patch("app.extensions.project.service.replace_outline", new_callable=AsyncMock, return_value=chapters):
            response = client.put(
                f"/api/extensions/project/projects/{pid}/outline",
                json={"chapters": [{"title": "New Ch"}]},
            )

        assert response.status_code == 200


# ── POST /projects/{id}/confirm-outline ──


class TestConfirmOutline:
    def test_confirms_outline(self, client):
        from app.extensions.project.schemas import ProjectOut

        pid = uuid4()
        project = ProjectOut(id=pid, name="Test", report_type="other", status="writing", current_stage=3)
        with patch("app.extensions.project.service.confirm_outline", new_callable=AsyncMock, return_value=project):
            response = client.post(f"/api/extensions/project/projects/{pid}/confirm-outline")

        assert response.status_code == 200
        assert response.json()["status"] == "writing"

    def test_returns_404_for_missing(self, client):
        pid = uuid4()
        with patch("app.extensions.project.service.confirm_outline", new_callable=AsyncMock, return_value=None):
            response = client.post(f"/api/extensions/project/projects/{pid}/confirm-outline")

        assert response.status_code == 404


# ── POST /projects/{id}/members ──


class TestAddMember:
    def test_adds_member(self, client):
        pid = uuid4()
        uid = uuid4()
        with patch("app.extensions.project.service.add_member", new_callable=AsyncMock, return_value=True):
            response = client.post(
                f"/api/extensions/project/projects/{pid}/members",
                json={"user_id": str(uid), "role": "editor"},
            )

        assert response.status_code == 204

    def test_returns_404_for_missing_project(self, client):
        pid = uuid4()
        uid = uuid4()
        with patch("app.extensions.project.service.add_member", new_callable=AsyncMock, return_value=False):
            response = client.post(
                f"/api/extensions/project/projects/{pid}/members",
                json={"user_id": str(uid), "role": "editor"},
            )

        assert response.status_code == 404


# ── DELETE /projects/{id}/members/{user_id} ──


class TestRemoveMember:
    def test_removes_member(self, client):
        pid = uuid4()
        uid = uuid4()
        with patch("app.extensions.project.service.remove_member", new_callable=AsyncMock, return_value=True):
            response = client.delete(f"/api/extensions/project/projects/{pid}/members/{uid}")

        assert response.status_code == 204

    def test_returns_404_for_missing(self, client):
        pid = uuid4()
        uid = uuid4()
        with patch("app.extensions.project.service.remove_member", new_callable=AsyncMock, return_value=False):
            response = client.delete(f"/api/extensions/project/projects/{pid}/members/{uid}")

        assert response.status_code == 404
