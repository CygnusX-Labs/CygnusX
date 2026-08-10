from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from omichub_agentteams_bridge.audit import AuditStore
from omichub_agentteams_bridge.case_store import CaseStore
from omichub_agentteams_bridge.config import BridgeSettings
from omichub_agentteams_bridge.models import (
    CaseCreateRequest,
    ContextRef,
    ReadOnlyExecutionRequest,
    WorkItemCreateRequest,
)
from omichub_agentteams_bridge.service import BridgeService


class FakeOmicHubClient:
    async def aclose(self) -> None:
        return None


class ConcurrentGateway:
    configured = True

    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.payloads: list[dict[str, object]] = []

    async def consult(self, payload: dict[str, object]) -> dict[str, object]:
        self.payloads.append(payload)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.03)
            return {
                "schema_version": "1.0",
                "status": "completed",
                "conclusion": f"Completed {payload['agent_id']}",
                "recommendations": ["Keep the result reproducible."],
                "evidence_refs": ["omic://project/project-1"],
                "risks": [],
                "agent_id": payload["agent_id"],
                "schema_ver": "1.0",
                "duration_ms": 30,
                "token_usage": 42,
            }
        finally:
            self.active -= 1


class PlanningGateway:
    configured = True

    async def consult(self, payload: dict[str, object]) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "status": "completed",
            "conclusion": "冻结 RNA-seq 执行计划。",
            "recommendations": ["Proceed with project preflight."],
            "evidence_refs": ["omic://project/project-1"],
            "risks": [],
            "agent_id": payload["agent_id"],
            "schema_ver": "1.0",
            "duration_ms": 1,
            "token_usage": 10,
            "proposed_submission": {
                "flow_id": "rna_seq",
                "name": "rna-seq-analysis",
                "sample_sheet": [{"sample": "sample-a", "group": "control"}],
                "comparisons": [{"control": "control", "treatment": "treated"}],
            },
        }


def make_service(tmp_path, gateway: ConcurrentGateway) -> BridgeService:
    settings = BridgeSettings(
        omichub_service_token="service-token",
        approval_signing_secret="test-signing-secret",
        identities=(
            "approval-authority:approval,bioops-manager:manager,data-steward:steward,"
            "workflow-operator:operator,quality-auditor:auditor,delivery-reporter:reporter,"
            "agent-code:code,agent-viz:viz,agent-scrna:scrna,agent-rnaseq:rnaseq"
        ),
        audit_log_path=str(tmp_path / "audit.jsonl"),
        case_store_path=str(tmp_path / "cases.json"),
        manifest_dir=str(tmp_path / "manifests"),
    )
    return BridgeService(
        settings,
        FakeOmicHubClient(),
        AuditStore(settings.audit_log_path),
        CaseStore(settings.case_store_path),
        gateway,
    )


async def create_case(service: BridgeService, case_id: str = "cluster-case") -> None:
    await service.create_case(
        CaseCreateRequest(
            case_id=case_id,
            project_ref=ContextRef(kind="project", id="project-1"),
            intent="read_only_cluster_consultation",
            requester_ref="user-1",
        ),
        "bioops-manager",
    )


@pytest.mark.asyncio
async def test_planning_consultation_freezes_plan_before_preflight(tmp_path) -> None:
    service = make_service(tmp_path, PlanningGateway())
    case = await service.create_case(
        CaseCreateRequest(
            case_id="planned-case",
            project_ref=ContextRef(kind="project", id="project-1"),
            intent="bulk_rnaseq_delivery",
            requester_ref="user-1",
            flow_id="rna_seq",
        ),
        "bioops-manager",
    )

    assert case.status == "planning_running"
    assert case.work_items[0].work_item_id == "plan-01"
    assert case.work_items[0].target == "agent-rnaseq"
    await service.claim_work_item("planned-case", "plan-01", "agent-rnaseq")
    result = await service.execute_readonly_work_item(
        "planned-case",
        "plan-01",
        ReadOnlyExecutionRequest(
            agent_id="agent-rnaseq",
            capability="planning_advice",
            question="Draft a frozen RNA-seq plan.",
            trace_id="trace-plan-01",
        ),
        "agent-rnaseq",
    )
    frozen_case = await service._cases.get("planned-case")

    assert result.status == "completed"
    assert frozen_case.status == "preflight_running"
    assert frozen_case.plan_hash
    assert frozen_case.proposed_submission and frozen_case.proposed_submission["flow_id"] == "rna_seq"
    preflight = next(item for item in frozen_case.work_items if item.work_item_id == "preflight-01")
    assert preflight.depends_on == ["plan-01"]


