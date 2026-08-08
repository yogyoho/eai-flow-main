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
        mock_result.scalar_one_or_none.return_value = mock_project
        mock_result.scalars.return_value.first.return_value = mock_member
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
        mock_result.scalar_one_or_none.return_value = mock_project
        mock_result.scalars.return_value.first.return_value = mock_member
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.extensions.project.service._create_deerflow_thread", new_callable=AsyncMock) as mock_create, \
             patch("app.extensions.project.service._write_project_context"):
            from app.extensions.project.service import enter_project

            result = await enter_project(mock_db, project_id, user_id)

        mock_create.assert_not_called()
        assert result["thread_id"] == existing_tid
        assert result["project_id"] == str(project_id)

    @pytest.mark.asyncio
    async def test_refreshes_context_on_reentry(self, mock_db, project_id, user_id):
        """Re-entering an existing project thread must refresh project-context.json
        with the current project/template data, so edits made after the first
        conversation creation still reach the agent on the next new conversation
        (the middleware freezes the snapshot into the first HumanMessage, so the
        file must be up-to-date before that first turn runs)."""
        existing_tid = str(uuid4())
        template_id = uuid4()

        mock_project = MagicMock()
        mock_project.id = project_id
        mock_project.template_id = template_id
        mock_project.report_type = "fire_protection_design"
        mock_project.name = "抚顺消防专篇（已改名）"

        mock_member = MagicMock()
        mock_member.thread_id = existing_tid
        mock_member.user_id = user_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project
        mock_result.scalars.return_value.first.return_value = mock_member
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_template = MagicMock()
        mock_template.name = "消防模板v2"
        mock_template.domain = "fire_protection"
        mock_template.root_sections_json = {"sections": [{"title": "设计依据"}]}
        mock_db.get = AsyncMock(return_value=mock_template)

        with patch("app.extensions.project.service._create_deerflow_thread", new_callable=AsyncMock) as mock_create, \
             patch("app.extensions.project.service._write_project_context") as mock_write:
            from app.extensions.project.service import enter_project

            result = await enter_project(mock_db, project_id, user_id)

        # Reuse the existing thread — do not create a new one.
        mock_create.assert_not_called()
        assert result["thread_id"] == existing_tid
        # Context file must be refreshed with current project/template data.
        mock_write.assert_called_once()
        written_tid, written_uid, metadata = mock_write.call_args[0]
        assert written_tid == existing_tid
        assert written_uid == str(user_id)
        assert metadata["project_name"] == "抚顺消防专篇（已改名）"
        assert metadata["template"]["template_name"] == "消防模板v2"

    @pytest.mark.asyncio
    async def test_raises_for_non_member(self, mock_db, project_id, user_id):
        """When user is not a project member, raise ValueError."""
        mock_project = MagicMock()
        mock_project.id = project_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project
        mock_result.scalars.return_value.first.return_value = None
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
        mock_result.scalar_one_or_none.return_value = mock_project
        mock_result.scalars.return_value.first.return_value = mock_member
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
        mock_result.scalar_one_or_none.return_value = mock_project
        mock_result.scalars.return_value.first.return_value = mock_member
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
        mock_result.scalar_one_or_none.return_value = mock_project
        mock_result.scalars.return_value.first.return_value = mock_member
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
    async def test_delegates_to_list_project_outputs(self, mock_db, project_id):
        """get_project_files 复用 AIDocumentService.list_project_outputs，返回其 files 列表。"""
        caller = uuid4()
        files = [{"name": "消防设计专篇.md", "thread_id": "T1", "member": "lisi"}]
        with patch(
            "app.extensions.docmgr.service.AIDocumentService.list_project_outputs",
            new=AsyncMock(return_value={"files": files, "total": 1}),
        ) as mock_list:
            from app.extensions.project.service import get_project_files

            result = await get_project_files(mock_db, project_id, caller_user_id=caller)
        assert result == files
        mock_list.assert_awaited_once_with(mock_db, project_id, caller)


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
                    {"user_id": zhangsan, "role": "writer"},  # EAI-CUSTOM: canonical (ADR P5)
                    {"user_id": wanger, "role": "writer"},  # EAI-CUSTOM: canonical (ADR P5)
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
