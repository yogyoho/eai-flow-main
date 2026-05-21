import os
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import UUID

import pytest

from app.extensions.models import AIDocument
from app.extensions.schemas import AIDocumentCreate, AIDocumentResponse


def test_ai_document_model_has_new_fields():
    col_names = {c.name for c in AIDocument.__table__.columns}
    assert "doc_type" in col_names
    assert "file_ref_path" in col_names
    assert "file_size" in col_names
    assert "file_mime" in col_names


def test_ai_document_create_schema_accepts_file_ref_fields():
    data = AIDocumentCreate(
        title="test.md",
        folder="测试",
        doc_type="file_ref",
        file_ref_path="/mnt/user-data/test.md",
        file_size=1024,
        file_mime="text/markdown",
    )
    assert data.doc_type == "file_ref"


def test_ai_document_response_includes_new_fields():
    schema_fields = set(AIDocumentResponse.model_fields.keys())
    for f in ("doc_type", "file_ref_path", "file_size", "file_mime"):
        assert f in schema_fields


@pytest.mark.asyncio
async def test_sync_thread_files_creates_file_ref_docs():
    """sync_thread_files should create file_ref documents for sandbox files."""
    from app.extensions.docmgr.service import AIDocumentService

    db = AsyncMock()
    db.commit = AsyncMock()
    # Mock: no existing docs for this thread+path combo
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    user_id = UUID("12345678-1234-1234-1234-123456789012")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create fake sandbox files
        with open(os.path.join(tmpdir, "report.md"), "w") as f:
            f.write("# Report\nContent here")
        with open(os.path.join(tmpdir, "data.csv"), "w") as f:
            f.write("a,b\n1,2")

        with patch.object(AIDocumentService, "_get_thread_title", new_callable=AsyncMock, return_value="测试线程"):
            result = await AIDocumentService.sync_thread_files(
                db=db,
                user_id=user_id,
                thread_id="thread-001",
                sandbox_dir=tmpdir,
            )

    assert result["synced"] >= 2


# ─── Task 3: move, rename, batch_delete, preview ───────────────────────────


@pytest.mark.asyncio
async def test_move_to_documents_text_file():
    """move_to_documents should read text file content into doc.content."""
    from app.extensions.docmgr.service import AIDocumentService

    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    doc = AIDocument(
        user_id=UUID("12345678-1234-1234-1234-123456789012"),
        title="report.md",
        doc_type="file_ref",
        file_ref_path="",
        file_mime="text/markdown",
    )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write("# Hello\nWorld content")
        tmppath = f.name

    doc.file_ref_path = tmppath
    try:
        result = await AIDocumentService.move_to_documents(db, doc)
        assert result.doc_type == "document"
        assert "# Hello" in result.content
        assert "World content" in result.content
    finally:
        os.unlink(tmppath)


@pytest.mark.asyncio
async def test_move_to_documents_binary_file():
    """move_to_documents should store binary_ref JSON for non-text files."""
    from app.extensions.docmgr.service import AIDocumentService

    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    doc = AIDocument(
        user_id=UUID("12345678-1234-1234-1234-123456789012"),
        title="image.png",
        doc_type="file_ref",
        file_ref_path="",
        file_mime="image/png",
    )

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        tmppath = f.name

    doc.file_ref_path = tmppath
    try:
        result = await AIDocumentService.move_to_documents(db, doc)
        assert result.doc_type == "document"
        import json

        parsed = json.loads(result.content)
        assert parsed["type"] == "binary_ref"
        assert "file_ref_path" in parsed
    finally:
        os.unlink(tmppath)


@pytest.mark.asyncio
async def test_move_to_documents_missing_file():
    """move_to_documents should store file_missing JSON when file doesn't exist."""
    from app.extensions.docmgr.service import AIDocumentService

    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    doc = AIDocument(
        user_id=UUID("12345678-1234-1234-1234-123456789012"),
        title="gone.txt",
        doc_type="file_ref",
        file_ref_path="/nonexistent/path/gone.txt",
        file_mime="text/plain",
    )

    result = await AIDocumentService.move_to_documents(db, doc)
    assert result.doc_type == "document"
    import json

    parsed = json.loads(result.content)
    assert parsed["type"] == "file_missing"