@pytest.mark.asyncio
async def test_workspace_execution_is_rejected_without_frozen_approved_plan(tmp_path) -> None:
    service = make_service(tmp_path, ConcurrentGateway())
    await create_case(service, "workspace-case")

    with pytest.raises(Exception, match="frozen approved plan"):
        await service.assign_work_item(
            "workspace-case",
            WorkItemCreateRequest(
                work_item_id="code-write-01",
                target="agent-code",
                objective="Generate a scoped report artifact.",
                skill_name="code-review",
                execution_mode="workspace_execution",
            ),
            "bioops-manager",
        )


@pytest.mark.asyncio
async def test_all_readonly_worker_roles_execute_in_parallel(tmp_path) -> None:
    gateway = ConcurrentGateway()
    service = make_service(tmp_path, gateway)
    await create_case(service)
    assignments = [
        ("agent-code", "code-01", "code-review", "agent-code", "planning_advice"),
        ("agent-viz", "viz-01", "visualization-review", "agent-viz", "result_interpretation"),
        ("agent-scrna", "scrna-01", "scrna-interpretation", "agent-scrna", "interpretation"),
        (
            "data-steward",
            "data-01",
            "project-preflight",
            "agent-data",
            "project-preflight",
        ),
        ("quality-auditor", "quality-01", "quality-gate", "agent-qc", "quality-gate"),
        (
            "delivery-reporter",
            "delivery-01",
            "delivery-report",
            "agent-delivery",
            "delivery-pack",
        ),
    ]
    for identity, work_item_id, skill_name, *_ in assignments:
        await service.assign_work_item(
            "cluster-case",
            WorkItemCreateRequest(
                work_item_id=work_item_id,
                target=identity,
                objective=f"Review {identity} output.",
                skill_name=skill_name,
                context_refs=[ContextRef(kind="project", id="project-1")],
            ),
            "bioops-manager",
        )
        await service.claim_work_item("cluster-case", work_item_id, identity)

    results = await asyncio.gather(
        *(
            service.execute_readonly_work_item(
                "cluster-case",
                work_item_id,
                ReadOnlyExecutionRequest(
                    agent_id=agent_id,
                    capability=capability,
                    question=f"Review {identity} output.",
                    trace_id=f"trace-{work_item_id}",
                ),
                identity,
            )
            for identity, work_item_id, _, agent_id, capability in assignments
        )
    )

    assert gateway.max_active == len(assignments)
    assert {payload["requester_ref"] for payload in gateway.payloads} == {"user-1"}
    assert [result.status for result in results] == ["completed"] * len(assignments)
    events = await service.get_case_events("cluster-case", "bioops-manager")
    assert {event["event_type"] for event in events.events} >= {
        "work_item.claimed",
        "work_item.running",
        "worker.heartbeat",
        "skill.finished",
    }


@pytest.mark.asyncio
async def test_expired_lease_is_requeued_and_can_be_claimed_again(tmp_path) -> None:
    service = make_service(tmp_path, ConcurrentGateway())
    await create_case(service)
    await service.assign_work_item(
        "cluster-case",
        WorkItemCreateRequest(
            work_item_id="code-01",
            target="agent-code",
            objective="Review code.",
            skill_name="code-review",
            deadline_seconds=30,
        ),
        "bioops-manager",
    )
    claimed = await service.claim_work_item("cluster-case", "code-01", "agent-code")
    expired = claimed.model_copy(update={"lease_expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    await service._cases.update_work_item("cluster-case", "code-01", expired)

    inbox = await service.list_worker_inbox("agent-code")

    assert inbox.items[0].work_item.status == "pending"
    reclaimed = await service.claim_work_item("cluster-case", "code-01", "agent-code")
    assert reclaimed.status == "claimed"
    assert reclaimed.attempt == 2
