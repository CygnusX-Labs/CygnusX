import pytest

from omichub.application.services.mas_plan_validator import MASPlanValidator
from omichub.core.exceptions import ValidationError
from omichub.domain.mas.models import ExecutionPlan, MASNode


def test_plan_validator_requires_registered_agent_capabilities() -> None:
    plan = ExecutionPlan(
        title="RNA workflow",
        nodes=(
            MASNode(
                key="analyse",
                agent_id="agent-rnaseq",
                intent="run",
                resources={"required_capabilities": ["rnaflow"]},
            ),
        ),
    )
    validator = MASPlanValidator({"agent-rnaseq": {"rnaflow", "quality-gate"}})

    assert validator.validate(plan) == plan
    with pytest.raises(ValidationError, match="未注册"):
        MASPlanValidator({}).validate(plan)
    with pytest.raises(ValidationError, match="不具备"):
        MASPlanValidator({"agent-rnaseq": set()}).validate(plan)


def test_plan_validator_requires_quality_gate_before_volcano() -> None:
    plan = ExecutionPlan(
        title="RNA workflow",
        nodes=(
            MASNode(key="rnaseq", agent_id="agent-rnaseq", intent="run"),
            MASNode(
                key="volcano",
                agent_id="agent-viz",
                intent="plot",
                depends_on=("rnaseq",),
                resources={"executor": "deg-volcano"},
            ),
        ),
    )
    validator = MASPlanValidator({"agent-rnaseq": set(), "agent-viz": set()})

    with pytest.raises(ValidationError, match="quality-gate"):
        validator.validate(plan)

    guarded_plan = plan.model_copy(
        update={
            "nodes": (
                plan.nodes[0],
                MASNode(
                    key="qc",
                    agent_id="agent-rnaseq",
                    intent="quality",
                    depends_on=("rnaseq",),
                    resources={"executor": "quality-gate"},
                ),
                plan.nodes[1].model_copy(update={"depends_on": ("qc",)}),
            )
        }
    )
    assert validator.validate(guarded_plan) == guarded_plan
