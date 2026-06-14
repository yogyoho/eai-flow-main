"""Tests for enter_project and get_project_files service functions."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


@pytest.fixture
def mock_db():
    db = AsyncMock()
    return db


@pytest.fixture
def project_id():
    return uuid4()


@pytest.fixture
def user_id():
    return uuid4()


class TestEnterProject:
    @pytest.mark.asyncio
    async def test_creates_thread_for_member_without_thread(self, mock_db, project_id, user_id):
        """When member exists but has no thread_id, create one."""
        tid = str(uuid4())
        mock_project = MagicMock()
        mock_project.id = project_id
        mock_project.template_id = None
        mock_project.report_type = "environmental_impact"
        mock_project.name = "环评报告"

        mock_member = MagicMock()
        mock_member.thread_id = None
        mock_member.user_id = user_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [mock_project, mock_member]
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.extensions.project.service._create_deerflow_thread", new_callable=AsyncMock, return_value=tid) as mock_create, \
             patch("app.extensions.project.service._write_project_context") as mock_write:
            from app.extensions.project.service import enter_project

            result = await enter_project(mock_db, project_id, user_id)

        mock_create.assert_called_once()
        metadata = mock_create.call_args[0][0]
        assert metadata["project_id"] == str(project_id)
        assert metadata["type"] == "report_project"
        assert metadata["report_type"] == "environmental_impact"
        assert metadata["project_name"] == "环评报告"
        assert metadata["template"] == {}

        mock_write.assert_called_once_with(tid, str(user_id), metadata)

        assert result["thread_id"] == tid
        assert result["project_id"] == str(project_id)
        assert mock_member.thread_id == tid

    @pytest.mark.asyncio
    async def test_returns_existing_thread(self, mock_db, project_id, user_id):
        """When member already has a thread_id, return it without creating."""
        existing_tid = str(uuid4())

        mock_project = MagicMock()
        mock_project.id = project_id

        mock_member = MagicMock()
        mock_member.thread_id = existing_tid
        mock_member.user_id = user_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [mock_project, mock_member]
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.extensions.project.service._create_deerflow_thread", new_callable=AsyncMock) as mock_create:
            from app.extensions.project.service import enter_project

            result = await enter_project(mock_db, project_id, user_id)

        mock_create.assert_not_called()
        assert result["thread_id"] == existing_tid
        assert result["project_id"] == str(project_id)

    @pytest.mark.asyncio
    async def test_raises_for_non_member(self, mock_db, project_id, user_id):
        """When user is not a project member, raise ValueError."""
        mock_project = MagicMock()
        mock_project.id = project_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [mock_project, None]
        mock_db.execute = AsyncMock(return_value=mock_result)

        from app.extensions.project.service import enter_project

        with pytest.raises(ValueError, match="Not a project member"):
            await enter_project(mock_db, project_id, user_id)

    @pytest.mark.asyncio
    async def test_raises_for_project_not_found(self, mock_db, project_id, user_id):
        """When project doesn't exist, raise ValueError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        from app.extensions.project.service import enter_project

        with pytest.raises(ValueError, match="Project not found"):
            await enter_project(mock_db, project_id, user_id)

    @pytest.mark.asyncio
    async def test_injects_template_context(self, mock_db, project_id, user_id):
        """When project has template_id, inject template context into metadata."""
        tid = str(uuid4())
        template_id = uuid4()

        mock_project = MagicMock()
        mock_project.id = project_id
        mock_project.template_id = template_id
        mock_project.report_type = "environmental_impact"
        mock_project.name = "环评报告"

        mock_member = MagicMock()
        mock_member.thread_id = None
        mock_member.user_id = user_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [mock_project, mock_member]
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_template = MagicMock()
        mock_template.name = "环评模板v1"
        mock_template.domain = "environmental"
        mock_template.root_sections_json = {"sections": [{"title": "概述"}]}
        mock_db.get = AsyncMock(return_value=mock_template)

        with patch("app.extensions.project.service._create_deerflow_thread", new_callable=AsyncMock, return_value=tid) as mock_create, \
             patch("app.extensions.project.service._write_project_context"):
            from app.extensions.project.service import enter_project

            result = await enter_project(mock_db, project_id, user_id)

        metadata = mock_create.call_args[0][0]
        assert metadata["template"]["template_name"] == "环评模板v1"
        assert metadata["template"]["domain"] == "environmental"
        assert metadata["template"]["sections"]["sections"][0]["title"] == "概述"

    @pytest.mark.asyncio
    async def test_passes_cookies_to_thread_creation(self, mock_db, project_id, user_id):
        """Cookies and CSRF token should be forwarded to _create_deerflow_thread."""
        tid = str(uuid4())
        cookies = {"access_token": "jwt-token"}
        csrf_token = "csrf-abc"

        mock_project = MagicMock()
        mock_project.id = project_id
        mock_project.template_id = None
        mock_project.report_type = "other"
        mock_project.name = "Test"

        mock_member = MagicMock()
        mock_member.thread_id = None
        mock_member.user_id = user_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [mock_project, mock_member]
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.extensions.project.service._create_deerflow_thread", new_callable=AsyncMock, return_value=tid) as mock_create, \
             patch("app.extensions.project.service._write_project_context"):
            from app.extensions.project.service import enter_project

            await enter_project(mock_db, project_id, user_id, cookies=cookies, csrf_token=csrf_token)

        assert mock_create.call_args.kwargs["cookies"] == cookies
        assert mock_create.call_args.kwargs["csrf_token"] == csrf_token

    @pytest.mark.asyncio
    async def test_handles_missing_template_gracefully(self, mock_db, project_id, user_id):
        """When template_id is set but template not found in DB, use empty context."""
        tid = str(uuid4())
        template_id = uuid4()

        mock_project = MagicMock()
        mock_project.id = project_id
        mock_project.template_id = template_id
        mock_project.report_type = "other"
        mock_project.name = "Test"

        mock_member = MagicMock()
        mock_member.thread_id = None
        mock_member.user_id = user_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [mock_project, mock_member]
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.get = AsyncMock(return_value=None)

        with patch("app.extensions.project.service._create_deerflow_thread", new_callable=AsyncMock, return_value=tid) as mock_create, \
             patch("app.extensions.project.service._write_project_context"):
            from app.extensions.project.service import enter_project

            result = await enter_project(mock_db, project_id, user_id)

        metadata = mock_create.call_args[0][0]
        assert metadata["template"] == {}


