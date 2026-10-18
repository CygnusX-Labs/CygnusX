"""Public dataset input contracts: IDs and evidence, never server paths/tokens."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DatasetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DataType(StrEnum):
    RAW_FASTQ = "RAW_FASTQ"
    RAW_INTEGER_COUNTS = "RAW_INTEGER_COUNTS"
    NORMALIZED_EXPRESSION_TPM = "NORMALIZED_EXPRESSION_TPM"
    NORMALIZED_EXPRESSION_FPKM = "NORMALIZED_EXPRESSION_FPKM"
    NORMALIZED_EXPRESSION_CPM = "NORMALIZED_EXPRESSION_CPM"
    TRANSFORMED_EXPRESSION = "TRANSFORMED_EXPRESSION"
    MICROARRAY_EXPRESSION = "MICROARRAY_EXPRESSION"
    SINGLE_CELL_COUNT_MATRIX = "SINGLE_CELL_COUNT_MATRIX"
    SAMPLE_METADATA = "SAMPLE_METADATA"
    UNKNOWN = "UNKNOWN"


class DatasetCreate(DatasetInput):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    assay_type: Literal["bulk_rnaseq", "microarray", "scrna", "unknown"] = "unknown"


class VersionCreate(DatasetInput):
    revision_reason: str = Field(min_length=1, max_length=2000)


class AssetAttach(DatasetInput):
    file_record_id: UUID
    role: Literal[
        "raw_reads",
        "raw_counts",
        "normalized_expression",
        "metadata",
        "annotation",
        "archive",
        "other",
    ] = "other"


class SampleAttach(DatasetInput):
    sample_id: UUID
    sample_key: str = Field(min_length=1, max_length=200)
    file_record_ids: list[UUID] = Field(default_factory=list, max_length=500)
    source_accessions: list[str] = Field(default_factory=list, max_length=100)
    group: str | None = Field(default=None, max_length=100)
    group_confirmed: bool = False


class HandoffAsset(DatasetInput):
    asset_id: UUID
    file_record_id: UUID
    asset_role: str
    data_type: DataType
    format: str
    size: int
    sha256: str | None
    checksum_status: str
    availability: str


class DataHandoff(DatasetInput):
    handoff_schema_version: Literal["1.0"] = "1.0"
    project_id: UUID
    dataset_id: UUID
    dataset_version_id: UUID
    source: list[dict[str, Any]]
    ingestion: list[dict[str, Any]]
    assets: list[HandoffAsset]
    samples: list[dict[str, Any]]
    validation: dict[str, Any]
    provenance: dict[str, Any]
    manifest_hash: str | None = None


class ImportPrepare(DatasetInput):
    dataset_id: UUID | None = None
    accession: str = Field(min_length=4, max_length=40)
    mode: Literal["raw", "processed"]
    selected_ids: list[str] = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    request_key: UUID
    max_bytes: int = Field(gt=0)


class DatasetAnalysisPrepare(DatasetInput):
    flow_id: str = Field(min_length=1, max_length=80)
    options: dict[str, Any] = Field(default_factory=dict)


class SampleGroupReview(DatasetInput):
    group: str = Field(min_length=1, max_length=100)


class VersionReview(DatasetInput):
    assay_type: Literal["bulk_rnaseq", "microarray", "scrna", "unknown"]
    reason: str = Field(min_length=1, max_length=2000)


class AssetRoleReview(DatasetInput):
    role: Literal[
        "raw_reads",
        "raw_counts",
        "normalized_expression",
        "metadata",
        "annotation",
        "archive",
        "other",
    ]
    reason: str = Field(min_length=1, max_length=2000)