@pytest.mark.asyncio
async def test_move_to_documents_non_file_ref_returns_unchanged():
    """move_to_documents should return doc unchanged if doc_type is not file_ref."""
    from app.extensions.docmgr.service import AIDocumentService

    db = AsyncMock()
    doc = AIDocument(
        user_id=UUID("12345678-1234-1234-1234-123456789012"),
        title="My Doc",
        doc_type="document",
        content="Already here",
    )

    result = await AIDocumentService.move_to_documents(db, doc)
    assert result.doc_type == "document"
    assert result.content == "Already here"
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_delete_deletes_owned_documents():
    """batch_delete should only delete documents belonging to the user."""
    from app.extensions.docmgr.service import AIDocumentService

    db = AsyncMock()
    db.commit = AsyncMock()
    db.delete = AsyncMock()

    user_id = UUID("12345678-1234-1234-1234-123456789012")
    doc_ids = [UUID("aaaaaaaa-1111-1111-1111-111111111111"), UUID("bbbbbbbb-2222-2222-2222-222222222222")]

    # Mock: query returns 2 docs
    mock_doc1 = MagicMock()
    mock_doc2 = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_doc1, mock_doc2]
    db.execute = AsyncMock(return_value=mock_result)

    count = await AIDocumentService.batch_delete(db, user_id, doc_ids)
    assert count == 2
    assert db.delete.await_count == 2


@pytest.mark.asyncio
async def test_batch_delete_empty_list():
    """batch_delete with empty list should return 0."""
    from app.extensions.docmgr.service import AIDocumentService

    db = AsyncMock()
    user_id = UUID("12345678-1234-1234-1234-123456789012")

    count = await AIDocumentService.batch_delete(db, user_id, [])
    assert count == 0


@pytest.mark.asyncio
async def test_batch_delete_exceeds_limit():
    """batch_delete should raise ValueError for more than 50 ids."""
    from app.extensions.docmgr.service import AIDocumentService

    db = AsyncMock()
    user_id = UUID("12345678-1234-1234-1234-123456789012")
    too_many = [UUID(f"{i:032x}") for i in range(51)]

    with pytest.raises(ValueError, match="Batch delete limited to 50"):
        await AIDocumentService.batch_delete(db, user_id, too_many)


@pytest.mark.asyncio
async def test_rename_document():
    """rename should update title and rename physical file for file_ref."""
    from app.extensions.docmgr.service import AIDocumentService

    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    with tempfile.TemporaryDirectory() as tmpdir:
        old_path = os.path.join(tmpdir, "old_name.txt")
        with open(old_path, "w") as f:
            f.write("content")

        doc = AIDocument(
            user_id=UUID("12345678-1234-1234-1234-123456789012"),
            title="old_name.txt",
            doc_type="file_ref",
            file_ref_path=old_path,
        )

        result = await AIDocumentService.rename(db, doc, "new_name.txt")
        assert result.title == "new_name.txt"
        assert "new_name.txt" in result.file_ref_path
        assert not os.path.exists(old_path)
        assert os.path.exists(os.path.join(tmpdir, "new_name.txt"))


@pytest.mark.asyncio
async def test_rename_regular_document():
    """rename should only update title for non-file_ref documents."""
    from app.extensions.docmgr.service import AIDocumentService

    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    doc = AIDocument(
        user_id=UUID("12345678-1234-1234-1234-123456789012"),
        title="Old Title",
        doc_type="document",
        content="Some content",
    )

    result = await AIDocumentService.rename(db, doc, "New Title")
    assert result.title == "New Title"


@pytest.mark.asyncio
async def test_read_file_content_success():
    """read_file_content should return file content for existing files."""
    from app.extensions.docmgr.service import AIDocumentService

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("Hello preview content")
        tmppath = f.name

    doc = AIDocument(
        user_id=UUID("12345678-1234-1234-1234-123456789012"),
        title="test.txt",
        doc_type="file_ref",
        file_ref_path=tmppath,
    )

    try:
        content = await AIDocumentService.read_file_content(doc)
        assert content == "Hello preview content"
    finally:
        os.unlink(tmppath)


@pytest.mark.asyncio
async def test_read_file_content_missing():
    """read_file_content should return None for missing files."""
    from app.extensions.docmgr.service import AIDocumentService

    doc = AIDocument(
        user_id=UUID("12345678-1234-1234-1234-123456789012"),
        title="gone.txt",
        doc_type="file_ref",
        file_ref_path="/nonexistent/gone.txt",
    )

    content = await AIDocumentService.read_file_content(doc)
    assert content is None


