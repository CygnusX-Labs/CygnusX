"""Runtime configuration for the isolated Bridge service."""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BridgeSettings(BaseSettings):
    """Only Bridge-owned configuration is accepted here; no database credentials."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="BRIDGE_", extra="ignore")

    environment: str = "development"
    omichub_base_url: str = "http://omichub-api:8000"
    omichub_service_token: str = ""
    omichub_api_key: str = ""
    gateway_url: str = ""
    gateway_manager_token: str = ""
    approval_signing_secret: str = "change-me-before-deployment"
    identities: str = (
        "approval-authority:approval-secret,bioops-manager:manager-secret,data-steward:steward-secret,"
        "workflow-operator:operator-secret,quality-auditor:auditor-secret,"
        "delivery-reporter:reporter-secret,agent-code:code-secret,agent-viz:viz-secret,"
        "agent-scrna:scrna-secret,agent-rnaseq:rnaseq-secret,analysis-worker:analysis-secret"
    )
    allowed_flow_ids: str = "rna_seq,scrna_seq"
    request_timeout_seconds: float = 20.0
    max_request_bytes: int = Field(default=1_048_576, ge=1_024, le=16_777_216)
    max_response_bytes: int = Field(default=1_048_576, ge=1_024, le=16_777_216)
    max_evidence_bytes: int = 16_384
    worker_heartbeat_ttl_seconds: int = Field(default=180, ge=30, le=3_600)
    state_store_url: str = ""
    state_store_key_prefix: str = "omichub:agentteams"
    audit_log_path: str = "/tmp/omichub-agentteams-bridge-audit.jsonl"
    case_store_path: str = "/tmp/omichub-agentteams-bridge-cases.json"
    manifest_dir: str = "/tmp/omichub-agentteams-bridge-manifests"

    @model_validator(mode="after")
    def validate_production_secrets(self) -> BridgeSettings:
        if self.environment != "production":
            return self
        default_values = {
            "approval_signing_secret": "change-me-before-deployment",
            "identities": (
                "approval-authority:approval-secret,bioops-manager:manager-secret,data-steward:steward-secret,"
                "workflow-operator:operator-secret,quality-auditor:auditor-secret,"
            "delivery-reporter:reporter-secret,agent-code:code-secret,agent-viz:viz-secret,"
            "agent-scrna:scrna-secret,agent-rnaseq:rnaseq-secret,analysis-worker:analysis-secret"
            ),
        }
        configured_upstream_credentials = [
            value
            for value in (self.omichub_service_token, self.omichub_api_key)
            if not self._is_placeholder(value)
        ]
        if not configured_upstream_credentials:
            raise ValueError("生产环境必须设置 OmicHub 受限服务令牌或 API Key")
        if len(configured_upstream_credentials) > 1:
            raise ValueError("生产环境只能配置一种 OmicHub 上游认证方式")
        if self._is_placeholder(self.approval_signing_secret):
            raise ValueError("生产环境必须替换审批签名密钥")
        identity_secrets = self.identity_secrets()
        if (
            self.identities == default_values["identities"]
            or not identity_secrets
            or any(self._is_placeholder(secret) for secret in identity_secrets.values())
        ):
            raise ValueError("生产环境必须替换 Bridge 身份凭证")
        if not self.allowed_flows():
            raise ValueError("生产环境必须配置允许的流程白名单")
        if bool(self.gateway_url) != bool(self.gateway_manager_token):
            raise ValueError("生产环境 Gateway URL 与 Manager token 必须同时配置")
        if self.gateway_url and self._is_placeholder(self.gateway_manager_token):
            raise ValueError("生产环境必须替换 Gateway Manager token")
        if not self.state_store_url:
            raise ValueError("生产环境必须配置 Redis 共享状态存储")
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

    def allowed_flows(self) -> set[str]:
        return {flow_id.strip() for flow_id in self.allowed_flow_ids.split(",") if flow_id.strip()}
