"""The sole HTTP adapter to OmicHub's public API."""

from __future__ import annotations

from typing import Any

import httpx

from .config import BridgeSettings


class OmicHubClient:
    def __init__(self, settings: BridgeSettings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(
            base_url=settings.omichub_base_url.rstrip("/"),
            timeout=settings.request_timeout_seconds,
        )
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def list_flows(self) -> dict[str, Any]:
        return await self._request("GET", "/api/v1/flows")

    async def get_flow_schema(self, flow_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/flows/{flow_id}/schema")

    async def submit_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/api/v1/tasks", json=payload)

    async def get_task(self, task_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/tasks/{task_id}")

    async def cancel_task(self, task_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/api/v1/tasks/{task_id}/cancel")

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = kwargs.pop("headers", {})
        if self._settings.omichub_api_key:
            headers["X-API-Key"] = self._settings.omichub_api_key
        elif self._settings.omichub_service_token:
            headers["Authorization"] = f"Bearer {self._settings.omichub_service_token}"
        response = await self._client.request(method, path, headers=headers, **kwargs)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise httpx.HTTPStatusError(
                "OmicHub response must be an object", request=response.request, response=response
            )
        return data
