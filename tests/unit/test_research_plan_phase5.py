"""Phase5 deterministic contracts; no real runtime or scientific-task claims."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from cygnusx.application.schemas.research_plan import (
    PlanStatus,
    ResearchPlanDraft,
    StepStatus,
)
from cygnusx.domain.research.plan_state import (
    InvalidTransitionError,
    plan_digest,
    ready_steps,
    transition,
)

pytestmark = pytest.mark.unit


def discovery():
    return {
        "research_question": "synthetic discovery",
        "steps": [
            {
                "step_id": "discover",
                "kind": "DISCOVERY",
                "goal": "inspect source",
                "arguments": {"accession": "GSE1234"},
            }
        ],
    }


def chain():
    value = discovery()
    value["steps"] = [
        {
            "step_id": "prepare",
            "kind": "ANALYSIS_PREPARE",
            "goal": "prepare",
            "arguments": {
                "dataset_id": "00000000-0000-0000-0000-000000000001",
                "version_id": "00000000-0000-0000-0000-000000000002",
                "request": {"flow_id": "counts_deg"},
            },
        },
        {
            "step_id": "execute",
            "kind": "ANALYSIS_EXECUTE",
            "goal": "execute",
            "depends_on": ["prepare"],
            "bindings": [
                {"argument": "proposal_id", "from_step": "prepare", "output": "analysis_proposal"}
            ],
        },
        {
            "step_id": "deliver",
            "kind": "DELIVERY_PREPARE",
            "goal": "deliver",
            "depends_on": ["execute"],
            "bindings": [{"argument": "task_id", "from_step": "execute", "output": "task_id"}],
        },
    ]
    return value


def test_schema_roundtrip_and_digest():
    plan = ResearchPlanDraft.model_validate(chain())
    assert ResearchPlanDraft.model_validate_json(plan.model_dump_json()) == plan
    assert len(plan_digest(plan)) == 64
    changed = chain()
    changed["steps"][0]["arguments"]["request"]["flow_id"] = "rna_seq"
    assert plan_digest(ResearchPlanDraft.model_validate(changed)) != plan_digest(plan)


@pytest.mark.parametrize(
    "field", ["owner_id", "project_id", "plan_id", "status", "approved", "task_id"]
)
def test_model_cannot_inject_trusted_fields(field):
    value = discovery()
    value[field] = "trusted"
    with pytest.raises(ValidationError):
        ResearchPlanDraft.model_validate(value)


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "cycle",
        "dangling",
        "port",
        "tool",
        "step_kind",
        "self_confirm",
        "unbounded",
        "shadow",
        "direct_write",
    ],
)
def test_hostile_or_invalid_dag_rejected(mutation):
    value = chain()
    if mutation == "duplicate":
        value["steps"].append(deepcopy(value["steps"][0]))
    elif mutation == "cycle":
        value["steps"][0]["depends_on"] = ["deliver"]
    elif mutation == "dangling":
        value["steps"][0]["depends_on"] = ["missing"]
    elif mutation == "port":
        value["steps"][1]["bindings"][0]["output"] = "import_proposal"
    elif mutation == "tool":
        value["steps"][0]["capability_id"] = "shell.execute"
    elif mutation == "step_kind":
        value["steps"][0]["kind"] = "SHELL"
    elif mutation == "self_confirm":
        value["steps"][1]["arguments"] = {"confirmed": True}
    elif mutation == "unbounded":
        value["budget"] = {"max_retries": 100}
    elif mutation == "shadow":
        value["steps"][1]["arguments"] = {"proposal_id": "00000000-0000-0000-0000-000000000001"}
    elif mutation == "direct_write":
        value["steps"][1]["bindings"] = []
        value["steps"][1]["arguments"] = {"proposal_id": "00000000-0000-0000-0000-000000000001"}
    with pytest.raises(ValidationError):
        ResearchPlanDraft.model_validate(value)


def test_dependencies_and_ambiguous_submitting_never_replayed():
    plan = ResearchPlanDraft.model_validate(chain())
    assert ready_steps(plan, {}) == ["prepare"]
    assert ready_steps(plan, {"prepare": StepStatus.COMPLETE}) == ["execute"]
    assert (
        ready_steps(plan, {"prepare": StepStatus.COMPLETE, "execute": StepStatus.SUBMITTING}) == []
    )
    assert ready_steps(plan, {"prepare": StepStatus.COMPLETE, "execute": StepStatus.PARTIAL}) == []


def test_state_machine_does_not_accept_model_completion_or_replay():
    with pytest.raises(InvalidTransitionError):
        transition(PlanStatus.DRAFT, PlanStatus.COMPLETED)
    with pytest.raises(InvalidTransitionError):
        transition(PlanStatus.RECONCILIATION_REQUIRED, PlanStatus.RUNNING)
    assert transition(PlanStatus.RUNNING, PlanStatus.PAUSED) == PlanStatus.PAUSED
    assert transition(PlanStatus.RUNNING, PlanStatus.RUNNING) == PlanStatus.RUNNING


def test_counts_design_allowed_but_nested_secret_and_path_overrides_rejected():
    value = chain()
    value["steps"][0]["arguments"]["request"]["options"] = {"parameters": {"design": "~ group"}}
    ResearchPlanDraft.model_validate(value)
    for forbidden in [
        {"token": "secret"},
        {"raw_data_path": "/home/owner"},
        {"parameters": {"reference": "/etc/passwd"}},
        {"parameters": {"reference": "https://untrusted.invalid"}},
    ]:
        hostile = deepcopy(value)
        hostile["steps"][0]["arguments"]["request"]["options"] = forbidden
        with pytest.raises(ValidationError):
            ResearchPlanDraft.model_validate(hostile)


def test_dataset_output_bindings_match_typed_input_ports():
    value = {
        "research_question": "Inspect a previously resolved version",
        "steps": [
            {
                "step_id": "inspect",
                "kind": "DATASET_INSPECT",
                "goal": "inspect",
                "arguments": {
                    "dataset_id": "00000000-0000-0000-0000-000000000001",
                    "version_id": "00000000-0000-0000-0000-000000000002",
                },
            },
            {
                "step_id": "match",
                "kind": "WORKFLOW_MATCH",
                "goal": "match",
                "depends_on": ["inspect"],
                "bindings": [
                    {"argument": "dataset_id", "from_step": "inspect", "output": "dataset_version"},
                    {"argument": "version_id", "from_step": "inspect", "output": "dataset_version"},
                ],
            },
        ],
    }
    ResearchPlanDraft.model_validate(value)
    value["steps"][1]["bindings"][0]["output"] = "task_id"
    with pytest.raises(ValidationError):
        ResearchPlanDraft.model_validate(value)


def test_real_task_state_projection_requires_manifest_and_independent_reports():
    from uuid import uuid4

    from cygnusx.application.schemas.research_delivery import ResearchProvenance
    from cygnusx.application.schemas.research_plan import Effect, StepKind, StepView
    from cygnusx.application.services.research_plan_service import ResearchPlanService

    step = StepView(
        step_id="deliver",
        kind=StepKind.DELIVERY_PREPARE,
        capability_id="research.task_provenance",
        effect=Effect.READ_ONLY,
        approval_required=False,
        expected_output="delivery_proposal",
        status=StepStatus.WAITING_INPUT,
    )
    graph = ResearchProvenance(owner_id=uuid4(), task_id=uuid4(), compute_state="queued")
    ResearchPlanService.observe_delivery(step, graph)
    assert step.status == StepStatus.QUEUED and step.task_id == graph.task_id
    graph.compute_state = "success"
    graph.result_integrity = "MISSING"
    ResearchPlanService.observe_delivery(step, graph)
    assert step.status == StepStatus.PARTIAL
    assert step.error_code == "RESULT_MANIFEST_OR_ARTIFACT_NOT_VERIFIED"
    graph.result_integrity = "VERIFIED"
    graph.delivery_state = "PARTIAL"
    ResearchPlanService.observe_delivery(step, graph)
    assert step.status == StepStatus.PARTIAL and step.error_code == "REPORT_DELIVERY_INCOMPLETE"
    graph.delivery_state = "READY"
    ResearchPlanService.observe_delivery(step, graph)
    assert step.status == StepStatus.COMPLETE and step.error_code is None


@pytest.mark.parametrize(
    "filename,model_name",
    [
        ("cygnusx-research-plan-v1.schema.json", "ResearchPlanView"),
        ("cygnusx-research-plan-input-v1.schema.json", "ResearchPlanDraft"),
        ("cygnusx-research-claim-input-v1.schema.json", "ClaimDraft"),
        ("cygnusx-research-claim-v1.schema.json", "ClaimAssessment"),
        ("cygnusx-research-artifact-cell-v1.schema.json", "ArtifactCellRequest"),
    ],
)
def test_published_schema_matches_runtime_contract(filename, model_name):
    import json
    from pathlib import Path

    from cygnusx.application.schemas import research_claims, research_plan

    model = getattr(research_plan, model_name, None) or getattr(research_claims, model_name)
    root = Path(__file__).resolve().parents[2]
    published = json.loads((root / "docs/contracts" / filename).read_text())
    assert published == model.model_json_schema()


@pytest.mark.parametrize("compute_state", ["unknown", "retry", "SUCCESS", ""])
def test_unknown_compute_state_never_projects_complete(compute_state):
    from uuid import uuid4

    from cygnusx.application.schemas.research_delivery import ResearchProvenance
    from cygnusx.application.schemas.research_plan import Effect, StepKind, StepView
    from cygnusx.application.services.research_plan_service import ResearchPlanService

    step = StepView(
        step_id="deliver",
        kind=StepKind.DELIVERY_PREPARE,
        capability_id="research.task_provenance",
        effect=Effect.READ_ONLY,
        approval_required=False,
        expected_output="delivery_proposal",
        status=StepStatus.WAITING_INPUT,
    )
    graph = ResearchProvenance(
        owner_id=uuid4(), task_id=uuid4(), compute_state=compute_state,
        result_integrity="VERIFIED", delivery_state="READY",
    )
    ResearchPlanService.observe_delivery(step, graph)
    assert step.status == StepStatus.RECONCILIATION_REQUIRED
    assert step.error_code == "COMPUTE_STATE_UNKNOWN"
