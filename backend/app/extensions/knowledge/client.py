"""RAGFlow client for knowledge base integration."""

import asyncio
import json
import logging
from typing import Optional

import httpx

from app.extensions.config import get_extensions_config

logger = logging.getLogger(__name__)


class RAGFlowClient:
    """RAGFlow API client."""

    PARSE_STATUS_PENDING = "pending"
    PARSE_STATUS_PARSING = "parsing"
    PARSE_STATUS_SUCCESS = "success"
    PARSE_STATUS_FAILED = "failed"

    API_PREFIX = "/api/v1"

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        config = get_extensions_config()
        self.api_key = api_key or config.ragflow.api_key
        self.base_url = base_url or config.ragflow.base_url
        self.timeout = config.ragflow.timeout

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        max_retries: int = 3,
        **kwargs
    ) -> httpx.Response:
        """Send request with automatic retry."""
        retry_count = 0
        last_error = None

        while retry_count < max_retries:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(method, url, **kwargs)
                    response.raise_for_status()
                    return response
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                last_error = e
                retry_count += 1
                if retry_count < max_retries:
                    wait_time = 2 ** retry_count
                    logger.warning(f"Request failed (attempt {retry_count}/{max_retries}): {e}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Request failed after {max_retries} attempts: {e}")

        raise last_error

    async def create_dataset(
        self,
        name: str,
        description: str = "",
        embedding_model: Optional[str] = None
    ) -> dict:
        """Create a new dataset in RAGFlow."""
        payload = {"name": name, "description": description}
        if embedding_model:
            payload["embedding_model"] = embedding_model

        async with httpx.AsyncClient(timeout=self.timeout * 20) as client:
            response = await client.post(
                f"{self.base_url}{self.API_PREFIX}/datasets",
                headers=self._get_headers(),
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"Created RAGFlow dataset: {name} (id: {result.get('data', {}).get('id')})")
            return result

    async def get_dataset(self, dataset_id: str) -> dict:
        """Get dataset details by listing and filtering."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/kb/list",
                headers=self._get_headers(),
                json={"page": 1, "size": 100},
            )
            response.raise_for_status()
            result = response.json()
            kbs = result.get("data", {}).get("kbs", []) or []
            for ds in kbs:
                if ds.get("id") == dataset_id:
                    return {"data": ds}
            return {"data": None}

    async def list_datasets(self, page: int = 1, size: int = 100) -> dict:
        """List all datasets."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/kb/list",
                headers=self._get_headers(),
                json={"page": page, "size": size},
            )
            response.raise_for_status()
            return response.json()

    async def update_dataset(self, dataset_id: str, name: str = None, description: str = None) -> dict:
        """Update dataset info."""
        payload = {}
        if name:
            payload["name"] = name
        if description:
            payload["description"] = description

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.put(
                f"{self.base_url}{self.API_PREFIX}/datasets/{dataset_id}",
                headers=self._get_headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def delete_dataset(self, dataset_id: str) -> None:
        """Delete a dataset from RAGFlow."""
        import urllib.request
        import urllib.error

        url = f"{self.base_url}{self.API_PREFIX}/datasets"
        body = json.dumps({"ids": [dataset_id]}).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read().decode())
                if result.get("code") == 0:
                    logger.info(f"Deleted RAGFlow dataset: {dataset_id}")
                else:
                    logger.warning(f"RAGFlow delete response: {result}")
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            logger.error(f"Failed to delete RAGFlow dataset {dataset_id}: HTTP {e.code} - {error_body}")
            raise httpx.HTTPStatusError(error_body, request=req, response=e)
        except Exception as e:
            logger.error(f"Failed to delete RAGFlow dataset {dataset_id}: {e}")
            raise

    async def upload_document(
        self,
        dataset_id: str,
        file_path: str,
        file_name: str = None
    ) -> dict:
        """Upload a document to a dataset."""
        import os

        if file_name is None:
            file_name = os.path.basename(file_path)

        async with httpx.AsyncClient(timeout=self.timeout * 2) as client:
            with open(file_path, "rb") as f:
                files = {"file": (file_name, f)}
                headers = {"Authorization": f"Bearer {self.api_key}"}
                response = await client.post(
                    f"{self.base_url}{self.API_PREFIX}/datasets/{dataset_id}/documents",
                    files=files,
                    headers=headers,
                )
            response.raise_for_status()
            result = response.json()
            data = result.get("data", [])
            if isinstance(data, list) and data:
                result = {"data": data[0]}
            logger.info(f"Uploaded document to RAGFlow dataset {dataset_id}: {file_name}")
            return result

    async def get_document(self, dataset_id: str, document_id: str) -> dict:
        """Get document details."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}{self.API_PREFIX}/datasets/{dataset_id}/documents",
                headers=self._get_headers(),
                params={"page": 1, "limit": 100},
            )
            response.raise_for_status()
            result = response.json()
            docs = (result.get("data") or {}).get("docs", [])
            for doc in docs:
                if doc.get("id") == document_id:
                    return {"data": doc}
            return {"data": {}}

    async def list_documents(self, dataset_id: str, page: int = 1, size: int = 100) -> dict:
        """List documents in a dataset."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}{self.API_PREFIX}/datasets/{dataset_id}/documents",
                headers=self._get_headers(),
                params={"page": page, "limit": size},
            )
            response.raise_for_status()
            return response.json()

    async def delete_document(self, dataset_id: str, document_id: str) -> None:
        """Delete a document."""
        import urllib.request
        import urllib.error

        url = f"{self.base_url}{self.API_PREFIX}/datasets/{dataset_id}/documents"
        body = json.dumps({"ids": [document_id]}).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                logger.info(f"Deleted RAGFlow document: {document_id} from dataset {dataset_id}")
        except urllib.error.HTTPError as e:
            raise httpx.HTTPStatusError(str(e), request=None, response=None) from e

    async def parse_document(self, dataset_id: str, document_id: str) -> dict:
        """Trigger document parsing/embedding."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}{self.API_PREFIX}/datasets/{dataset_id}/chunks",
                headers=self._get_headers(),
                json={"document_ids": [document_id]},
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"Triggered parsing for document {document_id} in dataset {dataset_id}")
            return result

    async def list_chunks(self, dataset_id: str, document_id: str, page: int = 1, size: int = 100) -> dict:
        """List chunks of a document."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}{self.API_PREFIX}/datasets/{dataset_id}/documents/{document_id}/chunks",
                headers=self._get_headers(),
                params={"page": page, "size": size},
            )
            response.raise_for_status()
            return response.json()

    async def get_parsing_status(self, dataset_id: str, document_id: str) -> dict:
        """Get document parsing status."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}{self.API_PREFIX}/datasets/{dataset_id}/documents",
                headers=self._get_headers(),
                params={"page": 1, "limit": 100},
            )
            response.raise_for_status()
            result = response.json()
            docs = (result.get("data") or {}).get("docs", [])
            for doc in docs:
                if doc.get("id") == document_id:
                    return {"data": doc}
            return {"data": {}}

    async def wait_for_parsing_complete(
        self,
        dataset_id: str,
        document_id: str,
        max_wait_seconds: int = 300,
        poll_interval: int = 5
    ) -> dict:
        """Wait for document parsing to complete."""
        elapsed = 0
        while elapsed < max_wait_seconds:
            status_result = await self.get_parsing_status(dataset_id, document_id)
            data = status_result.get("data", {})
            parse_status = data.get("status", self.PARSE_STATUS_PENDING)

            if parse_status == self.PARSE_STATUS_SUCCESS:
                logger.info(f"Document {document_id} parsing completed successfully")
                return status_result
            elif parse_status == self.PARSE_STATUS_FAILED:
                error_msg = data.get("error", "Unknown error")
                logger.error(f"Document {document_id} parsing failed: {error_msg}")
                return status_result
            elif parse_status == self.PARSE_STATUS_PARSING:
                progress = data.get("progress", 0)
                logger.debug(f"Document {document_id} parsing progress: {progress}%")

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(f"Document parsing timeout after {max_wait_seconds}s")

    async def chat(
        self,
        dataset_id: str,
        query: str,
        top_k: int = 5,
        similarity_threshold: float = 0.2,
        vector_similarity_weight: float = 0.3
    ) -> dict:
        """Retrieve chunks from a dataset (RAG query)."""
        async with httpx.AsyncClient(timeout=self.timeout * 2) as client:
            response = await client.post(
                f"{self.base_url}{self.API_PREFIX}/retrieval",
                headers=self._get_headers(),
                json={
                    "question": query,
                    "dataset_ids": [dataset_id],
                    "top_k": top_k,
                    "similarity_threshold": similarity_threshold,
                    "vector_similarity_weight": vector_similarity_weight,
                },
            )
            response.raise_for_status()
            return response.json()

    async def is_available(self) -> bool:
        """Check if RAGFlow service is available."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(
                    f"{self.base_url}{self.API_PREFIX}/datasets",
                    headers=self._get_headers(),
                )
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"RAGFlow service unavailable: {e}")
            return False

    async def get_dataset_statistics(self, dataset_id: str) -> dict:
        """Get dataset statistics."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}{self.API_PREFIX}/datasets/{dataset_id}/statistics",
                headers=self._get_headers(),
            )
            response.raise_for_status()
            return response.json()

    async def get_dataset_by_name(self, name: str) -> Optional[dict]:
        """Get dataset by name."""
        try:
            result = await self.list_datasets()
            kbs = result.get("data", {}).get("kbs", []) or result.get("data", [])
            for kb in kbs:
                if kb.get("name") == name:
                    return kb
            return None
        except Exception as e:
            logger.error(f"Failed to get dataset by name {name}: {e}")
            return None

    async def update_document_metadata(
        self, dataset_id: str, document_id: str, metadata: dict
    ) -> dict:
        """Update document metadata."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.put(
                f"{self.base_url}{self.API_PREFIX}/datasets/{dataset_id}/documents/{document_id}",
                headers=self._get_headers(),
                json=metadata,
            )
            response.raise_for_status()
            return response.json()
