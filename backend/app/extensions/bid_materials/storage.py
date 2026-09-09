# EAI-CUSTOM: forked from app.extensions.geo_samples.storage (bug-3109 v4 资质 MinIO 版本库).
"""MinIO storage for bid qualifications (independent ``bid-qualifications`` bucket).

对象键 {qual_id}/v{n}.{ext}——版本不可变只追加; 删除=best-effort(资质文件误删=灾难)。
读语义对齐 geo fork: 仅 NoSuchKey→None(调用方 404), 其余 S3Error(AccessDenied/NoSuchBucket
等基础设施故障) fail-fast 上抛——不许伪装成"文件缺失"。
Uses BQM_MINIO_* env (default ragflow-minio:9000, 同 geo/contract_price 理由)。
调用方负责 to_thread(同步 minio 客户端勿上事件循环)。
"""

import logging
import os
import re
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


def _key(qual_id: str, version: int, ext: str) -> str:
    """对象键单点: {qual_id}/v{n}.{ext}——put/get/delete 共用, 防三处手写漂移。"""
    return f"{qual_id}/v{version}.{ext}"


def put_file(qual_id: str, version: int, file_name: str, data: bytes) -> str:
    """存资质扫描件 {qual_id}/v{n}.{ext}; 返回 minio_key。

    ext 在此单点清洗到 [a-z0-9] 且 ≤9 字符（对齐 DB file_ext String(10) 口径）。
    """
    ext = re.sub(r"[^a-z0-9]", "", os.path.splitext(file_name)[1].lstrip(".").lower())[:9] or "bin"
    key = _key(qual_id, version, ext)
    mc = _client()
    _ensure_bucket(mc)
    mc.put_object(bucket_name=BUCKET, object_name=key, data=BytesIO(data), length=len(data))
    return key


def get_file(qual_id: str, version: int, ext: str) -> bytes | None:
    """读当前版对象; 仅缺失(NoSuchKey)→None(调用方 404), 其余 S3Error fail-fast 上抛。"""
    key = _key(qual_id, version, ext)
    try:
        resp = _client().get_object(BUCKET, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()
    except S3Error as exc:
        if exc.code != "NoSuchKey":
            raise  # AccessDenied/NoSuchBucket 等基础设施故障不许伪装成 404
        log.warning("get_file missing %s: %s", key, exc)
        return None


def delete_file(qual_id: str, version: int, ext: str) -> None:
    """best-effort 删除（S3Error 吞掉记 warning; 对齐 geo/contract_price 同款语义）。"""
    key = _key(qual_id, version, ext)
    try:
        _client().remove_object(BUCKET, key)
    except S3Error as exc:
        log.warning("delete_file failed for %s: %s", key, exc)
