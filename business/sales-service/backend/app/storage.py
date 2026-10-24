"""MinIO/S3-compatible attachment storage."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from pathlib import Path

from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.config import get_settings
from app.errors import unavailable

logger = logging.getLogger(__name__)
settings = get_settings()
_client = None
_ready = False


def _client_or_raise():
    global _client
    if not settings.minio_enabled:
        raise unavailable("对象存储未启用")
    if _client is None:
        import boto3

        _client = boto3.client(
            "s3",
            endpoint_url=settings.minio_endpoint,
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            region_name=settings.minio_region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
    return _client


async def ensure_bucket() -> bool:
    global _ready
    if not settings.minio_enabled:
        return False
    if _ready:
        return True

    def _ensure():
        client = _client_or_raise()
        try:
            client.head_bucket(Bucket=settings.minio_bucket)
        except ClientError:
            client.create_bucket(Bucket=settings.minio_bucket)

    try:
        await asyncio.to_thread(_ensure)
        _ready = True
        return True
    except (BotoCoreError, ClientError, Exception) as exc:  # noqa: BLE001
        logger.warning("MinIO bucket check failed: %s", exc)
        return False


def safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", Path(name).name)
    return cleaned[:180] or "attachment"


def build_key(object_type: str, object_id: uuid.UUID, file_name: str) -> str:
    return f"{object_type}/{object_id}/{uuid.uuid4().hex}-{safe_name(file_name)}"


async def put_bytes(key: str, data: bytes, content_type: str | None) -> None:
    def _put():
        client = _client_or_raise()
        client.put_object(
            Bucket=settings.minio_bucket,
            Key=key,
            Body=data,
            ContentType=content_type or "application/octet-stream",
        )

    try:
        await asyncio.to_thread(_put)
    except (BotoCoreError, ClientError, Exception) as exc:  # noqa: BLE001
        logger.warning("MinIO upload failed: %s", exc)
        raise unavailable("附件存储暂不可用") from exc


async def get_bytes(key: str) -> tuple[bytes, str | None]:
    def _get():
        client = _client_or_raise()
        response = client.get_object(Bucket=settings.minio_bucket, Key=key)
        return response["Body"].read(), response.get("ContentType")

    try:
        return await asyncio.to_thread(_get)
    except (BotoCoreError, ClientError, Exception) as exc:  # noqa: BLE001
        logger.warning("MinIO download failed: %s", exc)
        raise unavailable("附件读取失败") from exc


async def delete_bytes(key: str) -> None:
    def _delete():
        client = _client_or_raise()
        client.delete_object(Bucket=settings.minio_bucket, Key=key)

    try:
        await asyncio.to_thread(_delete)
    except Exception as exc:  # noqa: BLE001
        logger.warning("MinIO delete failed: %s", exc)


async def health() -> bool:
    if not settings.minio_enabled:
        return False
    return await ensure_bucket()
