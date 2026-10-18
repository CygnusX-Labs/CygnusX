from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from cygnusx.core.config import Settings
from cygnusx.infrastructure.download.supervisor_client import (
    MutualTLSExecutionAdapter,
    TrustedExecutionUnavailableError,
)
from cygnusx.infrastructure.download.trusted_execution import (
    ExecutionBoundaryObservation,
    ExecutionBoundaryRequest,
    ExecutionPublicationContext,
    ExecutionReceiptClaims,
    SignedExecutionReceipt,
)

pytestmark = pytest.mark.unit


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "test",
        "download_execution_supervisor_id": "supervisor-test",
        "download_execution_supervisor_url": "https://supervisor.test",
    }
    values.update(overrides)
    return Settings.model_validate(values)


def _request() -> ExecutionBoundaryRequest:
    return ExecutionBoundaryRequest(
        task_id=uuid4(),
        owner_id=uuid4(),
        attempt_id=uuid4(),
        execution_id=uuid4(),
        execution_epoch=3,
        admission_ref=uuid4(),
        budget_ref=uuid4(),
    )


def _observation(task_id: UUID, scope_ref: UUID) -> dict[str, object]:
    return ExecutionBoundaryObservation(
        task_id=task_id,
        scope_ref=scope_ref,
        execution_id=uuid4(),
        execution_epoch=3,
        policy_revision="http-policy-v1",
        state="stopped",
        reason="completed",
        rx_admitted_bytes=100,
        rx_observed_bytes=100,
        rx_dropped_bytes=0,
        rx_limit_bytes=1000,
        disk_peak_allocated_bytes=100,
        disk_limit_bytes=1000,
        inode_peak_used=1,
        inode_limit=10,
        started_at=100,
        stopped_at=101,
        live_processes=0,
        cgroup_populated=False,
        egress_revoked=True,
        quota_enforced=True,
        cleanup_complete=True,
        returncode=0,
    ).model_dump(mode="json")


def _publication_context(request: ExecutionBoundaryRequest, scope_ref: UUID) -> dict[str, Any]:
    observation_payload = _observation(request.task_id, scope_ref)
    observation_payload["execution_id"] = str(request.execution_id)
    observation_payload["execution_epoch"] = request.execution_epoch
    observation = ExecutionBoundaryObservation.model_validate_json(json.dumps(observation_payload))
    attempt_id = request.attempt_id
    context = ExecutionPublicationContext(
        scope_ref=scope_ref,
        attempt_id=attempt_id,
        execution_id=observation.execution_id,
        execution_epoch=observation.execution_epoch,
        policy_revision=observation.policy_revision,
        environment_id="http-small-v1",
        binary_sha256="a" * 64,
        receipt=SignedExecutionReceipt(
            claims=ExecutionReceiptClaims(
                supervisor_id="supervisor-test",
                task_id=request.task_id,
                attempt_id=attempt_id,
                execution_id=observation.execution_id,
                scope_ref=scope_ref,
                execution_epoch=observation.execution_epoch,
                policy_revision=observation.policy_revision,
                environment_id="http-small-v1",
                binary_sha256="a" * 64,
                nonce=uuid4(),
                issued_at=100,
                expires_at=120,
                artifact_manifest_sha256="b" * 64,
                observation=observation,
            ),
            signature="c" * 88,
        ),
    )
    return context.model_dump(mode="json")


def test_supervisor_url_must_use_https_without_userinfo_or_query() -> None:
    for url in (
        "http://supervisor.test",
        "https://user@supervisor.test",
        "https://supervisor.test?redirect=http://other.test",
        "https://supervisor.test/#fragment",
    ):
        with pytest.raises(ValueError, match="DOWNLOAD_SUPERVISOR_URL_INVALID"):
            MutualTLSExecutionAdapter(
                settings=_settings(download_execution_supervisor_url=url),
                transport=httpx.MockTransport(lambda request: httpx.Response(500)),
            )


def test_mtls_configuration_is_required_without_test_transport() -> None:
    with pytest.raises(ValueError, match="DOWNLOAD_SUPERVISOR_MTLS_CONFIG_MISSING"):
        MutualTLSExecutionAdapter(
            settings=_settings(app_env="acceptance"),
        )


async def test_start_sends_only_typed_identity_and_checks_ack_binding() -> None:
    request = _request()
    scope_ref = uuid4()

    async def respond(incoming: httpx.Request) -> httpx.Response:
        assert incoming.method == "POST"
        assert incoming.url.path == "/v1/executions"
        assert json.loads(incoming.read()) == request.model_dump(mode="json")
        return httpx.Response(
            200,
            json={
                "supervisor_id": "supervisor-test",
                "task_id": str(request.task_id),
                "scope_ref": str(scope_ref),
                "execution_id": str(request.execution_id),
                "execution_epoch": request.execution_epoch,
            },
        )

    adapter = MutualTLSExecutionAdapter(
        settings=_settings(), transport=httpx.MockTransport(respond)
    )
    try:
        assert await adapter.start(request) == scope_ref
    finally:
        await adapter.aclose()


async def test_start_rejects_ack_for_another_execution() -> None:
    request = _request()

    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "supervisor_id": "supervisor-test",
                "task_id": str(request.task_id),
                "scope_ref": str(uuid4()),
                "execution_id": str(uuid4()),
                "execution_epoch": request.execution_epoch,
            },
        )

    adapter = MutualTLSExecutionAdapter(
        settings=_settings(), transport=httpx.MockTransport(respond)
    )
    try:
        with pytest.raises(TrustedExecutionUnavailableError, match="IDENTITY_MISMATCH"):
            await adapter.start(request)
    finally:
        await adapter.aclose()


