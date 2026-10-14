"""MinIO storage for contract files (independent ``cpa-contracts`` bucket).

Shares connection settings (endpoint/credentials) with knowledge storage via
``app.extensions.config`` but uses a SEPARATE bucket so contract data is
physically isolated from kb-docs. Provides upload/get for contracts and
per-page OCR preview PNGs (used by the traceback overlay UI).

The skill-side pipeline has its own ContractStore (skills/.../storage.py)
with the same bucket; this is the backend-side mirror for the management API.
"""

import hashlib
import os
from io import BytesIO

from minio import Minio

BUCKET = "cpa-contracts"


def _client() -> Minio:
    """Minio client for the contract bucket. Uses CPA_MINIO_* env (default
    ragflow-minio:9000 — the container-network address). NOTE: we intentionally
    do NOT reuse app.extensions.config's storage.minio_endpoint here: that one
    defaults to localhost:9000, which is unreachable from inside the gateway
    container (MinIO runs as the ragflow-minio service on eai-flow-net)."""
    return Minio(
        os.environ.get("CPA_MINIO_ENDPOINT", "ragflow-minio:9000"),
        access_key=os.environ.get("CPA_MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.environ.get("CPA_MINIO_SECRET_KEY", "minioadmin"),
        secure=os.environ.get("CPA_MINIO_SECURE", "false").lower() == "true",
    )


def _ensure_bucket(mc: Minio) -> None:
    if not mc.bucket_exists(BUCKET):
        mc.make_bucket(BUCKET)


def upload_contract(local_path: str, key: str) -> str:
    """Upload a contract file from a local path; return its s3:// uri."""
    mc = _client()
    _ensure_bucket(mc)
    mc.fput_object(BUCKET, key, local_path)
    return f"s3://{BUCKET}/{key}"


def upload_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    mc = _client()
    _ensure_bucket(mc)
    mc.put_object(BUCKET, key, BytesIO(data), length=len(data), content_type=content_type)
    return f"s3://{BUCKET}/{key}"


def get_object(key: str) -> bytes:
    mc = _client()
    resp = mc.get_object(BUCKET, key)
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()


def get_preview(preview_prefix: str, page_no: int) -> bytes:
    """Read a page's OCR preview PNG (preview_prefix like 'previews/{doc_id}/')."""
    return get_object(f"{preview_prefix}page-{page_no}.png")


def sha256(key: str) -> str:
    return hashlib.sha256(get_object(key)).hexdigest()


def delete_object(key: str) -> None:
    """Remove a contract object from the bucket. Silent if missing (cleanup)."""
    try:
        _client().remove_object(BUCKET, key)
    except Exception:
        # best-effort; a missing object must not abort a document delete
        pass


# EAI-CUSTOM (cpa v3 文件库, spec 2026-10-14 §1.2): 文件库档案区前缀。
# 管线 scanner 跳过该前缀;只有「加入解析」拷出的对象才进扫描区。
LIBRARY_PREFIX = "library/"


def library_key(folder_id: str, file_hash: str, file_name: str) -> str:
    """库内对象键 library/{folder}/{hash16}_{name}。

    同文件夹同内容天然同键（幂等覆盖）;跨文件夹各自成对象,删除互不影响。
    文件名中的路径分隔符替换掉,防止借文件名伪造子路径。
    """
    safe = (file_name or "file").replace("/", "_").replace("\\", "_")
    return f"{LIBRARY_PREFIX}{folder_id}/{file_hash[:16]}_{safe}"


def copy_object(src_key: str, dst_key: str) -> str:
    """MinIO 服务端拷贝（加入解析: library/... → 扫描区根），返回 s3:// uri。"""
    from minio.commonconfig import CopySource

    mc = _client()
    mc.copy_object(BUCKET, dst_key, CopySource(BUCKET, src_key))
    return f"s3://{BUCKET}/{dst_key}"
