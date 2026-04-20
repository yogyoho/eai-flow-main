"""Storage providers for knowledge base documents."""

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from minio import Minio

from app.extensions.config import get_extensions_config

logger = logging.getLogger(__name__)


def _sanitize_filename(name: str) -> str:
    return Path(name).name.replace("\\", "/")


def _is_s3_uri(uri: str) -> bool:
    return uri.startswith("s3://")


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    if not bucket or not key:
        raise ValueError(f"Invalid s3 uri: {uri}")
    return bucket, key


@dataclass
class StoredObject:
    uri: str
    bucket: Optional[str] = None
    key: Optional[str] = None


class StorageProvider:
    """Abstract storage provider."""

    async def upload_local_file(
        self,
        local_path: str,
        owner_id: str,
        kb_id: str,
        filename: str,
        content_type: Optional[str] = None,
    ) -> StoredObject:
        raise NotImplementedError

    async def delete(self, uri: str) -> None:
        raise NotImplementedError


class LocalStorageProvider(StorageProvider):
    """Local filesystem storage (no-op for upload)."""

    async def upload_local_file(
        self,
        local_path: str,
        owner_id: str,
        kb_id: str,
        filename: str,
        content_type: Optional[str] = None,
    ) -> StoredObject:
        return StoredObject(uri=local_path)

    async def delete(self, uri: str) -> None:
        if os.path.exists(uri):
            os.unlink(uri)


class MinioStorageProvider(StorageProvider):
    """MinIO (S3-compatible) storage provider."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
        region: str = "",
        prefix: str = "knowledge",
    ) -> None:
        self._client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
            region=region or None,
        )
        self._bucket = bucket
        self._prefix = prefix.strip("/")

    def _ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)

    def _build_object_name(self, owner_id: str, kb_id: str, filename: str) -> str:
        safe_name = _sanitize_filename(filename)
        return f"{self._prefix}/{owner_id}/knowledge/{kb_id}/{safe_name}"

    async def upload_local_file(
        self,
        local_path: str,
        owner_id: str,
        kb_id: str,
        filename: str,
        content_type: Optional[str] = None,
    ) -> StoredObject:
        object_name = self._build_object_name(owner_id, kb_id, filename)
        await asyncio.to_thread(self._ensure_bucket)
        await asyncio.to_thread(
            self._client.fput_object,
            self._bucket,
            object_name,
            local_path,
            content_type=content_type,
        )
        uri = f"s3://{self._bucket}/{object_name}"
        return StoredObject(uri=uri, bucket=self._bucket, key=object_name)

    async def delete(self, uri: str) -> None:
        bucket, key = _parse_s3_uri(uri)
        await asyncio.to_thread(self._client.remove_object, bucket, key)


_provider: Optional[StorageProvider] = None


def get_storage_provider() -> StorageProvider:
    global _provider
    if _provider is not None:
        return _provider

    config = get_extensions_config()
    storage = config.storage
    if storage.type.lower() == "minio":
        if not storage.minio_access_key or not storage.minio_secret_key:
            logger.warning("MinIO storage enabled but credentials not set, falling back to local storage")
            _provider = LocalStorageProvider()
        else:
            _provider = MinioStorageProvider(
                endpoint=storage.minio_endpoint,
                access_key=storage.minio_access_key,
                secret_key=storage.minio_secret_key,
                bucket=storage.minio_bucket,
                secure=storage.minio_secure,
                region=storage.minio_region,
                prefix=storage.minio_prefix,
            )
    else:
        _provider = LocalStorageProvider()

    return _provider


def is_remote_uri(uri: str) -> bool:
    return _is_s3_uri(uri)
