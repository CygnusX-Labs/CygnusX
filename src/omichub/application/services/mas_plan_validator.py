"""Server-side validation for LLM-produced MAS execution plans."""

from __future__ import annotations

from collections.abc import Mapping

from omichub.core.exceptions import ValidationError
from omichub.domain.mas.models import ExecutionPlan


class MASPlanValidator:
    """Ensures every planned node targets a registered agent with matching capabilities."""

    def __init__(self, agent_capabilities: Mapping[str, set[str]]) -> None:
        self._agent_capabilities = agent_capabilities

    def validate(self, plan: ExecutionPlan) -> ExecutionPlan:
        for node in plan.nodes:
            capabilities = self._agent_capabilities.get(node.agent_id)
            if capabilities is None:
                raise ValidationError(f"计划引用了未注册的 MAS Agent: {node.agent_id}")
            required = {str(item) for item in node.resources.get("required_capabilities", [])}
            missing = required - capabilities
            if missing:
                raise ValidationError(
                    f"Agent {node.agent_id} 不具备节点 {node.key} 所需能力: {sorted(missing)}"
                )
        self._validate_quality_gate_dependencies(plan)
        return plan

    @staticmethod
    def _validate_quality_gate_dependencies(plan: ExecutionPlan) -> None:
        nodes = {node.key: node for node in plan.nodes}
        quality_gate_keys = {
            node.key for node in plan.nodes if node.resources.get("executor") == "quality-gate"
        }
        for node in plan.nodes:
            if node.resources.get("executor") != "deg-volcano":
                continue
            pending = list(node.depends_on)
            seen: set[str] = set()
            while pending:
                dependency = pending.pop()
                if dependency in seen:
                    continue
                if dependency in quality_gate_keys:
                    break
                seen.add(dependency)
                pending.extend(nodes[dependency].depends_on)
            else:
                raise ValidationError(
                    f"火山图节点 {node.key} 必须依赖一个 quality-gate 节点，不能绕过 QC 阻断"
                )
