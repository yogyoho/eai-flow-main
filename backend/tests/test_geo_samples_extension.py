"""Tests for the geo_samples extension (models, redactor, parsers, routes)."""

from unittest.mock import MagicMock

import pytest


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
    assert calls[0]["bucket_name"] == "geo-samples"
    assert calls[0]["object_name"] == "raw/rep1/报告.docx"


def test_storage_put_kwargs_match_real_minio_signature(monkeypatch):
    """回归（bug-3072）：put_object 关键字必须是 minio SDK 真实形参。

    旧代码传 bucket=（真实形参是 bucket_name），MagicMock 不校验签名所以
    单测全绿，实跑上传 500（TypeError: unexpected keyword argument 'bucket'）。
    """
    import inspect

    from minio import Minio

    from app.extensions.geo_samples import storage

    real_params = set(inspect.signature(Minio.put_object).parameters)
    assert "bucket_name" in real_params
    assert "bucket" not in real_params

    calls = []
    monkeypatch.setattr(storage, "_client", lambda: MagicMock(put_object=lambda *a, **k: calls.append(k)))
    storage.put_raw("rep1", "a.docx", b"data")
    storage.put_work("rep1", b"md")
    storage.put_clean("rep1", b"md")
    assert len(calls) == 3
    for call in calls:
        assert set(call) <= real_params, f"put_object 传了 SDK 不存在的形参: {set(call) - real_params}"
        assert call["bucket_name"] == "geo-samples"


@pytest.mark.asyncio
async def test_find_duplicate_document_matches_cross_filename():
    from unittest.mock import AsyncMock, MagicMock

    from app.extensions.geo_samples import crud
    from app.extensions.geo_samples.models import GsbDocument

    existing = GsbDocument(report_id="rep-a", file_name="a.pdf", file_hash="h1", file_type="pdf", raw_uri="s3://geo-samples/raw/rep-a/a.pdf")

    def session_returning(row):
        session = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=row)
        session.execute = AsyncMock(return_value=result)
        return session

    dup = await crud.find_duplicate_document(session_returning(existing), "h1", exclude_uri="s3://geo-samples/raw/rep-b/b.pdf")
    assert dup is existing
    assert await crud.find_duplicate_document(session_returning(None), "h1", exclude_uri="s3://geo-samples/raw/x/x.pdf") is None


def test_schemas_roundtrip():
    from app.extensions.geo_samples.schemas import DocumentOut, ReviewRequest, UploadMeta

    meta = UploadMeta(report_id="rep-1", stage="exploration", mineral="gold", year=2019)
    assert meta.mineral == "gold"
    assert ReviewRequest(decision="reject", note="漏脱矿权人").decision == "reject"
    assert DocumentOut.model_fields["status"].annotation is not None


def test_router_exposes_all_functional_areas():
    from app.extensions.geo_samples import router

    paths = {r.path for r in router.routes}
    base = "/api/extensions/geo-samples"
    assert f"{base}/documents" in paths
    assert f"{base}/documents/upload" in paths
    assert any("parse" in p for p in paths)
    assert any("/redact" in p for p in paths)
    assert any("review" in p for p in paths)
    assert any("redactions" in p for p in paths)
    assert f"{base}/runs" in paths


def test_all_endpoints_require_permission_source_level():
    """静态源码断言：每个 @router. 端点附近都有 _PERM/require_permission 防护。"""
    import inspect

    from app.extensions.geo_samples import routers

    src = inspect.getsource(routers)
    endpoints = src.count("@router.")
    guarded = src.count("= _PERM") + src.count("require_permission(")
    assert guarded >= endpoints, f"{endpoints} 个端点仅 {guarded} 处权限防护"
