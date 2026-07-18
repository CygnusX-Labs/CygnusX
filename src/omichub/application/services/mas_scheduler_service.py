"""Dependency-aware MAS scheduler with optimistic node state transitions."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.services.a2a_event_service import A2AEventService
from omichub.domain.mas.models import (
    A2AEvent,
    A2AEventType,
    AgentRecipient,
    AgentSender,
    NodeState,
)
from omichub.domain.mas.errors import classify_error
from omichub.infrastructure.database.models.mas import MASNodeModel
from omichub.infrastructure.database.repositories.mas_repository import MASRepository


class MASSchedulerService:
    def __init__(self, session: AsyncSession) -> None:
        self._repository = MASRepository(session)
        self._events = A2AEventService(session)

    @staticmethod
    def eligible_nodes(nodes: list[MASNodeModel]) -> list[MASNodeModel]:
        """Return pending nodes whose declared upstream dependencies all succeeded."""
        statuses = {node.node_key: node.status for node in nodes}
        return [
            node
            for node in nodes
            if node.status == NodeState.PENDING.value
            and all(
                statuses.get(dependency) == NodeState.SUCCEEDED.value
                for dependency in node.depends_on
            )
        ]

    async def unlock_ready_nodes(self, run_id: UUID, trace_id: str) -> list[str]:
        """Move currently eligible nodes to READY; stale concurrent updates become no-ops."""
        run = await self._repository.get_run(run_id)
        if run is None or run.status not in {"queued", "running"}:
            return []

        ready_keys: list[str] = []
        for node in self.eligible_nodes(await self._repository.list_nodes(run_id)):
            if not await self._repository.transition_node(
                node_id=node.id,
                expected_version=node.version,
                current_status=NodeState.PENDING.value,
                target_status=NodeState.READY.value,
            ):
                continue
            next_version = node.version + 1
            await self._events.record(
                A2AEvent(
                    event_type=A2AEventType.NODE_READY,
                    trace_id=trace_id,
                    run_id=run_id,
                    node_key=node.node_key,
                    sender=AgentSender(kind="system", id="mas-scheduler"),
                    recipient=AgentRecipient(kind="worker", id=node.agent_id),
                    status="ready",
                    intent=node.intent,
                    dedupe_key=(
                        f"{run_id}:{node.node_key}:attempt_{node.attempt_count}:"
                        f"node.ready:state_version_{next_version}"
                    ),
                    state_version=next_version,
                )
            )
            ready_keys.append(node.node_key)
        return ready_keys

    async def dispatch_ready_node(self, run_id: UUID, node_key: str, trace_id: str) -> bool:
        """Claim a READY node exactly once and optionally dispatch the test-only fake executor."""
        node = await self._repository.get_node(run_id, node_key)
        if node is None or node.status != NodeState.READY.value:
            return False
        if not await self._repository.transition_node(
            node_id=node.id,
            expected_version=node.version,
            current_status=NodeState.READY.value,
            target_status=NodeState.DISPATCHED.value,
        ):
            return False

        next_version = node.version + 1
        await self._events.record(
            A2AEvent(
                event_type=A2AEventType.NODE_DISPATCHED,
                trace_id=trace_id,
                run_id=run_id,
                node_key=node.node_key,
                sender=AgentSender(kind="system", id="mas-scheduler"),
                recipient=AgentRecipient(kind="worker", id=node.agent_id),
                status="dispatched",
                intent=node.intent,
                dedupe_key=(
                    f"{run_id}:{node.node_key}:attempt_{node.attempt_count}:"
                    f"node.dispatched:state_version_{next_version}"
                ),
                state_version=next_version,
            )
        )
        if node.resources.get("executor") == "fake":
            from omichub.infrastructure.celery_app.tasks.mas import run_fake_node

            run_fake_node.delay(str(run_id), node.node_key)
        elif node.resources.get("executor") == "apptainer-rnaflow":
            from omichub.infrastructure.celery_app.tasks.mas import run_rnaflow_node

            run_rnaflow_node.delay(str(run_id), node.node_key)
        elif node.resources.get("executor") == "deg-volcano":
            from omichub.infrastructure.celery_app.tasks.mas import run_volcano_node

            run_volcano_node.delay(str(run_id), node.node_key)
        elif node.resources.get("executor") == "quality-gate":
            from omichub.infrastructure.celery_app.tasks.mas import run_quality_gate_node

            run_quality_gate_node.delay(str(run_id), node.node_key)
        elif node.resources.get("executor") == "ebi-download":
            from omichub.infrastructure.celery_app.tasks.mas import run_ebi_download_node

            run_ebi_download_node.delay(str(run_id), node.node_key)
        return True

    async def mark_node_succeeded(self, event: A2AEvent) -> bool:
        """Accept only the current attempt's completion event, then unlock dependants."""
        if event.node_key is None:
            return False
        node = await self._repository.get_node(event.run_id, event.node_key)
        if node is None or node.status != NodeState.RUNNING.value or node.version != event.state_version:
            return False
        if not await self._repository.transition_node(
            node_id=node.id,
            expected_version=node.version,
            current_status=NodeState.RUNNING.value,
            target_status=NodeState.SUCCEEDED.value,
        ):
            return False
        await self.unlock_ready_nodes(event.run_id, event.trace_id)
        nodes = await self._repository.list_nodes(event.run_id)
        if all(node.status in {NodeState.SUCCEEDED.value, NodeState.SKIPPED.value} for node in nodes):
            run = await self._repository.get_run(event.run_id)
            if run is not None and run.status == "running":
                await self._repository.transition_run(
                    run_id=run.id,
                    expected_version=run.version,
                    current_status="running",
                    target_status="succeeded",
                )
        return True

    async def handle_node_failure(self, event: A2AEvent) -> bool:
        """Pause only the failed node when policy requires user intervention."""
        if event.node_key is None:
            return False
        node = await self._repository.get_node(event.run_id, event.node_key)
        if node is None or node.status != NodeState.RUNNING.value or node.version != event.state_version:
            return False
        error_code = str(event.summary.metrics.get("error_code", "UNKNOWN"))
        decision = classify_error(error_code)
        retry_budget = min(node.max_attempts, decision.max_attempts)
        if decision.retryable and node.attempt_count < retry_budget:
            if not await self._repository.transition_node(
                node_id=node.id,
                expected_version=node.version,
                current_status=NodeState.RUNNING.value,
                target_status=NodeState.RETRY_WAIT.value,
            ):
                return False
            retry_wait_version = event.state_version + 1
            next_attempt = node.attempt_count + 1
            if not await self._repository.transition_node(
                node_id=node.id,
                expected_version=retry_wait_version,
                current_status=NodeState.RETRY_WAIT.value,
                target_status=NodeState.READY.value,
                attempt_count=next_attempt,
            ):
                return False
            ready_version = retry_wait_version + 1
            await self._events.record(
                A2AEvent(
                    event_type=A2AEventType.NODE_RETRY_SCHEDULED,
                    trace_id=event.trace_id,
                    run_id=event.run_id,
                    node_key=node.node_key,
                    sender=AgentSender(kind="system", id="mas-scheduler", attempt_count=next_attempt),
                    recipient=AgentRecipient(kind="worker", id=node.agent_id),
                    status="retry_scheduled",
                    intent=node.intent,
                    dedupe_key=(
                        f"{event.run_id}:{node.node_key}:attempt_{next_attempt}:"
                        f"node.retry_scheduled:state_version_{ready_version}"
                    ),
                    state_version=ready_version,
                )
            )
            await self._events.record(
                A2AEvent(
                    event_type=A2AEventType.NODE_READY,
                    trace_id=event.trace_id,
                    run_id=event.run_id,
                    node_key=node.node_key,
                    sender=AgentSender(kind="system", id="mas-scheduler", attempt_count=next_attempt),
                    recipient=AgentRecipient(kind="worker", id=node.agent_id),
                    status="ready",
                    intent=node.intent,
                    dedupe_key=(
                        f"{event.run_id}:{node.node_key}:attempt_{next_attempt}:"
                        f"node.ready:state_version_{ready_version}"
                    ),
                    state_version=ready_version,
                )
            )
            return True
        target_state = NodeState.WAITING_APPROVAL if decision.requires_approval else NodeState.FAILED
        if not await self._repository.transition_node(
            node_id=node.id,
            expected_version=node.version,
            current_status=NodeState.RUNNING.value,
            target_status=target_state.value,
        ):
            return False
        run = await self._repository.get_run(event.run_id)
        if decision.requires_approval:
            await self._repository.create_approval(
                run_id=event.run_id,
                node_id=node.id,
                kind=error_code.lower(),
                prompt=event.summary.message or f"节点 {node.node_key} 需要人工处理：{error_code}",
                options=[{"value": "approve", "label": "确认继续"}, {"value": "reject", "label": "终止运行"}],
            )
            if run is not None and run.status == "running":
                await self._repository.transition_run(
                    run_id=run.id,
                    expected_version=run.version,
                    current_status="running",
                    target_status="paused_for_input",
                )
        elif run is not None and run.status == "running":
            await self._repository.transition_run(
                run_id=run.id,
                expected_version=run.version,
                current_status="running",
                target_status="failed",
            )
        return True
