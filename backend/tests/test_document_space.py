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
