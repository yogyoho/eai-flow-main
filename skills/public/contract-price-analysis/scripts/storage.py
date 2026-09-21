"""MinIO object storage for contract files (independent bucket).

Shares the same MinIO instance as knowledge storage (ragflow-minio) but uses
a SEPARATE bucket (cpa-contracts) so contract data is physically isolated from
kb-docs. Connection settings come from Config (env), sharing endpoint/creds
with knowledge storage. Also holds per-page OCR preview PNGs for traceback.
"""

import hashlib
import json
from io import BytesIO

from minio import Minio

from scripts.config import Config


class ContractStore:
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

    def has_objects(self, prefix: str) -> bool:
        """前缀下是否存在任意对象(不拉内容)。"""
        for _ in self._client.list_objects(self._bucket, prefix=prefix, max_keys=1):
            return True
        return False

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

    def get_ocr_cache(self, key: str) -> dict | None:
        """OCR 结构化缓存;缺失/损坏/合法JSON但非dict 一律返回 None(回退全量 OCR,
        绝不因缓存挂掉)。"""
        try:
            data = json.loads(self.get(key))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def put_ocr_cache(self, key: str, obj: dict) -> None:
        self.put_bytes(key, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                       content_type="application/json")

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
