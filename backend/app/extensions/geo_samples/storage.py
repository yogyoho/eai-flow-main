# EAI-CUSTOM: forked from app.extensions.contract_price.storage (geo-sample-bank Phase 1).
"""MinIO storage for the geo sample bank (independent ``geo-samples`` bucket).

Single bucket, three prefixes: ``raw/`` (original uploaded report files),
``work/`` (parser output ``parsed.md``), ``clean/`` (curated ``source.md``
fed to generation). Uses GSB_MINIO_* env and intentionally does NOT reuse
app.extensions.config's storage.minio_endpoint: that one defaults to
localhost:9000, unreachable from inside the gateway container (MinIO runs
as the ragflow-minio service on eai-flow-net) — same rationale as
contract_price.
"""

import os
from io import BytesIO

from minio import Minio
from minio.error import S3Error

BUCKET = "geo-samples"


def _client() -> Minio:
    """Minio client for the geo-samples bucket. Uses GSB_MINIO_* env (default
    ragflow-minio:9000 — the container-network address)."""
    return Minio(
        os.environ.get("GSB_MINIO_ENDPOINT", "ragflow-minio:9000"),
        access_key=os.environ.get("GSB_MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.environ.get("GSB_MINIO_SECRET_KEY", "minioadmin"),
        secure=os.environ.get("GSB_MINIO_SECURE", "false").lower() == "true",
    )


def _ensure_bucket(mc: Minio) -> None:
    if not mc.bucket_exists(BUCKET):
        mc.make_bucket(BUCKET)


def put_raw(report_id: str, file_name: str, data: bytes) -> str:
    """Store the original uploaded report file under raw/<id>/; return its s3:// uri."""
    file_name = os.path.basename(file_name)  # strip any path component: keep the raw/ prefix layout intact
    key = f"raw/{report_id}/{file_name}"
    mc = _client()
    _ensure_bucket(mc)
    mc.put_object(bucket=BUCKET, object_name=key, data=BytesIO(data), length=len(data))
    return f"s3://{BUCKET}/{key}"


def put_work(report_id: str, data: bytes) -> str:
    """Store parser output as work/<id>/parsed.md; return its s3:// uri."""
    key = f"work/{report_id}/parsed.md"
    mc = _client()
    _ensure_bucket(mc)
    mc.put_object(bucket=BUCKET, object_name=key, data=BytesIO(data), length=len(data))
    return f"s3://{BUCKET}/{key}"


def put_clean(report_id: str, data: bytes) -> str:
    """Store the curated source markdown as clean/<id>/source.md; return its s3:// uri."""
    key = f"clean/{report_id}/source.md"
    mc = _client()
    _ensure_bucket(mc)
    mc.put_object(bucket=BUCKET, object_name=key, data=BytesIO(data), length=len(data))
    return f"s3://{BUCKET}/{key}"


def get_object(uri: str) -> bytes:
    """s3://bucket/key → bytes（work/clean/preview 通用读取）。"""
    prefix = f"s3://{BUCKET}/"
    if not uri.startswith(prefix):
        raise ValueError(f"unexpected uri: {uri}")  # ValueError, not assert: asserts are stripped under python -O
    resp = _client().get_object(BUCKET, uri[len(prefix) :])
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()


def object_exists(uri: str) -> bool:
    prefix = f"s3://{BUCKET}/"
    if not uri.startswith(prefix):
        return False
    try:
        _client().stat_object(BUCKET, uri[len(prefix) :])
        return True
    except S3Error:
        return False
