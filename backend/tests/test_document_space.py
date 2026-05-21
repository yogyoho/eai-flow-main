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
