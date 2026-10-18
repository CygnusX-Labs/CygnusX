"""Versioned shared capability contract. Identity is never a tool argument."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cygnusx.application.schemas.dataset import DatasetAnalysisPrepare, ImportPrepare
from cygnusx.application.schemas.research_plan import PlanPrepare, ResearchPlanDraft


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EmptyArgs(ToolArgs):
    pass


class WorkflowArgs(ToolArgs):
    flow_id: str = Field(min_length=1, max_length=80)


class AnalysisPrepareArgs(WorkflowArgs):
    arguments: dict[str, Any]


class DownloadPrepareArgs(ToolArgs):
    accession: str = Field(min_length=1, max_length=40)
    download_method: Literal["ftp", "aws"] = "ftp"


class TaskArgs(ToolArgs):
    task_id: str = Field(pattern=r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")


class ExecuteArgs(ToolArgs):
    proposal_id: str = Field(pattern=r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")


class DatasetDiscoverArgs(ToolArgs):
    accession: str = Field(min_length=4, max_length=40)


class DatasetVersionArgs(ToolArgs):
    dataset_id: str = Field(pattern=r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
    version_id: str = Field(pattern=r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")


class DatasetImportArgs(ToolArgs):
    request: ImportPrepare


class DatasetAnalysisArgs(DatasetVersionArgs):
    request: DatasetAnalysisPrepare


class AgentToolCall(ToolArgs):
    capability_id: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)
    call_id: str = Field(default="", max_length=80)


class ToolProposal(BaseModel):
    proposal_id: str
    conversation_id: str
    operation: Literal["downloads.submit", "analysis.submit"]
    project_id: str | None
    parameters_hash: str
    normalized_parameters: dict[str, Any]
    preview: dict[str, Any]
    confirmation_id: str
    expires_at: str
    state: str
    write_enabled: Literal[False] = False
    gate: Literal["WRITE_GATE_BLOCKED"] = "WRITE_GATE_BLOCKED"


class TaskStatusView(BaseModel):
    task_id: str
    status: str
    progress: None = None
    progress_status: Literal["unavailable"] = "unavailable"
    error_summary: str
    task_url: str


class GatewayResult(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    invocation_id: str
    result: dict[str, Any] | list[Any]


class ToolCapability(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    capability_id: str
    tool_name: str
    description: str
    scope: str
    side_effect: Literal["none", "confirmation", "task"]
    input_schema: dict[str, Any]
    approval: str = "none"
    idempotency: str = "no_business_task"
    owner_source: str = "authenticated_principal_and_owned_session"
    result_schema: dict[str, Any] = Field(default_factory=GatewayResult.model_json_schema)
    errors: list[str] = Field(
        default_factory=lambda: [
            "FEATURE_DISABLED",
            "FORBIDDEN",
            "NOT_FOUND",
            "VALIDATION_ERROR",
            "CONFIRMATION_STORE_UNAVAILABLE",
            "WRITE_GATE_BLOCKED",
        ]
    )
    agents: list[str] = Field(default_factory=lambda: ["research_treasure_mouse", "platform_ai"])


# Single schema authority; MCP and REST views are projections of these models.
class ReportEvidenceArgs(ToolArgs):
    report_id: str = Field(pattern=r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")


class PlanPrepareArgs(ToolArgs):
    request: PlanPrepare


class PlanValidateArgs(ToolArgs):
    draft: ResearchPlanDraft


class PlanGetArgs(ToolArgs):
    plan_id: str = Field(pattern=r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")


CAPABILITY_MODELS: dict[str, type[ToolArgs]] = {
    "research.plan.prepare": PlanPrepareArgs,
    "research.plan.validate": PlanValidateArgs,
    "research.plan.get_status": PlanGetArgs,
    "research.plan.get_evidence": PlanGetArgs,
    "downloads.describe_capabilities": EmptyArgs,
    "downloads.prepare": DownloadPrepareArgs,
    "analysis.list_workflows": EmptyArgs,
    "analysis.get_workflow_schema": WorkflowArgs,
    "analysis.prepare": AnalysisPrepareArgs,
    "tasks.get_status": TaskArgs,
    "research.task_provenance": TaskArgs,
    "research.report_provenance": ReportEvidenceArgs,
    "research.dataset_provenance": DatasetVersionArgs,
    "research.project_delivery": EmptyArgs,
    "tasks.list_related": EmptyArgs,
    "dataset.discover": DatasetDiscoverArgs,
    "dataset.inspect": DatasetVersionArgs,
    "dataset.list_files": DatasetVersionArgs,
    "dataset.list_project_assets": EmptyArgs,
    "dataset.prepare_import": DatasetImportArgs,
    "analysis.list_compatible_workflows": DatasetVersionArgs,
    "analysis.prepare_from_dataset": DatasetAnalysisArgs,
    "dataset.execute_import": ExecuteArgs,
    "downloads.submit": ExecuteArgs,
    "analysis.submit": ExecuteArgs,
    "tasks.cancel": ExecuteArgs,
}


def capability_catalog(
    *,
    include_write: bool = False,
    include_dataset: bool = False,
    include_research: bool = False,
    include_plans: bool = False,
) -> list[ToolCapability]:
    catalog: list[ToolCapability] = []
    for name, model in CAPABILITY_MODELS.items():
        if name.startswith("research.plan."):
            if not include_plans:
                continue
        elif name.startswith("research.") and not include_research:
            continue
        if not include_dataset and (
            name.startswith("dataset.")
            or name in {"analysis.list_compatible_workflows", "analysis.prepare_from_dataset"}
        ):
            continue
        write = name.endswith(".submit") or name in {"tasks.cancel", "dataset.execute_import"}
        if write and not include_write:
            continue
        prepare = (name.endswith(".prepare") and not name.startswith("research.plan.")) or name in {
            "dataset.prepare_import",
            "analysis.prepare_from_dataset",
        }
        scope = (
            "read:research"
            if name.startswith("research.")
            else "execute:cancel"
            if name == "tasks.cancel"
            else "execute:download"
            if name in {"downloads.submit", "dataset.execute_import"}
            else "execute:analysis"
            if name == "analysis.submit"
            else "prepare:download"
            if name in {"downloads.prepare", "dataset.prepare_import"}
            else "prepare:analysis"
            if name in {"analysis.prepare", "analysis.prepare_from_dataset"}
            else "read:datasets"
            if name.startswith("dataset.") or name == "analysis.list_compatible_workflows"
            else "read:tasks"
            if name.startswith("tasks.")
            else "read:workflows"
            if name.startswith("analysis.")
            else "read:discovery"
        )
        catalog.append(
            ToolCapability(
                capability_id=name,
                tool_name="bioops_" + name.replace(".", "_"),
                description=name + " (platform controlled; never self-approve)",
                scope=scope,
                side_effect="task" if write else "confirmation" if prepare else "none",
                input_schema=model.model_json_schema(),
                approval="human_jwt" if write or prepare else "none",
                idempotency="proposal_once_or_reconciliation" if write else "no_business_task",
            )
        )
    return catalog
