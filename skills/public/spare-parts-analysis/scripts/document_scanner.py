# EAI-CUSTOM: forked from contract-price-analysis/scripts/document_scanner.py(域无关,近乎逐字)。
"""Scan the MinIO bucket (csp-parts) for spare-parts contract files; detect changed via SHA-256。

增量检测:仅当内容 SHA-256 与缓存 hash(csp_documents.file_hash)不同才算"变更"。
这是精确的——重命名/重新上传同内容不触发重解析,只有真实内容变化才触发。
"""

import logging

from scripts.storage import SparePartsStore

logger = logging.getLogger(__name__)

_ACCEPTED = (".pdf", ".docx")


def scan_changed(store: SparePartsStore, cached_meta: dict, force_key: str | None = None) -> list:
    """Return [{key, size, hash}] for new/changed contract objects。

    ``cached_meta`` is {storage_key: {"hash": file_hash, "size": int|None, "parse_status": str}}。
    previews/ 下的对象是衍生物,跳过。

    Size 预过滤(免得每次扫描重下整个 bucket):若对象当前 size 与缓存 size 一致,
    视为内容未变,不下载+重 hash。ponytail ceiling——保持字节 size 不变的编辑会漏;
    通过单文档重解析(force_key)或周期性全量重 hash 恢复。真实合同编辑会改 size,实践安全。

    ``force_key``:若设置,仅重处理该单个对象(单文档重解析),忽略缓存。
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
        # → 始终处理,使文档从 pending/parsing 推进到 parsed。复用缓存 hash,
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
