"""OmicHub 平台 REST API 客户端"""

from __future__ import annotations

from typing import Any

import httpx

from core.config import settings
from core.logger import logger


class OmicHubAPIError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"[{status_code}] {detail}")


class OmicHubAPIClient:
    """通过 HTTP 调用 OmicHub 平台 REST API，使用 API Key 认证。"""

    def __init__(self) -> None:
        self._base_url = f"{settings.base_url.rstrip('/')}/api/v1"
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=settings.request_timeout,
            headers={"X-API-Key": settings.api_key},
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            resp = await self._client.request(method, path, **kwargs)
        except httpx.ConnectError as e:
            raise OmicHubAPIError(0, f"无法连接到平台: {settings.base_url} ({e})") from e
        except httpx.TimeoutException as e:
            raise OmicHubAPIError(0, f"请求超时 ({settings.request_timeout}s)") from e

        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise OmicHubAPIError(resp.status_code, str(detail))

        if resp.status_code == 204:
            return None
        return resp.json()

    async def get(self, path: str, **kwargs: Any) -> Any:
        return await self._request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> Any:
        return await self._request("POST", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> Any:
        return await self._request("DELETE", path, **kwargs)

    # ===== Tasks =====
    async def list_tasks(self, status: str | None = None) -> dict:
        params = {}
        if status:
            params["status"] = status
        return await self.get("/tasks", params=params)

    async def get_task(self, task_id: str) -> dict:
        return await self.get(f"/tasks/{task_id}")

    async def cancel_task(self, task_id: str) -> dict:
        return await self.post(f"/tasks/{task_id}/cancel")

    async def get_task_dag(self, task_id: str) -> dict:
        return await self.get(f"/tasks/{task_id}/dag")

    # ===== Flows =====
    async def list_flows(self, category: str | None = None) -> dict:
        params = {}
        if category:
            params["category"] = category
        return await self.get("/flows", params=params)

    async def get_flow(self, flow_id: str) -> dict:
        return await self.get(f"/flows/{flow_id}")

    async def get_flow_schema(self, flow_id: str) -> dict:
        return await self.get(f"/flows/{flow_id}/schema")

    # ===== Analysis =====
    async def submit_task(self, payload: dict) -> dict:
        return await self.post("/tasks", json=payload)

    # ===== Downloads =====
    async def list_downloads(self) -> dict:
        return await self.get("/downloads")

    async def submit_download(self, payload: dict) -> dict:
        return await self.post("/downloads", json=payload)

    async def get_download_progress(self, task_id: str) -> dict:
        return await self.get(f"/downloads/{task_id}/progress")

    # ===== Files =====
    async def list_files(self, directory: str | None = None) -> dict:
        params = {}
        if directory:
            params["directory"] = directory
        return await self.get("/files", params=params)

    async def get_file_tree(self) -> dict:
        return await self.get("/files/tree")

    async def list_directories(self) -> list:
        return await self.get("/files/directories")

    async def get_quota(self) -> dict:
        return await self.get("/files/quota")

    async def preview_file(self, path: str, max_lines: int = 50) -> dict:
        return await self.get("/files/preview", params={"path": path, "max_lines": max_lines})

    # ===== Reports =====
    async def list_reports(self, **filters: Any) -> dict:
        params = {k: v for k, v in filters.items() if v is not None}
        return await self.get("/reports", params=params)

    async def get_report(self, report_id: str) -> dict:
        return await self.get(f"/reports/{report_id}")

    async def get_report_content(self, report_id: str) -> str:
        return await self.get(f"/reports/{report_id}/preview")

    # ===== Sandbox =====
    async def sandbox_list_sessions(self) -> list:
        return await self.get("/sandbox/sessions")

    async def sandbox_create_session(self, language: str = "python") -> dict:
        return await self.post("/sandbox/sessions", json={"language": language})

    async def sandbox_execute(self, session_id: str, code: str, timeout: int = 300) -> dict:
        return await self.post(
            f"/sandbox/sessions/{session_id}/execute",
            json={"code": code, "timeout": timeout},
        )

    async def sandbox_delete_session(self, session_id: str) -> dict:
        return await self.delete(f"/sandbox/sessions/{session_id}")

    # ===== User / Platform =====
    async def get_me(self) -> dict:
        return await self.get("/auth/me")

    async def get_stats(self) -> dict:
        return await self.get("/stats/overview")


api = OmicHubAPIClient()
