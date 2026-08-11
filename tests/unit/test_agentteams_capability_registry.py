from __future__ import annotations

from omichub.application.services.agentteams_capability_registry import (
    AgentTeamsCapabilityRegistry,
)
from omichub.application.services.flow_registry import FlowRegistry


class _Abilities:
    def all(self):
        return {"agent-code": {}, "agent-qc": {}}


def test_registry_discovers_flow_roles_and_worker_profiles(tmp_path) -> None:
    flows_dir = tmp_path / "flows"
    shared_dir = flows_dir / "_shared"
    shared_dir.mkdir(parents=True)
    (shared_dir / "policies.yaml").write_text(
        "retry_policies:\n  bounded: {max_attempts: 1}\napproval_templates: {}\n",
        encoding="utf-8",
    )
    (shared_dir / "resources.yaml").write_text(
        "standard: {cpu: 1, memory_gb: 1, temp_disk_gb: 1, queue: general, max_project_concurrency: 1}\n",
        encoding="utf-8",
    )
    (shared_dir / "artifact_types.yaml").write_text(
        "table: {format: tsv, media_types: [text/tab-separated-values], max_size_gb: 1, retention_days: 1}\n",
        encoding="utf-8",
    )
    (flows_dir / "test_general.yaml").write_text(
        """flow:
  id: test_general
  version: 1.0.0
  display_name: Test General
  domain: general
  actor: agent-code
  runtime_image: analysis-core
  bridge_workflow: test_general
artifacts:
  - {key: result, type: table}
stages:
  - key: transform
    title: Transform
    executors:
      - {key: transform, queue: general, resource_profile: standard, outputs: [result], retry_policy: bounded}
delivery: {quality_gate: true, outputs: [result]}
""",
        encoding="utf-8",
    )
    registry = AgentTeamsCapabilityRegistry(
        FlowRegistry.from_directory(flows_dir),
        _Abilities(),
        [
            {
                "agent_id": "agent-code",
                "name": "Code",
                "features": {"internal_case_role": "agent-code"},
            },
            {
                "agent_id": "agent-qc",
                "name": "QC",
                "features": {"internal_case_role": "quality-auditor"},
            },
            {
                "agent_id": "agent-disabled",
                "is_active": False,
                "features": {"internal_case_role": "disabled"},
            },
        ],
    )

    assert registry.allowed_flow_ids() == {"test_general"}
    assert registry.role_agent_map() == {"agent-code": "agent-code", "quality-auditor": "agent-qc"}
    assert registry.consultation_agents() == {"agent-code", "agent-qc"}
    assert registry.flow_agent_map() == {"test_general": "agent-code"}
    assert registry.agent_for_flow("test_general") == "agent-code"
    assert registry.worker_profile("agent-code").capability == "planning_advice"


def test_registry_rejects_flow_without_active_actor(tmp_path) -> None:
    registry = AgentTeamsCapabilityRegistry(FlowRegistry.from_directory(tmp_path), _Abilities(), [])
    assert registry.agent_for_flow("missing") is None


def test_registry_falls_back_to_general_agent_when_flow_actor_is_missing(tmp_path) -> None:
    flows_dir = tmp_path / "flows"
    shared_dir = flows_dir / "_shared"
    shared_dir.mkdir(parents=True)
    (shared_dir / "policies.yaml").write_text(
        "retry_policies:\n  bounded: {max_attempts: 1}\napproval_templates: {}\n",
        encoding="utf-8",
    )
    (shared_dir / "resources.yaml").write_text(
        "standard: {cpu: 1, memory_gb: 1, temp_disk_gb: 1, queue: general, max_project_concurrency: 1}\n",
        encoding="utf-8",
    )
    (shared_dir / "artifact_types.yaml").write_text(
        "table: {format: tsv, media_types: [text/tab-separated-values], max_size_gb: 1, retention_days: 1}\n",
        encoding="utf-8",
    )
    (flows_dir / "fallback.yaml").write_text(
        """flow:
  id: fallback
  version: 1.0.0
  display_name: Fallback
  domain: general
  actor: agent-missing
  runtime_image: analysis-core
  bridge_workflow: fallback
artifacts: [{key: result, type: table}]
stages:
  - key: run
    title: Run
    executors: [{key: run, queue: general, resource_profile: standard, outputs: [result], retry_policy: bounded}]
delivery: {quality_gate: true, outputs: [result]}
""",
        encoding="utf-8",
    )
    registry = AgentTeamsCapabilityRegistry(
        FlowRegistry.from_directory(flows_dir),
        _Abilities(),
        [{"agent_id": "agent-general", "features": {"internal_case_role": "bioops-manager"}}],
    )

    assert registry.agent_for_flow("fallback") == "agent-general"