class TestGetProjectFiles:
    @pytest.mark.asyncio
    async def test_skips_members_without_thread(self, mock_db, project_id):
        """Members without thread_id should be skipped."""
        member = MagicMock()
        member.thread_id = None
        member.user_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [member]
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            from app.extensions.project.service import get_project_files

            result = await get_project_files(mock_db, project_id)

        assert result == []
        mock_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_api_failure_gracefully(self, mock_db, project_id):
        """Failed API calls should be silently skipped."""
        member = MagicMock()
        member.thread_id = "thread-1"
        member.user_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [member]
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.extensions.project.service._resolve_username", return_value="alice"), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            from app.extensions.project.service import get_project_files

            result = await get_project_files(mock_db, project_id)

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_members(self, mock_db, project_id):
        """Project with no members returns empty list."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        from app.extensions.project.service import get_project_files

        result = await get_project_files(mock_db, project_id)
        assert result == []

    @pytest.mark.asyncio
    async def test_aggregates_files_from_multiple_threads(self, mock_db, project_id):
        """Should collect files from all member threads and tag with member info."""
        member1 = MagicMock()
        member1.thread_id = "thread-1"
        member1.user_id = uuid4()

        member2 = MagicMock()
        member2.thread_id = "thread-2"
        member2.user_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [member1, member2]
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.extensions.project.service._resolve_username", side_effect=lambda db, uid: "alice" if uid == member1.user_id else "bob"), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_response1 = MagicMock()
            mock_response1.status_code = 200
            mock_response1.json.return_value = {"files": [{"name": "report1.docx", "size": 1024}]}

            mock_response2 = MagicMock()
            mock_response2.status_code = 200
            mock_response2.json.return_value = {"files": [{"name": "report2.docx", "size": 2048}]}

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=[mock_response1, mock_response2])
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            from app.extensions.project.service import get_project_files

            result = await get_project_files(mock_db, project_id)

        assert len(result) == 2
        assert result[0]["name"] == "report1.docx"
        assert result[0]["thread_id"] == "thread-1"
        assert result[0]["member"] == "alice"
        assert result[1]["name"] == "report2.docx"
        assert result[1]["thread_id"] == "thread-2"
        assert result[1]["member"] == "bob"

    @pytest.mark.asyncio
    async def test_skips_non_200_responses(self, mock_db, project_id):
        """Non-200 API responses should be silently skipped."""
        member = MagicMock()
        member.thread_id = "thread-1"
        member.user_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [member]
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.extensions.project.service._resolve_username", return_value="alice"), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_response = MagicMock()
            mock_response.status_code = 404

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            from app.extensions.project.service import get_project_files

            result = await get_project_files(mock_db, project_id)

        assert result == []


class TestWriteProjectContext:
    def test_writes_json_to_thread_dir(self):
        """_write_project_context creates project-context.json in thread directory."""
        from app.extensions.project.service import _write_project_context

        with TemporaryDirectory() as tmpdir:
            metadata = {
                "project_id": "test-123",
                "type": "report_project",
                "report_type": "environmental_impact",
                "project_name": "环评报告",
                "template": {"template_name": "模板v1"},
            }

            with patch("deerflow.config.paths.get_paths") as mock_paths:
                mock_p = MagicMock()
                mock_p.thread_dir.return_value = Path(tmpdir) / "users" / "uid1" / "threads" / "tid1"
                mock_paths.return_value = mock_p

                _write_project_context("tid1", "uid1", metadata)

            context_file = Path(tmpdir) / "users" / "uid1" / "threads" / "tid1" / "project-context.json"
            assert context_file.exists()
            data = json.loads(context_file.read_text())
            assert data["project_id"] == "test-123"
            assert data["project_name"] == "环评报告"


class TestCreateProjectOwnerMembership:
    """DF-3 regression: the project creator must always be a project_member
    (role=owner), even when the creation wizard passes an explicit members list
    that includes the owner. Previously the creator was dropped (403 on access)."""

    @pytest.mark.asyncio
    async def test_creator_owner_when_members_provided(self, mock_db):
        from app.extensions.project import service as svc

        creator = uuid4()
        zhangsan = uuid4()
        wanger = uuid4()
        added: list = []
        mock_db.add = MagicMock(side_effect=lambda obj: added.append(obj))
        mock_db.flush = AsyncMock()

        with patch("app.extensions.project.service.get_project", new_callable=AsyncMock, return_value={"id": "p1"}):
            await svc.create_project(
                mock_db,
                name="辽阳石化消防设计专篇",
                report_type="fire_protection_design",
                created_by=creator,
                members_data=[
                    {"user_id": creator, "role": "owner"},
                    {"user_id": zhangsan, "role": "member"},
                    {"user_id": wanger, "role": "member"},
                ],
            )

        members = [o for o in added if isinstance(o, svc.ProjectMember)]
        owner_rows = [m for m in members if m.user_id == creator]
        assert len(owner_rows) == 1, "creator must be added exactly once as owner"
        assert owner_rows[0].role == "owner"
        assert {m.user_id for m in members} == {creator, zhangsan, wanger}

    @pytest.mark.asyncio
    async def test_creator_owner_without_members(self, mock_db):
        """Backward-compat: creator is owner when no members supplied."""
        from app.extensions.project import service as svc

        creator = uuid4()
        added: list = []
        mock_db.add = MagicMock(side_effect=lambda obj: added.append(obj))
        mock_db.flush = AsyncMock()

        with patch("app.extensions.project.service.get_project", new_callable=AsyncMock, return_value={"id": "p2"}):
            await svc.create_project(
                mock_db,
                name="P",
                report_type="fire_protection_design",
                created_by=creator,
            )

        members = [o for o in added if isinstance(o, svc.ProjectMember)]
        assert len(members) == 1
        assert members[0].user_id == creator and members[0].role == "owner"