@pytest.mark.asyncio
async def test_read_file_content_too_large():
    """read_file_content should return None for files over 10MB."""
    from app.extensions.docmgr.service import AIDocumentService

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        f.write(b"x" * (11 * 1024 * 1024))  # 11MB
        tmppath = f.name

    doc = AIDocument(
        user_id=UUID("12345678-1234-1234-1234-123456789012"),
        title="large.bin",
        doc_type="file_ref",
        file_ref_path=tmppath,
    )

    try:
        content = await AIDocumentService.read_file_content(doc)
        assert content is None
    finally:
        os.unlink(tmppath)


@pytest.mark.asyncio
async def test_list_docs_doc_type_filter():
    """list_docs should filter by doc_type when provided."""
    from unittest.mock import call

    from app.extensions.docmgr.service import AIDocumentService

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalar.return_value = 0
    db.execute = AsyncMock(return_value=mock_result)

    user_id = UUID("12345678-1234-1234-1234-123456789012")

    await AIDocumentService.list_docs(db, user_id=user_id, doc_type="file_ref")

    # Verify db.execute was called (once for docs, once for count)
    assert db.execute.await_count == 2


# ─── Task 4: Document Shares ────────────────────────────────────────────────


def test_document_share_model_columns():
    """DocumentShare model should have all expected columns."""
    from app.extensions.docmgr.share_models import DocumentShare

    col_names = {c.name for c in DocumentShare.__table__.columns}
    for col in ("id", "document_id", "share_type", "share_target_id", "share_token", "permission", "created_by", "created_at"):
        assert col in col_names, f"Missing column: {col}"


def test_share_create_request_validation():
    """ShareCreateRequest should validate share_type and permission patterns."""
    from app.extensions.docmgr.share_schemas import ShareCreateRequest
    from pydantic import ValidationError

    # Valid user share
    req = ShareCreateRequest(share_type="user", share_target_id="user-uuid-here", permission="read")
    assert req.share_type == "user"
    assert req.permission == "read"

    # Valid link share
    req = ShareCreateRequest(share_type="link", permission="edit")
    assert req.share_type == "link"
    assert req.share_target_id is None

    # Invalid share_type
    try:
        ShareCreateRequest(share_type="invalid")
        assert False, "Should have raised ValidationError"
    except ValidationError:
        pass

    # Invalid permission
    try:
        ShareCreateRequest(share_type="user", permission="admin")
        assert False, "Should have raised ValidationError"
    except ValidationError:
        pass


def test_share_response_model():
    """ShareResponse should have all expected fields."""
    from app.extensions.docmgr.share_schemas import ShareResponse

    fields = set(ShareResponse.model_fields.keys())
    for f in ("id", "document_id", "share_type", "share_target_id", "share_token", "permission", "created_by", "created_at"):
        assert f in fields, f"Missing field: {f}"


@pytest.mark.asyncio
async def test_create_share_verify_ownership():
    """create_share should raise ValueError when document not found or not owned."""
    from app.extensions.docmgr.share_service import ShareService
    from app.extensions.docmgr.share_schemas import ShareCreateRequest

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # document not found
    db.execute = AsyncMock(return_value=mock_result)

    user_id = UUID("12345678-1234-1234-1234-123456789012")
    doc_id = UUID("aaaaaaaa-1111-1111-1111-111111111111")
    data = ShareCreateRequest(share_type="user", share_target_id=str(user_id))

    with pytest.raises(ValueError, match="Document not found"):
        await ShareService.create_share(db, user_id, doc_id, data)


