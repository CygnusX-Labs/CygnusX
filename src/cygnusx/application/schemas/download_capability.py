"""Server-owned declared capabilities. No binary or runtime attestation is inferred."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class DownloadMethodParameter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    minimum: int
    maximum: int


class DownloadSourceCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_type: str
    supported_methods: tuple[str, ...]
    method_parameters: tuple[DownloadMethodParameter, ...] = ()
    input_accession_types: tuple[str, ...] = ()
    protocols: tuple[str, ...] = ()
    binary_name: str | None = None
    binary_version: str | None = None
    verification_status: Literal["SUPPORTED_BY_CODE", "NOT_IMPLEMENTED"] = "SUPPORTED_BY_CODE"
    runtime_readiness: Literal["BLOCKED"] = "BLOCKED"
    enabled_by_configuration: bool = False
    limitations: tuple[str, ...]
    code_available: bool = True
    transport_required: bool = True
    runtime_verification: Literal["UNKNOWN"] = "UNKNOWN"
    execution_allowed: Literal[False] = False
    required_scope: str = "read:discovery"
    requires_project: bool = False
    query_tools: tuple[str, ...] = ()

    states: tuple[str, ...] = ()

    @model_validator(mode="after")
    def derive_states(self) -> DownloadSourceCapability:
        """Orthogonal evidence labels; configuration never implies certification.

        RUNTIME_VERIFIED is reserved for a future trusted attestation consumer,
        which does not exist in this release. UNKNOWN describes that missing fact.
        """
        result = ["CODE_AVAILABLE" if self.code_available else "NOT_IMPLEMENTED"]
        if self.enabled_by_configuration and self.code_available:
            result.append("CONFIGURED")
        result.append("UNKNOWN")
        if self.transport_required or not self.code_available:
            result.append("EXECUTION_BLOCKED")
        object.__setattr__(self, "states", tuple(result))
        return self


class DownloadCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["cygnusx.download_capabilities.v1"] = "cygnusx.download_capabilities.v1"
    sources: tuple[DownloadSourceCapability, ...]
    capabilities: tuple[DownloadSourceCapability, ...] = ()
    runtime_status: Literal["BLOCKED"] = "BLOCKED"
    write_enabled: Literal[False] = False
    candidate_accessions: tuple[str, ...] = ("SRR", "PRJNA")
    runtime_verified_accessions: tuple[str, ...] = ()
    limits: dict[str, int | bool | None]
    legacy_method_policy: str = (
        "aws/ftp retained; aspera/prefetch/auto refused; no silent remapping"
    )
