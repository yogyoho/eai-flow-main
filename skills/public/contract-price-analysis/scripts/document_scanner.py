"""Scan the MinIO bucket for contract files; detect changed via SHA-256.

Incremental detection: a file is "changed" iff its content SHA-256 differs
from the cached hash (cpa_documents.file_hash). This is EXACT — unlike
RAGFlow's synthesized fingerprint, renaming or re-uploading the same content
does NOT trigger a re-parse; only real content changes do.
"""

import logging

from scripts.storage import ContractStore

logger = logging.getLogger(__name__)

_ACCEPTED = (".pdf", ".docx")


def scan_changed(store: ContractStore, cached_meta: dict, force_key: str | None = None) -> list:
    """Return [{key, size, hash}] for new/changed contract objects.

    ``cached_meta`` is {storage_key: {"hash": file_hash, "size": int|None}}.
    Objects under previews/ are derivatives and skipped.

    Size pre-filter (avoids re-downloading the whole bucket every scan): if the
    object's current size matches the cached size, the content is treated as
    unchanged WITHOUT downloading + re-hashing it. ponytail: ceiling — an edit
    that keeps byte-identical size would be missed; recover via single-doc
    reparse (force_key) or a periodic full re-hash. Real contract edits change
    size, so this is safe in practice.

    ``force_key``: if set, re-process ONLY that single object regardless of
    cache (single-document reparse). The object is still hashed for persistence.
    """
    changed = []
    for obj in store.list_objects():
        key = obj.object_name
        if getattr(obj, "is_dir", False) or not key.lower().endswith(_ACCEPTED):
            continue
        if key.startswith("previews/"):
            continue
        if force_key is not None and key != force_key:
            continue
        cached = cached_meta.get(key) or {}
        # 已上传待解析(pending),或已被触发端点提前置为「解析中」(parsing)
        # (开始解析按钮在起子进程前就把 pending→parsing,让前端即时显示解析中)
        # → 始终处理,使文档从 pending/parsing 推进到 parsed。复用缓存 hash
        # (内容自上传后未变),跳过重新下载。
        if force_key is None and cached.get("parse_status") in ("pending", "parsing"):
            changed.append({"key": key, "size": obj.size, "hash": cached.get("hash") or store.sha256(key)})
            continue
        # Cheap gate: size unchanged → trust the cached hash, skip the download.
        if (
            force_key is None
            and cached.get("size") is not None
            and obj.size == cached.get("size")
        ):
            continue
        try:
            digest = store.sha256(key)
        except Exception as exc:
            logger.warning("hash failed for %s: %s", key, exc)
            continue
        if force_key is not None or cached.get("hash") != digest:
            changed.append({"key": key, "size": obj.size, "hash": digest})
    return changed
