"""Tests for the geo_samples extension (models, redactor, parsers, routes)."""

from unittest.mock import MagicMock


def test_gsb_models_registered_on_shared_base():
    import app.extensions.geo_samples  # noqa: F401
    from app.extensions.database import Base

    tables = set(Base.metadata.tables)
    assert {"gsb_documents", "gsb_redactions", "gsb_run_history"} <= tables


def test_storage_key_layout(monkeypatch):
    from app.extensions.geo_samples import storage

    calls = []
    monkeypatch.setattr(storage, "_client", lambda: MagicMock(put_object=lambda *a, **k: calls.append(k)))
    uri = storage.put_raw("rep1", "报告.docx", b"data")
    assert uri == "s3://geo-samples/raw/rep1/报告.docx"
    assert calls[0]["bucket"] == "geo-samples"
    assert calls[0]["object_name"] == "raw/rep1/报告.docx"
