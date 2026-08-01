"""Policy enforcement, cost guarding, response sanitization, and audit for consultations."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict

import httpx
from pydantic import ValidationError

from .audit import AuditStore
from .client import OmicHubConsultationClient
from .config import GatewaySettings
from .models import ConsultationError, ConsultationRequest, ScientificInterpretationResponse


class GatewayService:
    def __init__(
        self,
        settings: GatewaySettings,
        client: OmicHubConsultationClient,
        audit: AuditStore,
    ) -> None:
        self._settings = settings
        self._client = client
        self._audit = audit
        self._case_calls: dict[str, int] = defaultdict(int)
        self._case_tokens: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def consult(
        self, request: ConsultationRequest, actor: str
    ) -> ScientificInterpretationResponse:
        started_at = time.perf_counter()
        policy_error = self._policy_error(request)
        if policy_error:
            return await self._reject(request, actor, started_at, policy_error)
        reservation_error = await self._reserve_call(request.case_id)
        if reservation_error:
            return await self._reject(request, actor, started_at, reservation_error)
        try:
            upstream = await asyncio.wait_for(
                self._client.consult(request), timeout=self._settings.request_timeout_seconds
            )
        except TimeoutError:
            return await self._manual_review(
                request,
                actor,
                started_at,
                "UPSTREAM_TIMEOUT",
                "Professional consultation timed out; manual review is required.",
            )
        except (httpx.HTTPError, ValidationError):
            return await self._manual_review(
                request,
                actor,
                started_at,
                "UPSTREAM_UNAVAILABLE",
                "Professional consultation failed; manual review is required.",
            )
        token_error = await self._consume_tokens(request.case_id, upstream.token_usage)
        if token_error:
            return await self._reject(request, actor, started_at, token_error)
        response = ScientificInterpretationResponse(
            status="completed",
            conclusion=upstream.conclusion,
            recommendations=upstream.recommendations,
            evidence_refs=upstream.evidence_refs,
            risks=upstream.risks,
            agent_id=request.agent_id,
            duration_ms=self._duration_ms(started_at),
            token_usage=upstream.token_usage,
        )
        await self._audit_response(request, actor, response)
        return response

    def _policy_error(self, request: ConsultationRequest) -> ConsultationError | None:
        policy = self._settings.agent_policy_map().get(request.agent_id)
        if policy is None:
            return ConsultationError(
                code="AGENT_NOT_ALLOWED", message="Target agent is not allowlisted."
            )
        capabilities, tools = policy
        if request.capability not in capabilities:
            return ConsultationError(
                code="CAPABILITY_NOT_ALLOWED",
                message="Requested capability is not allowed for this agent.",
            )
        forbidden_tools = sorted(set(request.requested_tools) - tools)
        if forbidden_tools:
            return ConsultationError(
                code="TOOL_NOT_ALLOWED", message="Requested tool is not in the read-only allowlist."
            )
        return None

    async def _reserve_call(self, case_id: str) -> ConsultationError | None:
        async with self._lock:
            if self._case_calls[case_id] >= self._settings.max_calls_per_case:
                return ConsultationError(
                    code="CASE_CALL_LIMIT_EXCEEDED",
                    message="Per-case consultation limit exceeded.",
                )
            self._case_calls[case_id] += 1
        return None

    async def _consume_tokens(self, case_id: str, token_usage: int) -> ConsultationError | None:
        async with self._lock:
            if self._case_tokens[case_id] + token_usage > self._settings.max_tokens_per_case:
                return ConsultationError(
                    code="CASE_TOKEN_LIMIT_EXCEEDED",
                    message="Per-case token limit exceeded.",
                )
            self._case_tokens[case_id] += token_usage
        return None

    async def _reject(
        self,
        request: ConsultationRequest,
        actor: str,
        started_at: float,
        error: ConsultationError,
    ) -> ScientificInterpretationResponse:
        response = ScientificInterpretationResponse(
            status="rejected",
            conclusion="Consultation was not executed.",
            risks=["No automated action is permitted; route this request for manual review."],
            agent_id=request.agent_id,
            duration_ms=self._duration_ms(started_at),
            token_usage=0,
            error=error,
        )
        await self._audit_response(request, actor, response)
        return response

    async def _manual_review(
        self,
        request: ConsultationRequest,
        actor: str,
        started_at: float,
        code: str,
        message: str,
    ) -> ScientificInterpretationResponse:
        response = ScientificInterpretationResponse(
            status="manual_review",
            conclusion="No automated scientific conclusion is available.",
            risks=["Manual review is required before any workflow action."],
            agent_id=request.agent_id,
            duration_ms=self._duration_ms(started_at),
            token_usage=0,
            error=ConsultationError(code=code, message=message),
        )
        await self._audit_response(request, actor, response)
        return response

    async def _audit_response(
        self,
        request: ConsultationRequest,
        actor: str,
        response: ScientificInterpretationResponse,
    ) -> None:
        await self._audit.record(
            case_id=request.case_id,
            actor=actor,
            event_type="agent.consultation",
            payload={
                "target_role": request.agent_id,
                "question_summary": self._question_summary(request.question),
                "schema_version": response.schema_version,
                "status": response.status,
                "duration_ms": response.duration_ms,
                "token_usage": response.token_usage,
                "evidence_refs": response.evidence_refs,
                "error_code": response.error.code if response.error else None,
            },
        )

    @staticmethod
    def _duration_ms(started_at: float) -> int:
        return int((time.perf_counter() - started_at) * 1_000)

    @staticmethod
    def _question_summary(question: str) -> str:
        return " ".join(question.split())[:500]