async def test_observe_and_stop_require_task_and_scope_match() -> None:
    task_id, scope_ref = uuid4(), uuid4()
    calls: list[str] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path.endswith("/stop"):
            return httpx.Response(200, json=_observation(task_id, scope_ref))
        return httpx.Response(200, json=_observation(uuid4(), scope_ref))

    adapter = MutualTLSExecutionAdapter(
        settings=_settings(), transport=httpx.MockTransport(respond)
    )
    try:
        with pytest.raises(TrustedExecutionUnavailableError, match="IDENTITY_MISMATCH"):
            await adapter.observe(task_id, scope_ref)
        observation = await adapter.stop(task_id, scope_ref)
        assert observation.task_id == task_id
        assert calls == [
            f"GET /v1/executions/{task_id}/{scope_ref}",
            f"POST /v1/executions/{task_id}/{scope_ref}/stop",
        ]
    finally:
        await adapter.aclose()


async def test_evidence_returns_signed_context_bound_to_original_execution_request() -> None:
    request, scope_ref = _request(), uuid4()

    async def respond(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == f"/v1/executions/{request_task_id}/{scope_ref}/evidence"
        return httpx.Response(200, json=_publication_context(execution_request, scope_ref))

    execution_request = request
    request_task_id = execution_request.task_id

    adapter = MutualTLSExecutionAdapter(
        settings=_settings(), transport=httpx.MockTransport(respond)
    )
    try:
        context = await adapter.evidence(execution_request, scope_ref)
        assert context.scope_ref == scope_ref
        assert context.receipt.claims.task_id == execution_request.task_id
        assert context.receipt.claims.supervisor_id == "supervisor-test"
    finally:
        await adapter.aclose()


@pytest.mark.parametrize(
    "binding",
    [
        "supervisor",
        "task",
        "scope",
        "attempt",
        "execution",
        "epoch",
        "policy",
        "environment",
        "binary",
        "observation",
    ],
)
async def test_evidence_rejects_identity_binding_mismatch(binding: str) -> None:
    execution_request, scope_ref = _request(), uuid4()
    payload = _publication_context(execution_request, scope_ref)
    context = payload
    claims = context["receipt"]["claims"]
    observation = claims["observation"]
    if binding == "supervisor":
        claims["supervisor_id"] = "different-supervisor"
    elif binding == "task":
        task_id = str(uuid4())
        claims["task_id"] = observation["task_id"] = task_id
    elif binding == "scope":
        scope = str(uuid4())
        context["scope_ref"] = claims["scope_ref"] = observation["scope_ref"] = scope
    elif binding == "attempt":
        attempt_id = str(uuid4())
        context["attempt_id"] = claims["attempt_id"] = attempt_id
    elif binding == "execution":
        execution_id = str(uuid4())
        context["execution_id"] = claims["execution_id"] = observation["execution_id"] = (
            execution_id
        )
    elif binding == "epoch":
        epoch = execution_request.execution_epoch + 1
        context["execution_epoch"] = claims["execution_epoch"] = observation[
            "execution_epoch"
        ] = epoch
    elif binding == "policy":
        policy = "different-policy"
        claims["policy_revision"] = policy
    elif binding == "environment":
        claims["environment_id"] = "different-environment"
    elif binding == "binary":
        claims["binary_sha256"] = "d" * 64
    else:
        observation["policy_revision"] = "different-observation-policy"

    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    adapter = MutualTLSExecutionAdapter(
        settings=_settings(), transport=httpx.MockTransport(respond)
    )
    try:
        with pytest.raises(TrustedExecutionUnavailableError, match="IDENTITY_MISMATCH"):
            await adapter.evidence(execution_request, scope_ref)
    finally:
        await adapter.aclose()


async def test_lease_requires_no_redirect_and_is_never_replayed() -> None:
    task_id, scope_ref = uuid4(), uuid4()
    calls = 0

    async def respond(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(307, headers={"Location": "https://other.test/lease"})

    adapter = MutualTLSExecutionAdapter(
        settings=_settings(), transport=httpx.MockTransport(respond)
    )
    try:
        with pytest.raises(TrustedExecutionUnavailableError, match="REQUEST_FAILED"):
            await adapter.renew(task_id, scope_ref)
        assert calls == 1
    finally:
        await adapter.aclose()


async def test_oversized_control_response_is_rejected() -> None:
    class ChunkedBody(httpx.AsyncByteStream):
        def __init__(self) -> None:
            self.chunks_yielded = 0
            self.closed = False

        async def __aiter__(self) -> AsyncIterator[bytes]:
            for _ in range(4):
                self.chunks_yielded += 1
                yield b"x" * (32 * 1024)

        async def aclose(self) -> None:
            self.closed = True

    stream = ChunkedBody()

    async def respond(request: httpx.Request) -> httpx.Response:
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(200, stream=stream)

    adapter = MutualTLSExecutionAdapter(
        settings=_settings(), transport=httpx.MockTransport(respond)
    )
    try:
        with pytest.raises(TrustedExecutionUnavailableError, match="RESPONSE_TOO_LARGE"):
            await adapter.observe(uuid4(), uuid4())
        assert stream.chunks_yielded == 3
        assert stream.closed

        encoded_stream = ChunkedBody()

        async def compressed_response(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-encoding": "gzip"},
                stream=encoded_stream,
            )

        compressed_adapter = MutualTLSExecutionAdapter(
            settings=_settings(), transport=httpx.MockTransport(compressed_response)
        )
        try:
            with pytest.raises(
                TrustedExecutionUnavailableError, match="RESPONSE_ENCODING_UNSUPPORTED"
            ):
                await compressed_adapter.observe(uuid4(), uuid4())
            assert encoded_stream.chunks_yielded == 0
            assert encoded_stream.closed
        finally:
            await compressed_adapter.aclose()
    finally:
        await adapter.aclose()
