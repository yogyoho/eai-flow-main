"""Tests for the collaboration module: schemas, service logic, and router endpoints."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.extensions.auth.middleware import get_current_user
from app.extensions.database import get_db
from app.extensions.docmgr.collab_routers import router
from app.extensions.schemas import CurrentUser


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_user() -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        username="testuser",
        email="test@example.com",
        full_name="Test User",
        status="active",
    )


def _make_app() -> tuple[TestClient, CurrentUser, AsyncMock]:
    """Create a test app with dependency overrides for auth and DB."""
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
    return tc, mock_user, mock_db


# ── 1. Schema validation tests ──────────────────────────────────────────────


class TestCollabSchemas:
    """Pydantic schema validation for collaboration request/response models."""

    def test_comment_create_request_valid(self):
        from app.extensions.docmgr.collab_schemas import CommentCreateRequest

        req = CommentCreateRequest(block_id="block-1", content="Hello world")
        assert req.block_id == "block-1"
        assert req.content == "Hello world"
        assert req.parent_id is None

    def test_comment_create_request_with_parent(self):
        from app.extensions.docmgr.collab_schemas import CommentCreateRequest

        parent = uuid4()
        req = CommentCreateRequest(block_id="block-2", content="Reply", parent_id=parent)
        assert req.parent_id == parent

    def test_comment_create_request_empty_block_id_fails(self):
        from app.extensions.docmgr.collab_schemas import CommentCreateRequest

        with pytest.raises(ValidationError):
            CommentCreateRequest(block_id="", content="Hello")

    def test_comment_create_request_empty_content_fails(self):
        from app.extensions.docmgr.collab_schemas import CommentCreateRequest

        with pytest.raises(ValidationError):
            CommentCreateRequest(block_id="block-1", content="")

    def test_comment_update_request_valid(self):
        from app.extensions.docmgr.collab_schemas import CommentUpdateRequest

        req = CommentUpdateRequest(content="Updated text")
        assert req.content == "Updated text"

    def test_comment_update_request_empty_content_fails(self):
        from app.extensions.docmgr.collab_schemas import CommentUpdateRequest

        with pytest.raises(ValidationError):
            CommentUpdateRequest(content="")

    def test_version_create_request_defaults(self):
        from app.extensions.docmgr.collab_schemas import VersionCreateRequest

        req = VersionCreateRequest()
        assert req.summary is None

    def test_version_create_request_with_summary(self):
        from app.extensions.docmgr.collab_schemas import VersionCreateRequest

        req = VersionCreateRequest(summary="Initial draft")
        assert req.summary == "Initial draft"

    def test_version_diff_response_defaults(self):
        from app.extensions.docmgr.collab_schemas import VersionDiffResponse

        res = VersionDiffResponse(from_version=1, to_version=2)
        assert res.diff_blocks == []
        assert res.ai_summary is None
        assert res.from_summary is None
        assert res.to_summary is None

    def test_version_restore_response(self):
        from app.extensions.docmgr.collab_schemas import VersionRestoreResponse

        res = VersionRestoreResponse(version=3, message="Restored to version 3")
        assert res.version == 3
        assert "3" in res.message

    def test_ai_review_request_defaults(self):
        from app.extensions.docmgr.collab_schemas import AIReviewRequest

        req = AIReviewRequest(doc_id=uuid4())
        assert req.review_type == "full"

    def test_ai_review_request_custom_type(self):
        from app.extensions.docmgr.collab_schemas import AIReviewRequest

        req = AIReviewRequest(doc_id=uuid4(), review_type="style")
        assert req.review_type == "style"

    def test_ai_review_comment_defaults(self):
        from app.extensions.docmgr.collab_schemas import AIReviewComment

        c = AIReviewComment(comment="Test issue")
        assert c.block_id is None
        assert c.severity == "info"

    def test_ai_review_comment_with_block(self):
        from app.extensions.docmgr.collab_schemas import AIReviewComment

        c = AIReviewComment(block_id="b-1", comment="Fix this", severity="warning")
        assert c.block_id == "b-1"
        assert c.severity == "warning"

    def test_ai_review_response_defaults(self):
        from app.extensions.docmgr.collab_schemas import AIReviewResponse

        res = AIReviewResponse(review_id="r-1")
        assert res.comments == []
        assert res.overall_score is None
        assert res.summary is None

    def test_ai_review_response_full(self):
        from app.extensions.docmgr.collab_schemas import AIReviewComment, AIReviewResponse

        res = AIReviewResponse(
            review_id="r-2",
            comments=[AIReviewComment(comment="issue")],
            overall_score=85.5,
            summary="Good",
        )
        assert len(res.comments) == 1
        assert res.overall_score == 85.5

    def test_comment_response_fields(self):
        from app.extensions.docmgr.collab_schemas import CommentResponse

        now = datetime.now()
        uid = uuid4()
        did = uuid4()
        res = CommentResponse(
            id=uid,
            doc_id=did,
            block_id="b-1",
            content="hello",
            user_id=uid,
            resolved=False,
            created_at=now,
            updated_at=now,
        )
        assert res.username is None
        assert res.full_name is None

    def test_version_response_fields(self):
        from app.extensions.docmgr.collab_schemas import VersionResponse

        res = VersionResponse(
            id=1,
            doc_id=uuid4(),
            version=1,
            created_at=datetime.now(),
        )
        assert res.summary is None
        assert res.created_by is None


# ── 2. Version service diff logic tests ──────────────────────────────────────


class TestVersionServiceDiff:
    """Test the VersionService.diff_versions static method by mocking DB access."""

    @pytest.fixture()
    def mock_db(self):
        return AsyncMock(spec=AsyncSession)

    @pytest.mark.asyncio
    async def test_diff_detects_added_lines(self, mock_db):
        """Lines in 'to' but not in 'from' appear as 'added' blocks."""
        from app.extensions.docmgr.collab_service import VersionService

        from_snap = b"line A\nline B"
        to_snap = b"line A\nline B\nline C"

        with (
            patch.object(VersionService, "get_version", new_callable=AsyncMock) as mock_get_ver,
            patch.object(VersionService, "get_snapshot", new_callable=AsyncMock) as mock_get_snap,
        ):
            mock_get_ver.side_effect = [
                {"summary": "v1", "created_at": "2026-01-01"},
                {"summary": "v2", "created_at": "2026-01-02"},
            ]
            mock_get_snap.side_effect = [from_snap, to_snap]

            result = await VersionService.diff_versions(mock_db, uuid4(), 1, 2)

        assert result is not None
        assert result["from_version"] == 1
        assert result["to_version"] == 2
        types = [b["type"] for b in result["diff_blocks"]]
        assert "added" in types
        added_contents = [b["content"] for b in result["diff_blocks"] if b["type"] == "added"]
        assert "line C" in added_contents

    @pytest.mark.asyncio
    async def test_diff_detects_removed_lines(self, mock_db):
        """Lines in 'from' but not in 'to' appear as 'removed' blocks."""
        from app.extensions.docmgr.collab_service import VersionService

        from_snap = b"line A\nline B\nline C"
        to_snap = b"line A\nline B"

        with (
            patch.object(VersionService, "get_version", new_callable=AsyncMock) as mock_get_ver,
            patch.object(VersionService, "get_snapshot", new_callable=AsyncMock) as mock_get_snap,
        ):
            mock_get_ver.side_effect = [
                {"summary": None, "created_at": None},
                {"summary": None, "created_at": None},
            ]
            mock_get_snap.side_effect = [from_snap, to_snap]

            result = await VersionService.diff_versions(mock_db, uuid4(), 1, 2)

        removed = [b["content"] for b in result["diff_blocks"] if b["type"] == "removed"]
        assert "line C" in removed

    @pytest.mark.asyncio
    async def test_diff_returns_none_when_version_missing(self, mock_db):
        """If get_version returns None, diff_versions returns None."""
        from app.extensions.docmgr.collab_service import VersionService

        with patch.object(VersionService, "get_version", new_callable=AsyncMock, return_value=None):
            result = await VersionService.diff_versions(mock_db, uuid4(), 1, 2)

        assert result is None

    @pytest.mark.asyncio
    async def test_diff_no_changes_returns_empty_blocks(self, mock_db):
        """Identical snapshots produce no diff blocks."""
        from app.extensions.docmgr.collab_service import VersionService

        snap = b"line A\nline B"
        with (
            patch.object(VersionService, "get_version", new_callable=AsyncMock) as mock_get_ver,
            patch.object(VersionService, "get_snapshot", new_callable=AsyncMock) as mock_get_snap,
        ):
            mock_get_ver.side_effect = [
                {"summary": None, "created_at": None},
                {"summary": None, "created_at": None},
            ]
            mock_get_snap.side_effect = [snap, snap]

            result = await VersionService.diff_versions(mock_db, uuid4(), 1, 2)

        assert result["diff_blocks"] == []

    @pytest.mark.asyncio
    async def test_diff_returns_version_summaries(self, mock_db):
        """Diff result includes summary metadata from both versions."""
        from app.extensions.docmgr.collab_service import VersionService

        with (
            patch.object(VersionService, "get_version", new_callable=AsyncMock) as mock_get_ver,
            patch.object(VersionService, "get_snapshot", new_callable=AsyncMock) as mock_get_snap,
        ):
            mock_get_ver.side_effect = [
                {"summary": "first draft", "created_at": "2026-01-01"},
                {"summary": "revised", "created_at": "2026-01-02"},
            ]
            mock_get_snap.side_effect = [b"a", b"a"]

            result = await VersionService.diff_versions(mock_db, uuid4(), 1, 2)

        assert result["from_summary"] == "first draft"
        assert result["to_summary"] == "revised"

    @pytest.mark.asyncio
    async def test_diff_handles_empty_snapshots(self, mock_db):
        """Empty/None snapshots produce no diff blocks."""
        from app.extensions.docmgr.collab_service import VersionService

        with (
            patch.object(VersionService, "get_version", new_callable=AsyncMock) as mock_get_ver,
            patch.object(VersionService, "get_snapshot", new_callable=AsyncMock) as mock_get_snap,
        ):
            mock_get_ver.side_effect = [
                {"summary": None, "created_at": None},
                {"summary": None, "created_at": None},
            ]
            mock_get_snap.side_effect = [None, None]

            result = await VersionService.diff_versions(mock_db, uuid4(), 1, 2)

        assert result["diff_blocks"] == []

    @pytest.mark.asyncio
    async def test_diff_detects_both_added_and_removed(self, mock_db):
        """Diff correctly identifies simultaneous additions and removals."""
        from app.extensions.docmgr.collab_service import VersionService

        from_snap = b"alpha\nbeta\ngamma"
        to_snap = b"alpha\ndelta\nepsilon"

        with (
            patch.object(VersionService, "get_version", new_callable=AsyncMock) as mock_get_ver,
            patch.object(VersionService, "get_snapshot", new_callable=AsyncMock) as mock_get_snap,
        ):
            mock_get_ver.side_effect = [
                {"summary": None, "created_at": None},
                {"summary": None, "created_at": None},
            ]
            mock_get_snap.side_effect = [from_snap, to_snap]

            result = await VersionService.diff_versions(mock_db, uuid4(), 1, 2)

        added = {b["content"] for b in result["diff_blocks"] if b["type"] == "added"}
        removed = {b["content"] for b in result["diff_blocks"] if b["type"] == "removed"}
        assert added == {"delta", "epsilon"}
        assert removed == {"beta", "gamma"}


# ── 3. Router endpoint tests ────────────────────────────────────────────────


class TestCollabRouters:
    """Test collab router endpoints with mocked dependencies."""

    def test_diff_versions_endpoint_returns_diff(self):
        """GET /documents/{doc_id}/versions/diff calls service and returns result."""
        doc_id = uuid4()
        client, mock_user, mock_db = _make_app()

        mock_result = {
            "from_version": 1,
            "to_version": 2,
            "from_summary": None,
            "to_summary": None,
            "from_created_at": None,
            "to_created_at": None,
            "diff_blocks": [{"type": "added", "content": "new line"}],
            "ai_summary": None,
        }

        with (
            patch("app.extensions.docmgr.collab_routers.AIDocumentService") as mock_doc_svc,
            patch("app.extensions.docmgr.collab_routers.VersionService") as mock_ver_svc,
        ):
            mock_doc_svc.get_by_id = AsyncMock(return_value=MagicMock())
            mock_ver_svc.diff_versions = AsyncMock(return_value=mock_result)

            response = client.get(
                f"/api/extensions/docmgr/documents/{doc_id}/versions/diff?from=1&to=2"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["from_version"] == 1
        assert data["to_version"] == 2
        assert len(data["diff_blocks"]) == 1

    def test_diff_versions_endpoint_404_when_doc_missing(self):
        """Returns 404 when document doesn't exist."""
        doc_id = uuid4()
        client, _, _ = _make_app()

        with patch("app.extensions.docmgr.collab_routers.AIDocumentService") as mock_doc_svc:
            mock_doc_svc.get_by_id = AsyncMock(return_value=None)

            response = client.get(
                f"/api/extensions/docmgr/documents/{doc_id}/versions/diff?from=1&to=2"
            )

        assert response.status_code == 404

    def test_diff_versions_endpoint_404_when_version_missing(self):
        """Returns 404 when one or both versions are not found."""
        doc_id = uuid4()
        client, _, _ = _make_app()

        with (
            patch("app.extensions.docmgr.collab_routers.AIDocumentService") as mock_doc_svc,
            patch("app.extensions.docmgr.collab_routers.VersionService") as mock_ver_svc,
        ):
            mock_doc_svc.get_by_id = AsyncMock(return_value=MagicMock())
            mock_ver_svc.diff_versions = AsyncMock(return_value=None)

            response = client.get(
                f"/api/extensions/docmgr/documents/{doc_id}/versions/diff?from=1&to=2"
            )

        assert response.status_code == 404

    def test_ai_review_endpoint_returns_review(self):
        """POST /documents/ai-review returns AI review result."""
        doc_id = uuid4()
        client, _, _ = _make_app()

        mock_review = {
            "review_id": "r-123",
            "comments": [{"block_id": None, "comment": "Check this", "severity": "warning"}],
            "overall_score": 75.0,
            "summary": "Overall good document",
        }

        with (
            patch("app.extensions.docmgr.collab_routers.AIDocumentService") as mock_doc_svc,
            patch("app.extensions.docmgr.collab_routers.AIReviewService") as mock_ai_svc,
        ):
            mock_doc = MagicMock()
            mock_doc.content = "Test document content"
            mock_doc_svc.get_by_id = AsyncMock(return_value=mock_doc)
            mock_ai_svc.ai_review_document = AsyncMock(return_value=mock_review)

            response = client.post(
                "/api/extensions/docmgr/documents/ai-review",
                json={"doc_id": str(doc_id), "review_type": "full"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["review_id"] == "r-123"
        assert len(data["comments"]) == 1
        assert data["overall_score"] == 75.0

    def test_ai_review_endpoint_404_when_doc_missing(self):
        """Returns 404 when document doesn't exist."""
        doc_id = uuid4()
        client, _, _ = _make_app()

        with patch("app.extensions.docmgr.collab_routers.AIDocumentService") as mock_doc_svc:
            mock_doc_svc.get_by_id = AsyncMock(return_value=None)

            response = client.post(
                "/api/extensions/docmgr/documents/ai-review",
                json={"doc_id": str(doc_id), "review_type": "full"},
            )

        assert response.status_code == 404

    def test_list_comments_endpoint_returns_list(self):
        """GET /documents/{doc_id}/comments returns comment list."""
        doc_id = uuid4()
        client, _, _ = _make_app()
        now = datetime.now().isoformat()

        mock_comments = [
            {
                "id": str(uuid4()),
                "doc_id": str(doc_id),
                "block_id": "b-1",
                "content": "Nice",
                "parent_id": None,
                "user_id": str(uuid4()),
                "resolved": False,
                "created_at": now,
                "updated_at": now,
                "username": "alice",
                "full_name": "Alice",
            }
        ]

        with (
            patch("app.extensions.docmgr.collab_routers.AIDocumentService") as mock_doc_svc,
            patch("app.extensions.docmgr.collab_routers.CommentService") as mock_comment_svc,
        ):
            mock_doc_svc.get_by_id = AsyncMock(return_value=MagicMock())
            mock_comment_svc.list_comments = AsyncMock(return_value=mock_comments)

            response = client.get(f"/api/extensions/docmgr/documents/{doc_id}/comments")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["content"] == "Nice"

    def test_create_comment_endpoint_201(self):
        """POST /documents/{doc_id}/comments returns 201 on success."""
        doc_id = uuid4()
        comment_id = uuid4()
        user_id_obj = uuid4()
        client, mock_user, _ = _make_app()
        now = datetime.now().isoformat()

        mock_created = {
            "id": str(comment_id),
            "doc_id": str(doc_id),
            "block_id": "b-1",
            "content": "Great work",
            "parent_id": None,
            "user_id": str(user_id_obj),
            "resolved": False,
            "created_at": now,
            "updated_at": now,
            "username": "testuser",
            "full_name": "Test User",
        }

        with (
            patch("app.extensions.docmgr.collab_routers.AIDocumentService") as mock_doc_svc,
            patch("app.extensions.docmgr.collab_routers.CommentService") as mock_comment_svc,
        ):
            mock_doc_svc.get_by_id = AsyncMock(return_value=MagicMock())
            mock_comment_svc.create_comment = AsyncMock(return_value=mock_created)

            response = client.post(
                f"/api/extensions/docmgr/documents/{doc_id}/comments",
                json={"block_id": "b-1", "content": "Great work"},
            )

        assert response.status_code == 201
        assert response.json()["content"] == "Great work"

    def test_create_comment_endpoint_404_when_doc_missing(self):
        """POST /documents/{doc_id}/comments returns 404 when doc not found."""
        doc_id = uuid4()
        client, _, _ = _make_app()

        with patch("app.extensions.docmgr.collab_routers.AIDocumentService") as mock_doc_svc:
            mock_doc_svc.get_by_id = AsyncMock(return_value=None)

            response = client.post(
                f"/api/extensions/docmgr/documents/{doc_id}/comments",
                json={"block_id": "b-1", "content": "Hello"},
            )

        assert response.status_code == 404

    def test_update_comment_endpoint_returns_updated(self):
        """PUT /comments/{comment_id} returns updated comment."""
        comment_id = uuid4()
        client, _, _ = _make_app()
        now = datetime.now().isoformat()

        mock_updated = {
            "id": str(comment_id),
            "doc_id": str(uuid4()),
            "block_id": "b-1",
            "content": "Updated content",
            "parent_id": None,
            "user_id": str(uuid4()),
            "resolved": False,
            "created_at": now,
            "updated_at": now,
            "username": "testuser",
            "full_name": "Test User",
        }

        with patch("app.extensions.docmgr.collab_routers.CommentService") as mock_comment_svc:
            mock_comment_svc.update_comment = AsyncMock(return_value=mock_updated)

            response = client.put(
                f"/api/extensions/docmgr/comments/{comment_id}",
                json={"content": "Updated content"},
            )

        assert response.status_code == 200
        assert response.json()["content"] == "Updated content"

    def test_update_comment_endpoint_404_when_not_owned(self):
        """PUT /comments/{comment_id} returns 404 when comment not found or not owned."""
        comment_id = uuid4()
        client, _, _ = _make_app()

        with patch("app.extensions.docmgr.collab_routers.CommentService") as mock_comment_svc:
            mock_comment_svc.update_comment = AsyncMock(return_value=None)

            response = client.put(
                f"/api/extensions/docmgr/comments/{comment_id}",
                json={"content": "x"},
            )

        assert response.status_code == 404

    def test_delete_comment_endpoint_returns_message(self):
        """DELETE /comments/{comment_id} returns success message."""
        comment_id = uuid4()
        client, _, _ = _make_app()

        with patch("app.extensions.docmgr.collab_routers.CommentService") as mock_comment_svc:
            mock_comment_svc.delete_comment = AsyncMock(return_value=True)

            response = client.delete(f"/api/extensions/docmgr/comments/{comment_id}")

        assert response.status_code == 200
        assert "deleted" in response.json()["message"].lower()

    def test_delete_comment_endpoint_404_when_not_owned(self):
        """DELETE /comments/{comment_id} returns 404 when not found or not owned."""
        comment_id = uuid4()
        client, _, _ = _make_app()

        with patch("app.extensions.docmgr.collab_routers.CommentService") as mock_comment_svc:
            mock_comment_svc.delete_comment = AsyncMock(return_value=False)

            response = client.delete(f"/api/extensions/docmgr/comments/{comment_id}")

        assert response.status_code == 404

    def test_resolve_comment_endpoint(self):
        """POST /comments/{comment_id}/resolve marks comment as resolved."""
        comment_id = uuid4()
        client, _, _ = _make_app()
        now = datetime.now().isoformat()

        mock_resolved = {
            "id": str(comment_id),
            "doc_id": str(uuid4()),
            "block_id": "b-1",
            "content": "Fix this",
            "parent_id": None,
            "user_id": str(uuid4()),
            "resolved": True,
            "created_at": now,
            "updated_at": now,
            "username": "testuser",
            "full_name": "Test User",
        }

        with patch("app.extensions.docmgr.collab_routers.CommentService") as mock_comment_svc:
            mock_comment_svc.resolve_comment = AsyncMock(return_value=mock_resolved)

            response = client.post(f"/api/extensions/docmgr/comments/{comment_id}/resolve")

        assert response.status_code == 200
        assert response.json()["resolved"] is True

    def test_reopen_comment_endpoint(self):
        """POST /comments/{comment_id}/reopen marks comment as unresolved."""
        comment_id = uuid4()
        client, _, _ = _make_app()
        now = datetime.now().isoformat()

        mock_reopened = {
            "id": str(comment_id),
            "doc_id": str(uuid4()),
            "block_id": "b-1",
            "content": "Reopened issue",
            "parent_id": None,
            "user_id": str(uuid4()),
            "resolved": False,
            "created_at": now,
            "updated_at": now,
            "username": "testuser",
            "full_name": "Test User",
        }

        with patch("app.extensions.docmgr.collab_routers.CommentService") as mock_comment_svc:
            mock_comment_svc.reopen_comment = AsyncMock(return_value=mock_reopened)

            response = client.post(f"/api/extensions/docmgr/comments/{comment_id}/reopen")

        assert response.status_code == 200
        assert response.json()["resolved"] is False

    def test_list_versions_endpoint_returns_list(self):
        """GET /documents/{doc_id}/versions returns version list."""
        doc_id = uuid4()
        client, _, _ = _make_app()
        now = datetime.now().isoformat()

        mock_versions = [
            {
                "id": 1,
                "doc_id": str(doc_id),
                "version": 2,
                "summary": "second",
                "created_by": str(uuid4()),
                "created_at": now,
                "username": "alice",
                "full_name": "Alice",
            },
            {
                "id": 2,
                "doc_id": str(doc_id),
                "version": 1,
                "summary": None,
                "created_by": str(uuid4()),
                "created_at": now,
                "username": None,
                "full_name": None,
            },
        ]

        with (
            patch("app.extensions.docmgr.collab_routers.AIDocumentService") as mock_doc_svc,
            patch("app.extensions.docmgr.collab_routers.VersionService") as mock_ver_svc,
        ):
            mock_doc_svc.get_by_id = AsyncMock(return_value=MagicMock())
            mock_ver_svc.list_versions = AsyncMock(return_value=mock_versions)

            response = client.get(f"/api/extensions/docmgr/documents/{doc_id}/versions")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_get_version_endpoint_returns_version(self):
        """GET /documents/{doc_id}/versions/{version} returns version metadata."""
        doc_id = uuid4()
        client, _, _ = _make_app()
        now = datetime.now().isoformat()

        mock_ver = {
            "id": 1,
            "doc_id": str(doc_id),
            "version": 1,
            "summary": "initial",
            "created_by": str(uuid4()),
            "created_at": now,
            "username": "testuser",
            "full_name": "Test User",
        }

        with (
            patch("app.extensions.docmgr.collab_routers.AIDocumentService") as mock_doc_svc,
            patch("app.extensions.docmgr.collab_routers.VersionService") as mock_ver_svc,
        ):
            mock_doc_svc.get_by_id = AsyncMock(return_value=MagicMock())
            mock_ver_svc.get_version = AsyncMock(return_value=mock_ver)

            response = client.get(f"/api/extensions/docmgr/documents/{doc_id}/versions/1")

        assert response.status_code == 200
        assert response.json()["version"] == 1

    def test_get_version_endpoint_strips_snapshot(self):
        """GET version endpoint removes snapshot from response."""
        doc_id = uuid4()
        client, _, _ = _make_app()
        now = datetime.now().isoformat()

        mock_ver = {
            "id": 1,
            "doc_id": str(doc_id),
            "version": 1,
            "snapshot": b"raw bytes",
            "summary": "has snapshot",
            "created_by": str(uuid4()),
            "created_at": now,
            "username": "testuser",
            "full_name": "Test User",
        }

        with (
            patch("app.extensions.docmgr.collab_routers.AIDocumentService") as mock_doc_svc,
            patch("app.extensions.docmgr.collab_routers.VersionService") as mock_ver_svc,
        ):
            mock_doc_svc.get_by_id = AsyncMock(return_value=MagicMock())
            mock_ver_svc.get_version = AsyncMock(return_value=mock_ver)

            response = client.get(f"/api/extensions/docmgr/documents/{doc_id}/versions/1")

        assert response.status_code == 200
        assert "snapshot" not in response.json()
