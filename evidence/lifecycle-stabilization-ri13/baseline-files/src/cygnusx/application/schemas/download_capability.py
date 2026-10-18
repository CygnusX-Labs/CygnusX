"""Server-owned declared capabilities. No binary or runtime attestation is inferred."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


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
    verification_status: Literal["SUPPORTED_BY_CODE"] = "SUPPORTED_BY_CODE"
    runtime_readiness: Literal["BLOCKED"] = "BLOCKED"
    enabled_by_configuration: bool = False
    limitations: tuple[str, ...]


class DownloadCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["cygnusx.download_capabilities.v1"] = "cygnusx.download_capabilities.v1"
    sources: tuple[DownloadSourceCapability, ...]
    runtime_status: Literal["BLOCKED"] = "BLOCKED"
    write_enabled: Literal[False] = False
    candidate_accessions: tuple[str, ...] = ("SRR", "PRJNA")
    runtime_verified_accessions: tuple[str, ...] = ()
    limits: dict[str, int | bool | None]
    legacy_method_policy: str = (
        "aws/ftp retained; aspera/prefetch/auto refused; no silent remapping"
    )
