"""httpx AsyncClient wrapper for cross-service HTTP calls."""

import os
from typing import Any, Optional

import httpx


class BusinessAPIClient:
    """HTTP client for calling other business microservices.

    Automatically injects the Authorization header using the shared JWT secret.
    """

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get_token(self) -> Optional[str]:
        """Retrieve access token from localStorage-equivalent environment."""
        return os.environ.get("EAI_ACCESS_TOKEN")

    async def request(
        self,
        method: str,
        path: str,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        token: Optional[str] = None,
    ) -> dict[str, Any]:
        """Make an HTTP request to another business microservice."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        auth_token = token or self._get_token()
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        url = f"{self.base_url}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.request(
                method=method.upper(),
                url=url,
                json=json,
                params=params,
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def get(self, path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, json: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        return await self.request("POST", path, json=json)

    async def put(self, path: str, json: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        return await self.request("PUT", path, json=json)

    async def delete(self, path: str) -> dict[str, Any]:
        return await self.request("DELETE", path)


# Pre-configured clients for known services
def get_procurement_client() -> BusinessAPIClient:
    return BusinessAPIClient(os.environ.get("PROCUREMENT_API_URL", "http://procurement-backend:3001"))


def get_gateway_client() -> BusinessAPIClient:
    return BusinessAPIClient(os.environ.get("EAI_GATEWAY_URL", "http://gateway:4001"))
