# EAI-CUSTOM: forked from contract-price-analysis/scripts/storage.py(bucket→csp-parts)。
"""MinIO object storage for spare-parts contract files (独立 bucket)。

共用 ragflow-minio 实例,但用独立 bucket(csp-parts)使备件合同数据与 kb-docs
物理隔离。连接参数来自 Config(env),与知识库存储共用 endpoint/凭据。
亦存逐页 OCR 预览 PNG 供溯源。
"""

import hashlib
from io import BytesIO

from minio import Minio

from scripts.config import Config


class SparePartsStore:
    def __init__(self, cfg: Config):
        self._client = Minio(
            cfg.minio_endpoint,
            access_key=cfg.minio_access_key,
            secret_key=cfg.minio_secret_key,
            secure=cfg.minio_secure,
        )
        self._bucket = cfg.minio_bucket
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)

    @property
    def bucket(self) -> str:
        return self._bucket

    def list_objects(self):
        return list(self._client.list_objects(self._bucket, recursive=True))

    def get(self, key: str) -> bytes:
        resp = self._client.get_object(self._bucket, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self._client.put_object(
            self._bucket, key, BytesIO(data), length=len(data), content_type=content_type
        )
        return f"s3://{self._bucket}/{key}"

    def put_file(self, key: str, local_path: str, content_type: str | None = None) -> str:
        self._client.fput_object(self._bucket, key, local_path, content_type=content_type)
        return f"s3://{self._bucket}/{key}"

    def put_preview(self, doc_id: str, page_no: int, png_bytes: bytes) -> str:
        key = f"previews/{doc_id}/page-{page_no}.png"
        self.put_bytes(key, png_bytes, content_type="image/png")
        return f"previews/{doc_id}/"

    def get_preview(self, preview_prefix: str, page_no: int) -> bytes:
        return self.get(f"{preview_prefix}page-{page_no}.png")

    def sha256(self, key: str) -> str:
        return hashlib.sha256(self.get(key)).hexdigest()

    def delete(self, key: str) -> None:
        self._client.remove_object(self._bucket, key)
