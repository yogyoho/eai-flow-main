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


def scan_changed(store: ContractStore, cached_hashes: dict) -> list:
    """Return [{key, size, hash}] for new/changed contract objects.

    ``cached_hashes`` is {storage_key: file_hash}. Objects under previews/ are
    derivatives and skipped.
    """
    changed = []
    for obj in store.list_objects():
        key = obj.object_name
        if getattr(obj, "is_dir", False) or not key.lower().endswith(_ACCEPTED):
            continue
        if key.startswith("previews/"):
            continue
        try:
            digest = store.sha256(key)
        except Exception as exc:
            logger.warning("hash failed for %s: %s", key, exc)
            continue
        if cached_hashes.get(key) != digest:
            changed.append({"key": key, "size": obj.size, "hash": digest})
    return changed
