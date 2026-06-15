"""RAGFlow REST API client with incremental change detection.

Talks to a RAGFlow server (``http://localhost:9380/api/v1`` by default) and the
contract knowledge base identified by ``RAGFLOW_KB_ID``. Only the list-document +
chunk-retrieval + change-filter concerns live here — parsing happens downstream.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class RagflowError(RuntimeError):
    """Raised when RAGFlow returns a non-zero ``code`` in its JSON envelope."""


def _extract_list(data: Any) -> list[dict[str, Any]]:
    """Normalize RAGFlow ``data`` into a list.

    RAGFlow sometimes returns the list directly (``data: [...]``) and sometimes
    nested (``data: {"docs": [...], "total": N}`` or ``data: {"chunks": [...]}``).
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("docs", "chunks", "data", "items"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def doc_fingerprint(doc: dict[str, Any]) -> str:
    """Stable change signal for a RAGFlow document.

    RAGFlow documents do not expose a content ``hash``, so synthesize a
    fingerprint from the mutable fields that actually change on re-upload or
    re-parse: name, update/create time, chunk count, and parse progress. When a
    real ``hash`` IS present (some API versions), prefer it.
    """
    if doc.get("hash"):
        return str(doc["hash"])
    parts = [
        str(doc.get("name", "")),
        str(doc.get("update_time") or doc.get("create_time") or ""),
        str(doc.get("chunk_count", "")),
        str(doc.get("progress", "")),
    ]
    return "|".join(parts)


class RagflowClient:
    def __init__(self, base_url: str, api_key: str, kb_id: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.kb_id = kb_id
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    async def list_documents(self) -> list[dict[str, Any]]:
        """List all documents in the knowledge base. Returns raw doc dicts.

        Handles pagination by walking pages until a short page is returned.
        Robust to RAGFlow's two response shapes: ``data`` as a list, or
        ``data.docs`` as a list (with ``data.total``).
        """
        docs: list[dict[str, Any]] = []
        page = 1
        page_size = 1000
        while True:
            resp = await self._http.get(
                f"/datasets/{self.kb_id}/documents",
                params={
                    "page": page,
                    "page_size": page_size,
                    "orderby": "create_time",
                    "desc": True,
                },
            )
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") != 0:
                raise RagflowError(f"RAGFlow error listing documents: {body}")
            batch = _extract_list(body.get("data"))
            docs.extend(batch)
            if len(batch) < page_size:
                break
            page += 1
        return docs

    async def get_document_chunks(self, doc_id: str) -> list[dict[str, Any]]:
        """Retrieve parsed chunks (text + tables) for a document."""
        resp = await self._http.get(
            f"/datasets/{self.kb_id}/documents/{doc_id}/chunks",
            params={"page": 1, "page_size": 1000},
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != 0:
            raise RagflowError(f"RAGFlow error fetching chunks for {doc_id}: {body}")
        return _extract_list(body.get("data"))

    async def close(self) -> None:
        await self._http.aclose()

    @staticmethod
    def filter_changed(
        remote_docs: list[dict[str, Any]], cached_hashes: dict[str, str]
    ) -> list[dict[str, Any]]:
        """Return only docs that are new or whose fingerprint changed since last cache.

        ``remote_docs`` items carry ``id``. The change signal is ``doc_fingerprint``:
        RAGFlow documents do NOT expose a content ``hash``, so a fingerprint is
        synthesized from the available mutable fields (name + update/create time +
        chunk_count + progress) to detect re-parses and renames.
        """
        changed: list[dict[str, Any]] = []
        for doc in remote_docs:
            doc_id = doc.get("id")
            if doc_id is None:
                continue
            new_fp = doc_fingerprint(doc)
            if cached_hashes.get(doc_id) != new_fp:
                changed.append(doc)
        return changed


async def list_documents(cfg) -> list[dict[str, Any]]:
    """Convenience wrapper: open a client, list docs, close it."""
    client = RagflowClient(cfg.ragflow_base_url, cfg.ragflow_api_key, cfg.ragflow_kb_id)
    try:
        return await client.list_documents()
    finally:
        await client.close()
