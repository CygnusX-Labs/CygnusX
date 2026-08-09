"""Research-first planning for the overdrive v2 runtime.

The orchestration layer deliberately receives search and model callables instead of
importing ``ChatService``.  This keeps planning read-only, testable, and usable by
both the legacy chat loop and LangGraph-backed agents.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from omichub.application.services.overdrive_run_service import (
    OverdriveRunService,
    validate_plan,
)
from omichub.core.exceptions import ValidationError
from omichub.infrastructure.database.models.overdrive import OverdriveRunModel

ResearchCallable = Callable[..., Awaitable[Any]]
PlanBuilder = Callable[..., Awaitable[Mapping[str, Any]] | Mapping[str, Any]]

SOURCE_TYPES = ("knowledge_base", "web", "model_knowledge")
DOMAIN_HINTS: dict[str, tuple[str, ...]] = {
    "agent-rnaseq": ("rna-seq", "rnaseq", "bulk rna", "转录组", "差异表达", "deseq"),
    "agent-atacseq": ("atac-seq", "atacseq", "染色质开放", "peak calling", "可及性"),
    "agent-scrna": ("scrna", "单细胞", "single-cell", "细胞注释", "细胞通讯"),
    "agent-viz": ("可视化", "绘图", "图表", "publication-ready"),
    "agent-code": ("代码", "python", "bash", "脚本", "调试"),
    "agent-data": ("数据契约", "元数据", "样本对应", "输入核验"),
}


@dataclass(frozen=True)
class ResearchBundle:
    """Normalized evidence plus an honest per-source execution ledger."""

    evidence: list[dict[str, Any]]
    sources: dict[str, dict[str, Any]]

    @property
    def statuses(self) -> dict[str, str]:
        return {source: str(record["status"]) for source, record in self.sources.items()}


class ResearchBundleService:
    """Run KB and web IO concurrently, then obtain separate model knowledge."""

    def __init__(
        self,
        *,
        knowledge_search: ResearchCallable,
        web_search: ResearchCallable,
        model_knowledge: ResearchCallable,
        source_timeout_seconds: float = 20,
        wall_timeout_seconds: float = 45,
        max_evidence_items_per_source: int = 8,
    ) -> None:
        self._knowledge_search = knowledge_search
        self._web_search = web_search
        self._model_knowledge = model_knowledge
        self._source_timeout = max(0.01, float(source_timeout_seconds))
        self._wall_timeout = max(self._source_timeout, float(wall_timeout_seconds))
        self._max_items = max(1, int(max_evidence_items_per_source))

    async def collect(
        self,
        query: str,
        *,
        project_id: str | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> ResearchBundle:
        if not query.strip():
            raise ValidationError("研究问题不能为空")
        started = time.monotonic()
        kb_task = asyncio.create_task(
            self._call_retrieval(
                "knowledge_base",
                self._knowledge_search,
                query,
                project_id=project_id,
            )
        )
        web_task = asyncio.create_task(self._call_retrieval("web", self._web_search, query))
        kb_record, web_record = await asyncio.gather(kb_task, web_task)

        remaining = max(0.01, self._wall_timeout - (time.monotonic() - started))
        model_record = await self._call_model(
            query,
            [*kb_record["items"], *web_record["items"]],
            context=context,
            timeout_seconds=min(self._source_timeout, remaining),
        )
        sources = {
            "knowledge_base": kb_record,
            "web": web_record,
            "model_knowledge": model_record,
        }
        evidence: list[dict[str, Any]] = []
        next_id = 1
        for source in SOURCE_TYPES:
            record = sources[source]
            for raw_item in record.pop("items"):
                item = self._evidence_item(source, raw_item, next_id)
                if item is None:
                    continue
                evidence.append(item)
                record["evidence_ids"].append(item["evidence_id"])
                next_id += 1
        return ResearchBundle(evidence=evidence, sources=sources)

    async def _call_retrieval(
        self,
        source: str,
        function: ResearchCallable,
        query: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            raw = await asyncio.wait_for(
                self._invoke(function, query, **kwargs), timeout=self._source_timeout
            )
            items = self._unwrap_items(raw)
            return self._source_record("succeeded", started, items=items)
        except TimeoutError:
            return self._source_record(
                "timed_out", started, error=f"{source} research timed out"
            )
        except Exception as exc:  # noqa: BLE001 - one unavailable source must not block planning
            return self._source_record("failed", started, error=self._safe_error(exc))

    async def _call_model(
        self,
        query: str,
        retrieved_evidence: list[dict[str, Any]],
        *,
        context: Mapping[str, Any] | None,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            raw = await asyncio.wait_for(
                self._invoke(
                    self._model_knowledge,
                    query,
                    retrieved_evidence=deepcopy(retrieved_evidence),
                    context=deepcopy(dict(context or {})),
                ),
                timeout=timeout_seconds,
            )
            return self._source_record("completed", started, items=self._unwrap_items(raw))
        except TimeoutError:
            return self._source_record(
                "timed_out", started, error="model knowledge synthesis timed out"
            )
        except Exception as exc:  # noqa: BLE001
            return self._source_record("failed", started, error=self._safe_error(exc))

    async def _invoke(self, function: ResearchCallable, query: str, **kwargs: Any) -> Any:
        """Pass only accepted optional kwargs so existing tool adapters plug in directly."""
        try:
            signature = inspect.signature(function)
            accepts_kwargs = any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in signature.parameters.values()
            )
            accepted = kwargs if accepts_kwargs else {
                key: value for key, value in kwargs.items() if key in signature.parameters
            }
        except (TypeError, ValueError):
            accepted = kwargs
        return await function(query, **accepted)

    def _unwrap_items(self, raw: Any) -> list[dict[str, Any]]:
        if isinstance(raw, Mapping) and raw.get("success") is False:
            raise RuntimeError(str(raw.get("error") or "research source returned failure"))
        value = raw
        if isinstance(value, Mapping) and "result" in value:
            value = value["result"]
        if isinstance(value, Mapping):
            value = value.get("results", value.get("items", value.get("evidence", [])))
        if value is None:
            return []
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise ValueError("research source did not return an item list")
        return [deepcopy(dict(item)) for item in value[: self._max_items] if isinstance(item, Mapping)]

    @staticmethod
    def _source_record(
        status: str,
        started: float,
        *,
        items: list[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        record: dict[str, Any] = {
            "status": status,
            "evidence_ids": [],
            "duration_ms": max(0, round((time.monotonic() - started) * 1000)),
            "items": items or [],
        }
        if error:
            record["error"] = error
        return record

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        message = re.sub(r"(?i)(api[_-]?key|token|authorization)\s*[:=]\s*\S+", r"\1=[REDACTED]", str(exc))
        return (message or type(exc).__name__)[:500]

    @staticmethod
    def _evidence_item(
        source: str, raw: Mapping[str, Any], sequence: int
    ) -> dict[str, Any] | None:
        title = str(raw.get("title") or raw.get("name") or "").strip()
        claim = str(
            raw.get("claim")
            or raw.get("excerpt")
            or raw.get("snippet")
            or raw.get("content")
            or raw.get("text")
            or ""
        ).strip()
        if not title and not claim:
            return None
        if source == "model_knowledge":
            locator = ""
            freshness = "not_applicable"
        elif source == "web":
            locator = str(raw.get("url") or raw.get("link") or "").strip()
            freshness = str(raw.get("freshness") or "current")
        else:
            locator = str(raw.get("url") or "").strip()
            if not locator:
                doc_id = str(raw.get("doc_id") or raw.get("id") or "unknown")
                section = str(raw.get("section_path") or "").strip()
                locator = f"kb://{doc_id}" + (f"#{section}" if section else "")
            freshness = str(raw.get("freshness") or "possibly_stale")
        return {
            "evidence_id": f"ev-{sequence:03d}",
            "source_type": source,
            "title": title or claim[:80],
            "locator": locator,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "freshness": freshness,
            "claim": claim,
            "confidence": str(raw.get("confidence") or "medium"),
            "used_in_plan_sections": list(raw.get("used_in_plan_sections") or []),
        }


class OverdrivePlanningService:
    """Coordinate research, deterministic Markdown construction, review, and freeze."""

    def __init__(
        self,
        run_service: OverdriveRunService,
        research_service: ResearchBundleService,
        plan_builder: PlanBuilder,
    ) -> None:
        self._runs = run_service
        self._research = research_service
        self._plan_builder = plan_builder

    @staticmethod
    def select_lead_planner(
        request: str, agent_catalog: Sequence[Mapping[str, Any]]
    ) -> dict[str, Any]:
        """Choose one smallest capability-matched planner, with general as fallback."""
        if not request.strip():
            raise ValidationError("任务方向不能为空")
        active = [item for item in agent_catalog if item.get("is_active", True)]
        if not active:
            raise ValidationError("没有可用的规划 Agent")
        normalized = request.casefold()
        scored: list[tuple[int, str, Mapping[str, Any], list[str]]] = []
        for candidate in active:
            agent_id = str(candidate.get("agent_id") or "").strip()
            if not agent_id:
                continue
            features = candidate.get("features") or {}
            if not isinstance(features, Mapping):
                features = {}
            terms = [
                *DOMAIN_HINTS.get(agent_id, ()),
                *(str(value) for value in features.get("capability_scope") or []),
                *(str(value) for value in features.get("capability_tags") or []),
            ]
            matches = sorted({term for term in terms if term and term.casefold() in normalized})
            score = len(matches) * 10 - (1 if agent_id == "agent-general" else 0)
            scored.append((score, agent_id, candidate, matches))
        if not scored:
            raise ValidationError("Agent catalog 缺少有效 agent_id")
        matched = [item for item in scored if item[0] > 0]
        if matched:
            score, agent_id, _candidate, matches = max(matched, key=lambda item: (item[0], item[1]))
            reason = f"任务命中规划能力：{', '.join(matches)}"
        else:
            general = next((item for item in scored if item[1] == "agent-general"), None)
            score, agent_id, _candidate, matches = general or max(
                scored, key=lambda item: (item[0], item[1])
            )
            reason = "任务方向未命中特定领域，由通用规划 Agent 完成 intake 与跨域方案"
        return {
            "lead_planner_agent_id": agent_id,
            "advisor_agent_ids": [],
            "reason": reason,
            "matched_capabilities": matches,
            "score": score,
        }

    async def prepare_plan(
        self,
        run: OverdriveRunModel,
        *,
        known_agent_ids: set[str],
        project_id: str | None = None,
        revision_feedback: str = "",
    ) -> dict[str, Any]:
        await self._runs.transition(run, "RESEARCHING")
        bundle = await self._research.collect(
            run.root_request,
            project_id=project_id,
            context={
                "lead_planner_agent_id": run.lead_planner_agent_id,
                "revision_feedback": revision_feedback,
            },
        )
        await self._runs.save_research(
            run,
            bundle.evidence,
            bundle.statuses,
            source_details=bundle.sources,
        )
        await self._runs.transition(run, "PLAN_DRAFTED")
        plan_payload = await self._maybe_await(
            self._plan_builder(
                request=run.root_request,
                lead_planner_agent_id=run.lead_planner_agent_id,
                research=deepcopy(bundle.evidence),
                research_sources=deepcopy(bundle.sources),
                revision_feedback=revision_feedback,
            )
        )
        if not isinstance(plan_payload, Mapping):
            raise ValidationError("规划 Agent 未返回结构化计划")
        tasks = [deepcopy(dict(item)) for item in plan_payload.get("tasks") or []]
        tasks = self.ensure_independent_qc_task(tasks, known_agent_ids)
        content = str(plan_payload.get("content") or "").strip()
        if not content:
            content = build_plan_markdown(
                request=run.root_request,
                lead_planner_agent_id=str(run.lead_planner_agent_id or ""),
                evidence=bundle.evidence,
                tasks=tasks,
                plan=deepcopy(dict(plan_payload)),
                next_version=int((run.plan or {}).get("version") or 0) + 1,
            )
        validate_plan(content, tasks, known_agent_ids)
        await self._runs.transition(run, "PLAN_REVIEWING")
        draft_file = await self._runs.write_plan_draft(run, content)
        next_version = int(draft_file["version"])
        await self._runs.append_event(
            run.run_id,
            "plan_ready",
            {
                "lead_planner_agent_id": run.lead_planner_agent_id,
                "evidence_count": len(bundle.evidence),
                "plan_path": draft_file["path"],
            },
            dedupe_key=f"plan_ready:{next_version}",
        )
        await self._runs.append_event(
            run.run_id,
            "plan_review_passed",
            {
                "plan_version": next_version,
                "review_mode": "contract",
                "reviewed_by": "manager",
            },
            dedupe_key=f"plan_review_passed:{next_version}",
        )
        summary = deepcopy(dict(plan_payload.get("summary") or {}))
        summary.setdefault("evidence_count", len(bundle.evidence))
        summary["agent_ids"] = sorted({str(task.get("agent_id")) for task in tasks})
        summary["wave_count"] = len(task_waves(tasks))
        summary["deliverables"] = sorted(
            {
                str(output)
                for task in tasks
                for output in task.get("produces_outputs") or []
                if str(output).strip()
            }
        )
        agents = summary.get("agents") if isinstance(summary.get("agents"), list) else []
        if "agent-qc" in summary["agent_ids"] and not any(
            isinstance(agent, Mapping) and agent.get("agent_id") == "agent-qc"
            for agent in agents
        ):
            summary["agents"] = [
                *agents,
                {"agent_id": "agent-qc", "name": "质量审计员", "reason": "独立质量门"},
            ]
        return await self._runs.freeze_plan(
            run,
            content=content,
            tasks=tasks,
            known_agent_ids=known_agent_ids,
            summary=summary,
        )

    @staticmethod
    def ensure_independent_qc_task(
        tasks: list[dict[str, Any]], known_agent_ids: set[str]
    ) -> list[dict[str, Any]]:
        """Append one plan-bound QC gate after all non-QC outputs are available.

        The task is deliberately materialized before the Markdown/hash are frozen: it
        cannot be added after approval, and its absence is an explicit, visible
        downgrade only when the configured quality auditor is unavailable.
        """
        if not tasks or "agent-qc" not in known_agent_ids:
            return tasks
        if any(str(task.get("agent_id") or "") == "agent-qc" for task in tasks):
            return tasks
        task_ids = [str(task.get("task_id") or "") for task in tasks if task.get("task_id")]
        outputs = [
            str(output)
            for task in tasks
            for output in task.get("produces_outputs") or []
            if str(output).strip()
        ]
        tasks.append(
            {
                "task_id": "independent-qc",
                "agent_id": "agent-qc",
                "task": (
                    "独立核验所有已回流产物、证据链、完成判据与限制；逐项说明核验依据，"
                    "并在答复末尾严格输出“质量结论：通过”或“质量结论：返工”或“质量结论：人工复核”。"
                ),
                "depends_on": task_ids,
                "accepts_inputs": outputs or ["task-result"],
                "produces_outputs": ["quality-decision", "qc-review", "audit-evidence"],
                "completion_criteria": [
                    "逐项核验已登记产物路径与任务完成判据",
                    "输出可机读的“质量结论：通过|返工|人工复核”质量门结论",
                ],
                "tools": ["workspace_read"],
                "timeout_seconds": 900,
                "retry": {"max_attempts": 1, "backoff_seconds": 0},
                "requires_approval": False,
                "persona_context": "保持独立审计立场，不复述上游 Agent 的未经证实结论。",
            }
        )
        return tasks

    @staticmethod
    async def _maybe_await(value: Awaitable[Any] | Any) -> Any:
        return await value if inspect.isawaitable(value) else value


def task_waves(tasks: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    """Return deterministic dependency waves; validation reports cycles later."""
    unresolved = {
        str(task.get("task_id") or ""): {str(dep) for dep in task.get("depends_on") or []}
        for task in tasks
    }
    waves: list[list[str]] = []
    while unresolved:
        ready = sorted(task_id for task_id, deps in unresolved.items() if not deps)
        if not ready:
            break
        waves.append(ready)
        ready_set = set(ready)
        unresolved = {
            task_id: dependencies - ready_set
            for task_id, dependencies in unresolved.items()
            if task_id not in ready_set
        }
    return waves


def build_plan_markdown(
    *,
    request: str,
    lead_planner_agent_id: str,
    evidence: Sequence[Mapping[str, Any]],
    tasks: Sequence[Mapping[str, Any]],
    plan: Mapping[str, Any],
    next_version: int,
) -> str:
    """Build the mandatory plan document without inventing missing evidence."""

    def bullets(value: Any, empty: str = "- 无") -> str:
        if isinstance(value, str):
            value = [value] if value.strip() else []
        rows = [f"- {item}" for item in (value or []) if str(item).strip()]
        return "\n".join(rows) or empty

    evidence_groups = {source: [] for source in SOURCE_TYPES}
    for item in evidence:
        evidence_groups.setdefault(str(item.get("source_type") or ""), []).append(item)

    def evidence_lines(source: str) -> str:
        rows = []
        for item in evidence_groups.get(source, []):
            locator = str(item.get("locator") or "")
            suffix = f"（{locator}）" if locator else "（模型通用知识；无检索定位）"
            rows.append(f"- [{item.get('evidence_id')}] {item.get('claim') or item.get('title')} {suffix}")
        return "\n".join(rows) or "- 本路没有可用证据；详见 evidence.json 的状态与失败原因。"

    waves = task_waves(tasks)
    wave_lines = "\n".join(
        f"- 波次 {index}: {', '.join(task_ids)}"
        for index, task_ids in enumerate(waves, start=1)
    ) or "- 尚无可执行波次"
    task_blocks = []
    for task in tasks:
        task_blocks.append(
            f"### 任务 `{task.get('task_id', '')}`\n\n"
            f"```json\n{json.dumps(dict(task), ensure_ascii=False, indent=2)}\n```"
        )
    task_markdown = "\n\n".join(task_blocks) or "- 尚无任务"
    return (
        "# 执行计划\n\n"
        f"## 1. 用户目标与最终交付物\n\n{request.strip()}\n\n"
        f"{bullets(plan.get('deliverables'), '- 最终交付物待用户确认')}\n\n"
        f"## 2. 已确认输入\n\n{bullets(plan.get('confirmed_inputs'), '- 暂无已确认输入')}\n\n"
        "## 3. 假设、限制与待确认事项\n\n"
        f"{bullets(plan.get('assumptions'), '- 无额外假设')}\n\n"
        "## 4. 研究与证据摘要\n\n"
        f"### 4.1 平台知识库\n\n{evidence_lines('knowledge_base')}\n\n"
        f"### 4.2 网络资料\n\n{evidence_lines('web')}\n\n"
        "### 4.3 模型通用知识与待验证推断\n\n"
        f"{evidence_lines('model_knowledge')}\n\n"
        "## 5. 主 Agent 串行前置工作\n\n"
        f"{bullets(plan.get('manager_preflight'), '- 核验输入、数据契约与必要 Skill')}\n\n"
        "## 6. Agent 选择与理由\n\n"
        f"- 规划 Agent：`{lead_planner_agent_id}`\n"
        f"{bullets(plan.get('agent_selection_reasons'), '- 执行 Agent 以任务契约为准')}\n\n"
        f"## 7. 执行 DAG 与波次\n\n{wave_lines}\n\n"
        "## 8. 每个任务的输入、输出、工具、超时与重试\n\n"
        f"{task_markdown}\n\n"
        "## 9. 风险、审批点与停止条件\n\n"
        f"{bullets(plan.get('risks'), '- 未识别到额外风险')}\n\n"
        "## 10. 质量门与验收标准\n\n"
        f"{bullets(plan.get('quality_gates'), '- 每个任务满足 completion_criteria')}\n\n"
        f"## 11. 交付目录\n\n{bullets(plan.get('delivery_paths'), '- delivery/')}\n\n"
        "## 12. 计划版本与变更记录\n\n"
        f"- 版本：v{next_version}\n"
        f"{bullets(plan.get('change_log'), '- 初始版本')}\n"
    )
