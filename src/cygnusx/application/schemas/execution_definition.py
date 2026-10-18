"""RI12 design contract only. No persistence, backfill, authorization or execution adapter."""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SHA256 = r"^[0-9a-f]{64}$"


class FrozenDefinitionPart(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExecutionFileRef(FrozenDefinitionPart):
    file_record_id: UUID
    sha256: str | None = Field(default=None, pattern=SHA256)
    role: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    status: Literal["DECLARED", "UNKNOWN"] = "UNKNOWN"


class DefinitionParameter(FrozenDefinitionPart):
    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,79}$")
    value_json: str = Field(max_length=16384)

    @model_validator(mode="after")
    def safe_parameter(self) -> DefinitionParameter:
        def inspect(value: object) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if re.search(
                        r"token|secret|password|credential|authorization|api_key|path|directory|command|shell",
                        str(key),
                        re.I,
                    ):
                        raise ValueError("定义不接受敏感字段、命令或服务器路径")
                    inspect(item)
            elif isinstance(value, list):
                for item in value:
                    inspect(item)
            elif isinstance(value, float) and not math.isfinite(value):
                raise ValueError("定义不接受非有限数值")
            elif isinstance(value, str) and (
                value.startswith(("/", "file:", "Bearer "))
                or re.search(r"(?:token|secret|signature|password)=", value, re.I)
            ):
                raise ValueError("定义不接受凭据或服务器路径")

        inspect({self.name: json.loads(self.value_json)})
        return self

    @field_validator("value_json")
    @classmethod
    def canonical_value(cls, value: str) -> str:
        def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, item in items:
                if key in result:
                    raise ValueError("重复JSON键")
                result[key] = item
            return result

        parsed = json.loads(value, object_pairs_hook=pairs)
        return json.dumps(
            parsed, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )


class ExecutionResources(FrozenDefinitionPart):
    cores: int | None = Field(default=None, ge=1, le=1024)
    memory_bytes: int | None = Field(default=None, ge=1)
    time_seconds: int | None = Field(default=None, ge=1)


class ExecutionDefinition(FrozenDefinitionPart):
    schema_version: Literal["cygnusx.execution_definition.v1"] = "cygnusx.execution_definition.v1"
    digest_policy: Literal["canonical_definition.v1"] = "canonical_definition.v1"
    task_id: UUID | None = None
    dataset_version_id: UUID | None = None
    handoff_digest: str | None = Field(default=None, pattern=SHA256)
    workflow_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    workflow_release_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    workflow_release_digest: str | None = Field(default=None, pattern=SHA256)
    container_image_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    input_refs: tuple[ExecutionFileRef, ...] = Field(default=(), max_length=2000)
    reference_refs: tuple[ExecutionFileRef, ...] = Field(default=(), max_length=2000)
    normalized_parameters: tuple[DefinitionParameter, ...] = Field(default=(), max_length=200)
    sample_design_digest: str | None = Field(default=None, pattern=SHA256)
    resource_specification: ExecutionResources = ExecutionResources()
    comparison_policy: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    provenance_status: Literal["DECLARED", "UNKNOWN"] = "UNKNOWN"

    @model_validator(mode="after")
    def unique_refs(self) -> ExecutionDefinition:
        for refs in (self.input_refs, self.reference_refs):
            ids = [item.file_record_id for item in refs]
            if len(ids) != len(set(ids)):
                raise ValueError("文件引用重复")
        names = [item.name for item in self.normalized_parameters]
        if len(names) != len(set(names)):
            raise ValueError("参数重复")
        return self

    def canonical_bytes(self) -> bytes:
        payload = self.model_dump(mode="json")
        for name in ("input_refs", "reference_refs"):
            payload[name] = sorted(payload[name], key=lambda item: item["file_record_id"])
        payload["normalized_parameters"] = sorted(
            payload["normalized_parameters"], key=lambda item: item["name"]
        )
        return json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")

    def content_digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()
