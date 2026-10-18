"""RI12 v2 definition and RI13 task binding; v1 digests remain unchanged."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from cygnusx.application.schemas.execution_definition import (
    SHA256,
    DefinitionParameter,
    ExecutionFileRef,
    ExecutionResources,
    FrozenDefinitionPart,
)


def canonical_digest(payload: object) -> str:
    content = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


class ExecutionDefinitionV2(FrozenDefinitionPart):
    schema_version: Literal["cygnusx.execution_definition.v2"] = "cygnusx.execution_definition.v2"
    digest_policy: Literal["canonical_definition.v2"] = "canonical_definition.v2"
    workflow_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    flow_config_sha256: str = Field(pattern=SHA256)
    parameters_sha256: str = Field(pattern=SHA256)
    sample_design_digest: str = Field(pattern=SHA256)
    dataset_version_id: UUID | None = None
    handoff_digest: str | None = Field(default=None, pattern=SHA256)
    workflow_release_digest: str | None = Field(default=None, pattern=SHA256)
    container_image_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    input_refs: tuple[ExecutionFileRef, ...] = ()
    reference_refs: tuple[ExecutionFileRef, ...] = ()
    normalized_parameters: tuple[DefinitionParameter, ...] = ()
    resource_specification: ExecutionResources = ExecutionResources()
    provenance_status: Literal["DECLARED"] = "DECLARED"

    @model_validator(mode="after")
    def unique_identifiers(self) -> ExecutionDefinitionV2:
        for refs in (self.input_refs, self.reference_refs):
            ids = [item.file_record_id for item in refs]
            if len(set(ids)) != len(ids):
                raise ValueError("Duplicate file identity")
        names = [item.name for item in self.normalized_parameters]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate parameter")
        return self

    def content_digest(self) -> str:
        data = self.model_dump(mode="json")
        for field in ("input_refs", "reference_refs"):
            data[field] = sorted(data[field], key=lambda item: item["file_record_id"])
        data["normalized_parameters"] = sorted(
            data["normalized_parameters"], key=lambda item: item["name"]
        )
        return canonical_digest(data)


class ExecutionTaskBinding(FrozenDefinitionPart):
    schema_version: Literal["cygnusx.execution_task_binding.v1"] = (
        "cygnusx.execution_task_binding.v1"
    )
    task_id: UUID
    owner_id: UUID
    definition_digest: str = Field(pattern=SHA256)
    generated_files_digest: str = Field(pattern=SHA256)

    def content_digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


class WorkerEvidence(FrozenDefinitionPart):
    recorded_at: datetime
    phase: Literal["PREFLIGHT", "POSTFLIGHT", "FAILED"]
    input_integrity: Literal["VERIFIED", "NOT_OBSERVED", "FAILED"]
    workflow_release_status: Literal["NOT_OBSERVED"] = "NOT_OBSERVED"
    image_status: Literal["NOT_OBSERVED"] = "NOT_OBSERVED"
    tools_status: Literal["NOT_OBSERVED"] = "NOT_OBSERVED"
    reference_status: Literal["NOT_OBSERVED"] = "NOT_OBSERVED"
    reason_code: Literal["INPUT_OR_BINDING_CHANGED", "EXECUTION_FAILED"] | None = None


class GeneratedExecutionFile(FrozenDefinitionPart):
    name: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    sha256: str = Field(pattern=SHA256)


class ExecutionEvidence(FrozenDefinitionPart):
    schema_version: Literal["cygnusx.execution_evidence.v1"] = "cygnusx.execution_evidence.v1"
    definition: ExecutionDefinitionV2
    definition_digest: str = Field(pattern=SHA256)
    binding: ExecutionTaskBinding
    execution_binding_digest: str = Field(pattern=SHA256)
    frozen_at: datetime
    generated_files: tuple[GeneratedExecutionFile, ...] = Field(default=(), max_length=16)
    observations: tuple[WorkerEvidence, ...] = Field(default=(), max_length=256)

    @model_validator(mode="after")
    def verify_digests(self) -> ExecutionEvidence:
        if (
            self.definition_digest != self.definition.content_digest()
            or self.binding.definition_digest != self.definition_digest
            or self.execution_binding_digest != self.binding.content_digest()
            or self.binding.generated_files_digest
            != canonical_digest([item.model_dump(mode="json") for item in self.generated_files])
        ):
            raise ValueError("Execution evidence digest mismatch")
        return self
