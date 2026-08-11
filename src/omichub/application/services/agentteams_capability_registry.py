"""Runtime discovery for AgentTeams flows, roles, and worker profiles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

from omichub.application.services.flow_registry import FlowRegistry, get_flow_registry
from omichub.infrastructure.config.agent_ability_catalog import (
    AgentAbilityCatalog,
    agent_ability_catalog,
)
from omichub.infrastructure.config.agent_loader import load_agent_configs


@dataclass(frozen=True)
class WorkerProfile:
    identity: str
    agent_id: str
    capability: str

    def as_dict(self) -> dict[str, str]:
        return {
            "identity": self.identity,
            "agent_id": self.agent_id,
            "capability": self.capability,
        }


class AgentTeamsCapabilityRegistry:
    """Derive AgentTeams routing exclusively from platform-owned YAML registries."""

    def __init__(
        self,
        flow_registry: FlowRegistry | None = None,
        ability_catalog: AgentAbilityCatalog | None = None,
        agent_configs: list[dict[str, Any]] | None = None,
    ) -> None:
        self._flow_registry = flow_registry
        self._ability_catalog = ability_catalog or agent_ability_catalog
        self._agent_configs = agent_configs

    def allowed_flow_ids(self) -> set[str]:
        return self._flows().bridge_flow_ids()

    def role_agent_map(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for agent_id, config in self._active_agents().items():
            role = str((config.get("features") or {}).get("internal_case_role") or "").strip()
            if not role:
                logger.warning(
                    "Active Agent 缺少 internal_case_role，不参与 AgentTeams: {}", agent_id
                )
                continue
            mapping[role] = agent_id
        return mapping

    def consultation_agents(self) -> set[str]:
        abilities = self._ability_catalog.all()
        return {agent_id for agent_id in self.role_agent_map().values() if agent_id in abilities}

    def worker_profile(self, identity: str) -> WorkerProfile | None:
        agent_id = self.role_agent_map().get(identity)
        if not agent_id:
            return None
        return WorkerProfile(
            identity=identity,
            agent_id=agent_id,
            capability=self._capability_for(identity, agent_id),
        )

    def agent_for_flow(self, flow_id: str) -> str | None:
        return self.flow_agent_map().get(flow_id)

    def flow_agent_map(self) -> dict[str, str]:
        active_agents = self._active_agents()
        mapping: dict[str, str] = {}
        for registered in self._flows().flows.values():
            definition = registered.definition.flow
            actor = definition.actor
            if actor not in active_agents:
                fallback = next(
                    (candidate for candidate in ("agent-general", "agent-omics") if candidate in active_agents),
                    None,
                )
                if fallback is None:
                    continue
                logger.warning(
                    "actor_fallback: flow={} configured_actor={} fallback_actor={}",
                    registered.id,
                    actor,
                    fallback,
                )
                actor = fallback
            if actor not in active_agents:
                continue
            mapping[registered.id] = actor
            mapping[definition.bridge_workflow] = actor
        return mapping

    def role_labels(self) -> dict[str, dict[str, str]]:
        labels: dict[str, dict[str, str]] = {}
        for agent_id, config in self._active_agents().items():
            role = str((config.get("features") or {}).get("internal_case_role") or "").strip()
            if not role:
                continue
            labels[role] = {
                "agent_id": agent_id,
                "name": str(config.get("name") or role),
                "avatar": str(config.get("avatar") or "💬"),
                "color": str(config.get("color") or "#64748b"),
                "role": str(config.get("category") or "worker"),
            }
        return labels

    def snapshot(self) -> dict[str, Any]:
        role_map = self.role_agent_map()
        return {
            "allowed_flow_ids": sorted(self.allowed_flow_ids()),
            "flow_agent_map": self.flow_agent_map(),
            "role_agent_map": role_map,
            "consultation_agents": sorted(self.consultation_agents()),
            "worker_profiles": {
                identity: profile.as_dict()
                for identity in sorted(role_map)
                if (profile := self.worker_profile(identity)) is not None
            },
            "role_labels": self.role_labels(),
        }

    def _flows(self) -> FlowRegistry:
        registry = self._flow_registry or get_flow_registry()
        registry.reload()
        return registry

    def _active_agents(self) -> dict[str, dict[str, Any]]:
        configs = self._agent_configs if self._agent_configs is not None else load_agent_configs()
        return {
            str(config["agent_id"]): config
            for config in configs
            if config.get("agent_id") and config.get("is_active", True) is not False
        }

    @staticmethod
    def _capability_for(identity: str, agent_id: str) -> str:
        fixed = {
            "data-steward": "project-preflight",
            "quality-auditor": "quality-gate",
            "delivery-reporter": "delivery-pack",
            "agent-code": "planning_advice",
            "agent-viz": "result_interpretation",
        }
        return fixed.get(
            identity, "interpretation" if agent_id.startswith("agent-") else "planning_advice"
        )


def get_agentteams_capability_registry() -> AgentTeamsCapabilityRegistry:
    return AgentTeamsCapabilityRegistry()


__all__ = [
    "AgentTeamsCapabilityRegistry",
    "WorkerProfile",
    "get_agentteams_capability_registry",
]
