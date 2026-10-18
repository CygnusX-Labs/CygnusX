"""Authenticated HTTP client for an independently deployed download Supervisor.

This module is only the Worker-side control-plane client. It does not create
namespaces, enforce egress or quotas, or prove that a remote endpoint is a real
Supervisor; those guarantees belong to the separately managed server and host.
"""

from __future__ import annotations

import json
import ssl
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cygnusx.core.config import Settings, get_settings
from cygnusx.infrastructure.download.trusted_execution import (
    ExecutionBoundaryObservation,
    ExecutionBoundaryRequest,
    ExecutionPublicationContext,
)

_MAX_CONTROL_RESPONSE_BYTES = 64 * 1024


class _StartExecutionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    supervisor_id: str = Field(min_length=1, max_length=128)
    task_id: UUID
    scope_ref: UUID
    execution_id: UUID
    execution_epoch: int = Field(gt=0)


class TrustedExecutionUnavailableError(RuntimeError):
    """Supervisor request failed or returned an invalid identity-bound response."""


class MutualTLSExecutionAdapter:
    """Fail-closed client for the existing Task's authenticated Supervisor scope.

    The server contract is POST /v1/executions, GET the returned execution path,
    then POST its /lease or /stop subresource. Calls are never retried because a
    timed-out start/stop may have completed remotely and must be reconciled.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.base_url = self._validated_base_url(self.settings.download_execution_supervisor_url)
        self.supervisor_id = self.settings.download_execution_supervisor_id
        if not self.supervisor_id:
            raise ValueError("DOWNLOAD_SUPERVISOR_ID_MISSING")

        if transport is not None:
            if self.settings.app_env not in {"test", "acceptance"}:
                raise ValueError("DOWNLOAD_SUPERVISOR_TEST_TRANSPORT_FORBIDDEN")
            verify: ssl.SSLContext | bool = True
        else:
            ca_file = self.settings.download_execution_supervisor_ca_file
            cert_file = self.settings.download_execution_client_cert_file
            key_file = self.settings.download_execution_client_key_file
            if not ca_file or not cert_file or not key_file:
                raise ValueError("DOWNLOAD_SUPERVISOR_MTLS_CONFIG_MISSING")
            verify = ssl.create_default_context(cafile=ca_file)
            verify.load_cert_chain(certfile=cert_file, keyfile=key_file)

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.settings.download_execution_supervisor_timeout_seconds),
            verify=verify,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    @staticmethod
    def _validated_base_url(value: str | None) -> str:
        if not value:
            raise ValueError("DOWNLOAD_SUPERVISOR_URL_MISSING")
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("DOWNLOAD_SUPERVISOR_URL_INVALID")
        return value.rstrip("/")

    async def start(self, request: ExecutionBoundaryRequest) -> UUID:
        body = await self._json_request("POST", "/v1/executions", request.model_dump(mode="json"))
        try:
            response = _StartExecutionResponse.model_validate_json(json.dumps(body))
        except ValidationError as exc:
            raise TrustedExecutionUnavailableError("DOWNLOAD_SUPERVISOR_RESPONSE_INVALID") from exc
        if (
            response.supervisor_id != self.supervisor_id
            or response.task_id != request.task_id
            or response.execution_id != request.execution_id
            or response.execution_epoch != request.execution_epoch
        ):
            raise TrustedExecutionUnavailableError("DOWNLOAD_SUPERVISOR_IDENTITY_MISMATCH")
        return response.scope_ref

    async def observe(self, task_id: UUID, scope_ref: UUID) -> ExecutionBoundaryObservation:
        return await self._observation_request("GET", task_id, scope_ref)

    async def renew(self, task_id: UUID, scope_ref: UUID) -> None:
        path = self._execution_path(task_id, scope_ref) + "/lease"
        response = await self._request("POST", path)
        if response.status_code != 204:
            raise TrustedExecutionUnavailableError("DOWNLOAD_SUPERVISOR_LEASE_RESPONSE_INVALID")

    async def stop(self, task_id: UUID, scope_ref: UUID) -> ExecutionBoundaryObservation:
        return await self._observation_request("POST", task_id, scope_ref, suffix="/stop")

    async def evidence(
        self, request: ExecutionBoundaryRequest, scope_ref: UUID
    ) -> ExecutionPublicationContext:
        """Fetch and identity-check the Supervisor's signed publication context."""
        path = self._execution_path(request.task_id, scope_ref) + "/evidence"
        body = await self._json_request("GET", path)
        try:
            context = ExecutionPublicationContext.model_validate_json(json.dumps(body))
        except ValidationError as exc:
            raise TrustedExecutionUnavailableError("DOWNLOAD_SUPERVISOR_EVIDENCE_INVALID") from exc
        claims = context.receipt.claims
        observation = claims.observation
        if (
            context.scope_ref != scope_ref
            or claims.supervisor_id != self.supervisor_id
            or claims.task_id != request.task_id
            or claims.scope_ref != scope_ref
            or claims.attempt_id != request.attempt_id
            or context.attempt_id != request.attempt_id
            or claims.execution_id != request.execution_id
            or context.execution_id != request.execution_id
            or claims.execution_epoch != request.execution_epoch
            or context.execution_epoch != request.execution_epoch
            or claims.policy_revision != context.policy_revision
            or claims.environment_id != context.environment_id
            or claims.binary_sha256 != context.binary_sha256
            or observation.task_id != request.task_id
            or observation.scope_ref != scope_ref
            or observation.execution_id != context.execution_id
            or observation.execution_epoch != context.execution_epoch
            or observation.policy_revision != context.policy_revision
        ):
            raise TrustedExecutionUnavailableError("DOWNLOAD_SUPERVISOR_IDENTITY_MISMATCH")
        return context

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _observation_request(
        self, method: str, task_id: UUID, scope_ref: UUID, *, suffix: str = ""
    ) -> ExecutionBoundaryObservation:
        path = self._execution_path(task_id, scope_ref) + suffix
        body = await self._json_request(method, path)
        try:
            observation = ExecutionBoundaryObservation.model_validate_json(json.dumps(body))
        except ValidationError as exc:
            raise TrustedExecutionUnavailableError(
                "DOWNLOAD_SUPERVISOR_OBSERVATION_INVALID"
            ) from exc
        if observation.task_id != task_id or observation.scope_ref != scope_ref:
            raise TrustedExecutionUnavailableError("DOWNLOAD_SUPERVISOR_IDENTITY_MISMATCH")
        return observation

    async def _json_request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        response = await self._request(method, path, body)
        try:
            payload = response.json()
        except ValueError as exc:
            raise TrustedExecutionUnavailableError("DOWNLOAD_SUPERVISOR_RESPONSE_INVALID") from exc
        if not isinstance(payload, dict):
            raise TrustedExecutionUnavailableError("DOWNLOAD_SUPERVISOR_RESPONSE_INVALID")
        return payload

    async def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> httpx.Response:
        response: httpx.Response | None = None
        try:
            request = self._client.build_request(
                method, path, json=body, headers={"accept-encoding": "identity"}
            )
            response = await self._client.send(request, stream=True)
            response.raise_for_status()
            content_encoding = response.headers.get("content-encoding", "identity").lower()
            if content_encoding != "identity":
                raise TrustedExecutionUnavailableError(
                    "DOWNLOAD_SUPERVISOR_RESPONSE_ENCODING_UNSUPPORTED"
                )
            payload = bytearray()
            if response.is_stream_consumed:
                if self.settings.app_env not in {"test", "acceptance"}:
                    raise TrustedExecutionUnavailableError(
                        "DOWNLOAD_SUPERVISOR_RESPONSE_NOT_STREAMED"
                    )
                if len(response.content) > _MAX_CONTROL_RESPONSE_BYTES:
                    raise TrustedExecutionUnavailableError("DOWNLOAD_SUPERVISOR_RESPONSE_TOO_LARGE")
                payload.extend(response.content)
            else:
                async for chunk in response.aiter_raw():
                    if len(payload) + len(chunk) > _MAX_CONTROL_RESPONSE_BYTES:
                        raise TrustedExecutionUnavailableError(
                            "DOWNLOAD_SUPERVISOR_RESPONSE_TOO_LARGE"
                        )
                    payload.extend(chunk)
            return httpx.Response(
                status_code=response.status_code,
                headers=response.headers,
                content=bytes(payload),
                request=request,
            )
        except TrustedExecutionUnavailableError:
            raise
        except httpx.HTTPError as exc:
            raise TrustedExecutionUnavailableError("DOWNLOAD_SUPERVISOR_REQUEST_FAILED") from exc
        finally:
            if response is not None:
                await response.aclose()

    @staticmethod
    def _execution_path(task_id: UUID, scope_ref: UUID) -> str:
        return f"/v1/executions/{task_id}/{scope_ref}"