@pytest.mark.asyncio
async def test_create_share_link_generates_token():
    """create_share for link type should generate a share_token."""
    from app.extensions.docmgr.share_service import ShareService
    from app.extensions.docmgr.share_schemas import ShareCreateRequest

    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()

    # First execute: ownership check returns a document
    mock_doc = MagicMock()
    # Second execute: mark as shared
    mock_doc_obj = MagicMock()
    mock_doc_obj.is_shared = False
    # Third execute (refresh): return the share object
    mock_share = MagicMock()
    mock_share.id = UUID("cccccccc-3333-3333-3333-333333333333")
    mock_share.document_id = UUID("aaaaaaaa-1111-1111-1111-111111111111")
    mock_share.share_type = "link"
    mock_share.share_target_id = None
    mock_share.share_token = "some-token-value"
    mock_share.permission = "read"
    mock_share.created_by = UUID("12345678-1234-1234-1234-123456789012")
    mock_share.created_at = "2026-01-01T00:00:00"

    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.scalar_one_or_none.return_value = mock_doc
        elif call_count == 2:
            result.scalar_one_or_none.return_value = mock_doc_obj
        return result

    db.execute = AsyncMock(side_effect=fake_execute)

    async def fake_refresh(obj):
        for attr in ("id", "document_id", "share_type", "share_target_id", "share_token", "permission", "created_by", "created_at"):
            if not hasattr(obj, attr) or getattr(obj, attr) is None:
                setattr(obj, attr, getattr(mock_share, attr))

    db.refresh = AsyncMock(side_effect=fake_refresh)

    user_id = UUID("12345678-1234-1234-1234-123456789012")
    doc_id = UUID("aaaaaaaa-1111-1111-1111-111111111111")
    data = ShareCreateRequest(share_type="link")

    response = await ShareService.create_share(db, user_id, doc_id, data)
    assert response.share_type == "link"
    assert response.share_token is not None
    assert mock_doc_obj.is_shared is True


@pytest.mark.asyncio
async def test_list_shares():
    """list_shares should return all shares for a document."""
    from app.extensions.docmgr.share_service import ShareService

    db = AsyncMock()
    mock_share = MagicMock()
    mock_share.id = UUID("cccccccc-3333-3333-3333-333333333333")
    mock_share.document_id = UUID("aaaaaaaa-1111-1111-1111-111111111111")
    mock_share.share_type = "user"
    mock_share.share_target_id = "target-uuid"
    mock_share.share_token = None
    mock_share.permission = "read"
    mock_share.created_by = UUID("12345678-1234-1234-1234-123456789012")
    mock_share.created_at = "2026-01-01T00:00:00"

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_share]
    db.execute = AsyncMock(return_value=mock_result)

    user_id = UUID("12345678-1234-1234-1234-123456789012")
    doc_id = UUID("aaaaaaaa-1111-1111-1111-111111111111")

    shares = await ShareService.list_shares(db, doc_id, user_id)
    assert len(shares) == 1
    assert shares[0].share_type == "user"


@pytest.mark.asyncio
async def test_revoke_share_not_found():
    """revoke_share should return False when share not found."""
    from app.extensions.docmgr.share_service import ShareService

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    user_id = UUID("12345678-1234-1234-1234-123456789012")
    share_id = UUID("cccccccc-3333-3333-3333-333333333333")

    result = await ShareService.revoke_share(db, share_id, user_id)
    assert result is False


@pytest.mark.asyncio
async def test_get_shared_document_not_found():
    """get_shared_document should return None for invalid token."""
    from app.extensions.docmgr.share_service import ShareService

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    result = await ShareService.get_shared_document(db, "invalid-token")
    assert result is None


@pytest.mark.asyncio
async def test_list_shared_with_me():
    """list_shared_with_me should return documents shared with user."""
    from app.extensions.docmgr.share_service import ShareService

    db = AsyncMock()

    mock_share = MagicMock()
    mock_share.permission = "read"
    mock_share.share_type = "user"
    mock_share.created_by = UUID("99999999-9999-9999-9999-999999999999")
    mock_share.created_at = MagicMock()

    mock_doc = MagicMock()
    mock_doc.id = UUID("aaaaaaaa-1111-1111-1111-111111111111")
    mock_doc.title = "Shared Doc"
    mock_doc.content = "content"
    mock_doc.doc_type = "document"
    mock_doc.folder = "默认文件夹"
    mock_doc.updated_at = MagicMock()
    mock_doc.updated_at.isoformat.return_value = "2026-01-01T00:00:00"

    mock_result = MagicMock()
    mock_result.all.return_value = [(mock_share, mock_doc)]
    db.execute = AsyncMock(return_value=mock_result)

    user_id = UUID("12345678-1234-1234-1234-123456789012")
    result = await ShareService.list_shared_with_me(db, user_id)
    assert len(result) == 1
    assert result[0]["document"]["title"] == "Shared Doc"
    assert result[0]["permission"] == "read"
