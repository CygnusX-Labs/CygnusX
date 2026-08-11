"""Read-only execution kernel for AgentTeams professional consultations."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.services.agent_service import AgentService
from omichub.application.services.parallel_subagent_service import ParallelSubAgentService
from omichub.core.exceptions import NotFoundError
from omichub.domain.file.entities import DataFile
from omichub.domain.file.value_objects import FileType
from omichub.infrastructure.database.repositories.file_repository import FileRepositoryImpl
from omichub.infrastructure.storage.path_factory import get_path_factory

ALLOWED_CONSULTATION_AGENTS = {
    "agent-data",
    "agent-qc",
    "agent-delivery",
    "agent-rnaseq",
    "agent-scrna",
    "agent-code",
    "agent-viz",
}
_JSON_FENCE_RE = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)

_WORKSPACE_EXEC_PROTOCOL_PATH = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "ai"
    / "prompts"
    / "shared"
    / "agentteams_workspace_execution.md"
)


class ConsultationEnvelope(BaseModel):
    conclusion: str = Field(min_length=1, max_length=8_000)
    recommendations: list[str] = Field(default_factory=list, max_length=100)
    evidence_refs: list[str] = Field(default_factory=list, max_length=100)
    risks: list[str] = Field(default_factory=list, max_length=100)
    token_usage: int = Field(default=0, ge=0)
    proposed_submission: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list, max_length=100)


class AgentConsultationService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        agent_service: AgentService | None = None,
        parallel_service: ParallelSubAgentService | None = None,
    ) -> None:
        self._db = db
        self._agent_service = agent_service or AgentService(db)
        self._parallel_service = parallel_service or ParallelSubAgentService()

    async def run_consultation(
        self,
        *,
        case_id: str,
        agent_id: str,
        question: str,
        capability: str,
        evidence_refs: list[str],
        requested_tools: list[str],
        requester_ref: str,
        work_item_id: str | None = None,
        execution_mode: str = "readonly_consultation",
    ) -> ConsultationEnvelope:
        started = time.monotonic()
        if agent_id not in ALLOWED_CONSULTATION_AGENTS:
            raise NotFoundError(f"Agent {agent_id} 不存在或未启用")
        if execution_mode not in {"readonly_consultation", "workspace_execution"}:
            raise ValueError("Unsupported AgentTeams execution mode")
        if execution_mode == "workspace_execution" and (agent_id not in {"agent-code", "agent-viz"} or not work_item_id):
            raise ValueError("Workspace execution requires agent-code or agent-viz and a work item")
        context = await self._agent_service.assemble_context(agent_id, user_id=requester_ref)
        if context is None or context.model_config is None:
            raise NotFoundError(f"Agent {agent_id} 不存在或未启用")

        instruction = self._build_instruction(
            question=question,
            capability=capability,
            evidence_refs=evidence_refs,
            requested_tools=requested_tools,
            execution_mode=execution_mode,
        )
        workdir_root = (
            Path("/data/omichub") / "output" / "agentteams" / case_id / work_item_id
            if execution_mode == "workspace_execution" and work_item_id
            else None
        )
        result = await self._parallel_service.run(
            user_id=requester_ref,
            parent_agent_id="agent-general",
            parent_session_id=f"agentteams:{case_id}",
            context_summary=f"AgentTeams Case {case_id} 的受控专业会诊",
            tasks=[
                {
                    "task_id": f"consultation:{case_id}:{work_item_id or agent_id}",
                    "agent_id": agent_id,
                    "task": instruction,
                    "workspace_access": execution_mode == "workspace_execution",
                }
            ],
            db=self._db,
            safe_only=execution_mode == "readonly_consultation",
            runtime_authorized=True,
            workdir_root=workdir_root,
        )
        raw_answer = self._extract_answer(result)
        envelope = self.parse_envelope(raw_answer)
        if execution_mode == "workspace_execution" and workdir_root is not None:
            artifacts, errors = await self._register_workspace_artifacts(
                requester_ref, case_id, work_item_id or "", workdir_root
            )
            envelope.artifacts = artifacts
            envelope.risks.extend(errors)
        logger.bind(
            case_id=case_id,
            agent_id=agent_id,
            requester_ref=requester_ref,
            duration_ms=round((time.monotonic() - started) * 1000),
            token_usage=envelope.token_usage,
        ).info("AgentTeams consultation completed")
        return envelope

    @staticmethod
    def _workspace_execution_protocol() -> str:
        """加载工作区执行模式追加契约；文件缺失时返回兜底摘要。"""
        try:
            return _WORKSPACE_EXEC_PROTOCOL_PATH.read_text(encoding="utf-8")
        except OSError:
            return "仅可在分配工作目录内写入；不得修改数据库、任务或工作流。\n"

    @staticmethod
    def _build_instruction(
        *,
        question: str,
        capability: str,
        evidence_refs: list[str],
        requested_tools: list[str],
        execution_mode: str,
    ) -> str:
        if execution_mode == "workspace_execution":
            mode_clause = f"\n{AgentConsultationService._workspace_execution_protocol()}\n"
            envelope_clause = ""
        else:
            mode_clause = "不得修改文件、数据库、任务或工作流。\n"
            envelope_clause = (
                "最终答复必须只包含一个 ```json 代码块，结构为："
                '{"conclusion":"非空结论","recommendations":[],"evidence_refs":[],"risks":[],'
                '"token_usage":0,"proposed_submission":null,"artifacts":[]}。规划能力调用时 '
                "proposed_submission 必须是可校验的 TaskSpec 参数对象。"
            )
        return (
            "你正在执行 AgentTeams 受控专业会诊。\n"
            + mode_clause
            + f"\n能力：{capability}\n问题：{question}\n"
            f"证据引用：{json.dumps(evidence_refs, ensure_ascii=False)}\n"
            f"获准请求的只读工具：{json.dumps(requested_tools, ensure_ascii=False)}\n"
            + envelope_clause
        )

    async def _register_workspace_artifacts(
        self, requester_ref: str, case_id: str, work_item_id: str, workdir: Path
    ) -> tuple[list[dict[str, Any]], list[str]]:
        try:
            user_id = UUID(str(requester_ref))
        except ValueError:
            return [], ["产物登记失败：requester_ref 不是有效用户 UUID。"]
        if not workdir.exists():
            return [], []
        factory = get_path_factory()
        destination = factory.user_root(str(user_id)) / "workspace" / "agentteams" / case_id / work_item_id
        repository = FileRepositoryImpl(self._db)
        artifacts: list[dict[str, Any]] = []
        errors: list[str] = []
        sources = sorted(path for path in workdir.rglob("*") if path.is_file() and not path.is_symlink())[:100]
        for source in sources:
            try:
                relative = source.relative_to(workdir)
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                record = await repository.save(
                    DataFile(
                        id=uuid4(), user_id=user_id, path=factory.relative_to_root(target),
                        original_name=source.name, size=source.stat().st_size,
                        checksum=hashlib.sha256(source.read_bytes()).hexdigest(),
                        file_type=FileType.OTHER,
                        directory=f"workspace/agentteams/{case_id}/{work_item_id}", source="agentteams",
                    )
                )
                artifacts.append({"path": record.path, "kind": "file", "bytes": record.size})
            except (OSError, ValueError) as exc:
                errors.append(f"产物登记失败（{source.name}）：{exc}")
        return artifacts, errors

    @staticmethod
    def _extract_answer(result: dict[str, Any]) -> str:
        results = (result.get("llm_payload") or {}).get("results") or []
        if results and isinstance(results[0], dict):
            answer = str(results[0].get("answer") or "").strip()
            if answer:
                return answer
            error = str(results[0].get("error") or "").strip()
            if error:
                return error
        return str((result.get("llm_payload") or {}).get("summary") or "会诊未返回内容")

    @staticmethod
    def parse_envelope(raw_answer: str) -> ConsultationEnvelope:
        raw_answer = raw_answer.strip() or "会诊未返回内容"
        match = _JSON_FENCE_RE.search(raw_answer)
        candidate = match.group(1) if match else raw_answer
        try:
            payload = json.loads(candidate)
            if not isinstance(payload, dict):
                raise ValueError("consultation envelope must be an object")
            return ConsultationEnvelope.model_validate(payload)
        except (json.JSONDecodeError, ValueError):
            return ConsultationEnvelope(
                conclusion=raw_answer[:8_000],
                risks=["信封解析降级：专家答复未满足结构化 JSON 契约。"],
            )
