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
