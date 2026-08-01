"""HTTP-only adapter for OmicHub's controlled professional consultation endpoint."""

from __future__ import annotations

import httpx

from .config import GatewaySettings
from .models import ConsultationRequest, UpstreamConsultationResponse


class OmicHubConsultationClient:
    def __init__(self, settings: GatewaySettings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(
            base_url=settings.omichub_base_url,
            timeout=settings.request_timeout_seconds,
        )
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def consult(self, request: ConsultationRequest) -> UpstreamConsultationResponse:
        headers = self._auth_headers()
        payload = {
            "case_id": request.case_id,
            "agent_id": request.agent_id,
            "question": request.question,
            "capability": request.capability,
            "evidence_refs": request.evidence_refs,
            "requested_tools": request.requested_tools,
            "read_only": True,
            "allow_task_actions": False,
            "allow_file_write": False,
            "allow_database_access": False,
            "allow_shell": False,
        }
        response = await self._client.post(
            self._settings.omichub_consultation_path,
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        return UpstreamConsultationResponse.model_validate(response.json())

    def _auth_headers(self) -> dict[str, str]:
        if self._settings.omichub_service_token:
            return {"Authorization": f"Bearer {self._settings.omichub_service_token}"}
        if self._settings.omichub_api_key:
            return {"X-API-Key": self._settings.omichub_api_key}
        return {}
