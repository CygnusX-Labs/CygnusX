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
    identities: str = "bioops-manager:manager-secret"
    request_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    max_calls_per_case: int = Field(default=5, ge=1, le=100)
    max_tokens_per_case: int = Field(default=200_000, ge=1, le=2_000_000)
    audit_log_path: str = "/tmp/omichub-agent-gateway-audit.jsonl"
    agent_policies: str = (
        "agent-rnaseq|interpretation,planning_advice,result_interpretation,qc_advice|"
        "ensembl.lookup_gene,ensembl.search_genes;"
        "agent-scrna|interpretation,planning_advice,result_interpretation,qc_advice|"
        "ensembl.lookup_gene,ensembl.search_genes;"
        "agent-viz|interpretation,result_interpretation,qc_advice|"
        "ensembl.lookup_gene,ensembl.search_genes;"
        "agent-code|interpretation,planning_advice,result_interpretation,qc_advice|"
        "ensembl.lookup_gene,ensembl.search_genes"
    )

    @model_validator(mode="after")
    def validate_production_secrets(self) -> GatewaySettings:
        if self.environment != "production":
            return self
        credentials = [
            value
            for value in (self.omichub_service_token, self.omichub_api_key)
            if not self._is_placeholder(value)
        ]
        if len(credentials) != 1:
            raise ValueError("生产环境必须且只能配置一种 OmicHub 受限认证方式")
        identities = self.identity_secrets()
        if not identities or any(self._is_placeholder(secret) for secret in identities.values()):
            raise ValueError("生产环境必须替换 Gateway 身份凭证")
        if not self.agent_policy_map():
            raise ValueError("生产环境必须配置专业 Agent 白名单")
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
