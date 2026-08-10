"""Runtime settings for the isolated Agent Gateway."""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    """Gateway-only configuration; no database, shell, or filesystem credentials are accepted."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="GATEWAY_", extra="ignore")

    environment: str = "development"
    omichub_base_url: str = "http://omichub-api:8000"
    omichub_consultation_path: str = "/api/v1/agent-teams/consultations/scientific-interpretation"
    omichub_service_token: str = ""
    omichub_api_key: str = ""
    omichub_integration_token: str = ""
    identities: str = "bioops-manager:manager-secret"
    matrix_homeserver_url: str = ""
    matrix_service_token: str = ""
    matrix_identities: str = "bioops-manager=@bioops-manager:localhost,omichub-user=@omichub-user:localhost"
    matrix_request_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    matrix_sync_timeout_ms: int = Field(default=25_000, ge=1_000, le=60_000)
    element_base_url: str = ""
    request_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    max_calls_per_case: int = Field(default=5, ge=1, le=100)
    max_tokens_per_case: int = Field(default=200_000, ge=1, le=2_000_000)
    state_store_url: str = ""
    state_store_key_prefix: str = "omichub:agentteams:gateway"
    audit_log_path: str = "/tmp/omichub-agent-gateway-audit.jsonl"
    agent_policies: str = (
        "agent-rnaseq|interpretation,planning_advice,result_interpretation,qc_advice|"
        "ensembl.lookup_gene,ensembl.search_genes;"
        "agent-scrna|interpretation,planning_advice,result_interpretation,qc_advice|"
        "ensembl.lookup_gene,ensembl.search_genes;"
        "agent-viz|interpretation,result_interpretation,qc_advice,workspace_execution|"
        "ensembl.lookup_gene,ensembl.search_genes;"
        "agent-code|interpretation,planning_advice,result_interpretation,qc_advice,workspace_execution|"
        "ensembl.lookup_gene,ensembl.search_genes;"
        "agent-data|project-preflight|;"
        "agent-qc|quality-gate|;"
        "agent-delivery|delivery-pack|"
    )

    @model_validator(mode="after")
    def validate_production_secrets(self) -> GatewaySettings:
        if self.environment != "production":
            return self
        if self._is_placeholder(self.omichub_integration_token):
            raise ValueError("生产环境必须配置 OmicHub 集成令牌")
        identities = self.identity_secrets()
        if not identities or any(self._is_placeholder(secret) for secret in identities.values()):
            raise ValueError("生产环境必须替换 Gateway 身份凭证")
        if not self.agent_policy_map():
            raise ValueError("生产环境必须配置专业 Agent 白名单")
        if not self.state_store_url:
            raise ValueError("生产环境必须配置 Redis 共享状态存储")
        if bool(self.matrix_homeserver_url) != bool(self.matrix_service_token):
            raise ValueError("Matrix homeserver URL 与服务账号令牌必须同时配置")
        if self.matrix_homeserver_url and self._is_placeholder(self.matrix_service_token):
            raise ValueError("生产环境必须替换 Matrix 服务账号令牌")
        return self

    @staticmethod
    def _is_placeholder(value: str) -> bool:
        normalized = value.strip().lower()
        return (
            not normalized
            or normalized.startswith("replace-")
            or normalized.startswith("change-me")
        )

    def identity_secrets(self) -> dict[str, str]:
        entries = (entry.strip() for entry in self.identities.split(","))
        return {
            identity.strip(): secret.strip()
            for entry in entries
            if ":" in entry
            for identity, secret in [entry.split(":", maxsplit=1)]
            if identity.strip() and secret.strip()
        }

    def agent_policy_map(self) -> dict[str, tuple[set[str], set[str]]]:
        policies: dict[str, tuple[set[str], set[str]]] = {}
        for entry in self.agent_policies.split(";"):
            agent_id, separator, rules = entry.strip().partition("|")
            capabilities, separator2, tools = rules.partition("|") if separator else ("", "", "")
            if not agent_id or not separator or not separator2:
                continue
            policies[agent_id] = (
                {value.strip() for value in capabilities.split(",") if value.strip()},
                {value.strip() for value in tools.split(",") if value.strip()},
            )
        return policies

    @property
    def matrix_enabled(self) -> bool:
        return bool(self.matrix_homeserver_url.strip() and self.matrix_service_token.strip())

    def matrix_identity_map(self) -> dict[str, str]:
        entries = (entry.strip() for entry in self.matrix_identities.split(","))
        return {
            identity.strip(): matrix_user.strip()
            for entry in entries
            if "=" in entry
            for identity, matrix_user in [entry.split("=", maxsplit=1)]
            if identity.strip() and matrix_user.strip()
        }

    def matrix_identity_by_user(self) -> dict[str, str]:
        return {matrix_user: identity for identity, matrix_user in self.matrix_identity_map().items()}
