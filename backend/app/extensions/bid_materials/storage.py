# EAI-CUSTOM: forked from app.extensions.geo_samples.storage (bug-3109 v4 资质 MinIO 版本库).
"""MinIO storage for bid qualifications (independent ``bid-qualifications`` bucket).

对象键 {qual_id}/v{n}.{ext}——版本不可变只追加; 删除=best-effort(资质文件误删=灾难)。
Uses BQM_MINIO_* env (default ragflow-minio:9000, 同 geo/contract_price 理由)。
调用方负责 to_thread(同步 minio 客户端勿上事件循环)。
"""

import logging
import os
from io import BytesIO

from minio import Minio
from minio.error import S3Error

BUCKET = "bid-qualifications"

log = logging.getLogger("bid_materials.storage")


def _client() -> Minio:
    return Minio(
        os.environ.get("BQM_MINIO_ENDPOINT", "ragflow-minio:9000"),
        access_key=os.environ.get("BQM_MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.environ.get("BQM_MINIO_SECRET_KEY", "minioadmin"),
        secure=os.environ.get("BQM_MINIO_SECURE", "false").lower() == "true",
    )


def _ensure_bucket(mc: Minio) -> None:
    if not mc.bucket_exists(BUCKET):
        mc.make_bucket(BUCKET)


def put_file(qual_id: str, version: int, file_name: str, data: bytes) -> str:
    """存资质扫描件 {qual_id}/v{n}.{ext}; 返回 minio_key。"""
    ext = os.path.splitext(file_name)[1].lstrip(".").lower() or "bin"
    key = f"{qual_id}/v{version}.{ext}"
    mc = _client()
    _ensure_bucket(mc)
    mc.put_object(bucket_name=BUCKET, object_name=key, data=BytesIO(data), length=len(data))
    return key


def get_file(qual_id: str, version: int, ext: str) -> bytes | None:
    """读当前版对象; 缺失→None(调用方 404)。"""
    key = f"{qual_id}/v{version}.{ext}"
    try:
        resp = _client().get_object(BUCKET, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()
    except S3Error as exc:
        log.warning("get_file missing %s: %s", key, exc)
        return None


def delete_file(qual_id: str, version: int, ext: str) -> None:
    """best-effort 删除（S3Error 吞掉记 warning; 对齐 geo/contract_price 同款语义）。"""
    key = f"{qual_id}/v{version}.{ext}"
    try:
        _client().remove_object(BUCKET, key)
    except S3Error as exc:
        log.warning("delete_file failed for %s: %s", key, exc)
