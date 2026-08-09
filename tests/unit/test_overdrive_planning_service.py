from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from omichub.application.services.overdrive_planning_service import (
    OverdrivePlanningService,
    ResearchBundleService,
    build_plan_markdown,
)
from omichub.application.services.overdrive_run_service import PLAN_SECTIONS, validate_plan
from omichub.core.exceptions import ValidationError


def _task(task_id: str = "analysis", **overrides: object) -> dict[str, object]:
    task: dict[str, object] = {
        "task_id": task_id,
        "agent_id": "agent-rnaseq",
        "depends_on": [],
        "accepts_inputs": ["research-plan"],
        "produces_outputs": ["analysis-report"],
        "completion_criteria": ["report exists", "evidence is cited"],
        "tools": ["workspace_read"],
        "timeout_seconds": 300,
        "retry": {"max_attempts": 2, "backoff_seconds": 5},
        "requires_approval": False,
    }
    task.update(overrides)
    return task


def _plan_content(tasks: list[dict[str, object]] | None = None) -> str:
    return build_plan_markdown(
        request="分析 RNA-seq 数据",
        lead_planner_agent_id="agent-rnaseq",
        evidence=[],
        tasks=tasks or [_task()],
        plan={},
        next_version=1,
    )


@pytest.mark.asyncio
async def test_retrieval_sources_are_concurrent_and_model_runs_after_both() -> None:
    both_started = asyncio.Event()
    started: set[str] = set()
    model_seen: list[dict[str, object]] = []

    async def retrieval(query: str, *, source: str) -> list[dict[str, object]]:
        started.add(source)
        if len(started) == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=0.2)
        return [{"title": source, "url": f"https://example.test/{source}", "claim": query}]

    async def knowledge(query: str, **_: object) -> list[dict[str, object]]:
        return await retrieval(query, source="kb")

    async def web(query: str) -> list[dict[str, object]]:
        return await retrieval(query, source="web")

    async def model(
        query: str,
        *,
        retrieved_evidence: list[dict[str, object]],
        context: dict[str, object],
    ) -> list[dict[str, object]]:
        assert started == {"kb", "web"}
        model_seen.extend(retrieved_evidence)
        return [{"title": "通用知识", "claim": f"候选框架: {query}", "url": "fake://url"}]

    bundle = await ResearchBundleService(
        knowledge_search=knowledge,
        web_search=web,
        model_knowledge=model,
    ).collect("RNA-seq", project_id="project-1")

    assert bundle.statuses == {
        "knowledge_base": "succeeded",
        "web": "succeeded",
        "model_knowledge": "completed",
    }
    assert len(model_seen) == 2
    assert {item["source_type"] for item in bundle.evidence} == {
        "knowledge_base",
        "web",
        "model_knowledge",
    }
    model_item = next(item for item in bundle.evidence if item["source_type"] == "model_knowledge")
    assert model_item["locator"] == ""
    assert model_item["freshness"] == "not_applicable"


@pytest.mark.asyncio
async def test_failed_and_timed_out_sources_are_recorded_without_fabricated_evidence() -> None:
    async def kb(_query: str) -> object:
        raise RuntimeError("knowledge db unavailable")

    async def web(_query: str) -> object:
        await asyncio.sleep(0.1)
        return [{"title": "too late", "url": "https://example.test"}]

    async def model(_query: str, **_: object) -> object:
        return [{"title": "模型候选", "claim": "这只是待验证推断"}]

    bundle = await ResearchBundleService(
        knowledge_search=kb,
        web_search=web,
        model_knowledge=model,
        source_timeout_seconds=0.01,
        wall_timeout_seconds=0.05,
    ).collect("test")

    assert bundle.sources["knowledge_base"]["status"] == "failed"
    assert "unavailable" in bundle.sources["knowledge_base"]["error"]
    assert bundle.sources["web"]["status"] == "timed_out"
    assert bundle.sources["knowledge_base"]["evidence_ids"] == []
    assert bundle.sources["web"]["evidence_ids"] == []
    assert [item["source_type"] for item in bundle.evidence] == ["model_knowledge"]


@pytest.mark.asyncio
async def test_failure_envelope_is_not_treated_as_a_successful_empty_search() -> None:
    async def failed(_query: str) -> dict[str, object]:
        return {"success": False, "error": "provider missing"}

    async def empty(_query: str, **_: object) -> list[object]:
        return []

    bundle = await ResearchBundleService(
        knowledge_search=failed,
        web_search=empty,
        model_knowledge=empty,
    ).collect("test")

    assert bundle.sources["knowledge_base"]["status"] == "failed"
    assert bundle.sources["knowledge_base"]["error"] == "provider missing"


def test_builder_has_every_required_section_and_honest_empty_source_language() -> None:
    content = _plan_content()

    for index, section in enumerate(PLAN_SECTIONS, start=1):
        assert f"## {index}. {section}" in content
    assert "本路没有可用证据；详见 evidence.json 的状态与失败原因" in content
    validate_plan(content, [_task()], {"agent-rnaseq"})


def test_select_lead_planner_uses_smallest_domain_match_and_general_fallback() -> None:
    catalog = [
        {
            "agent_id": "agent-general",
            "features": {"capability_scope": ["研究设计", "跨专家协调"]},
        },
        {
            "agent_id": "agent-rnaseq",
            "features": {"capability_scope": ["差异表达", "通路富集"]},
        },
        {
            "agent_id": "agent-viz",
            "features": {"capability_scope": ["统计图表"]},
        },
    ]

    selected = OverdrivePlanningService.select_lead_planner(
        "请制定 RNA-seq 差异表达研究计划", catalog
    )
    assert selected["lead_planner_agent_id"] == "agent-rnaseq"
    assert selected["advisor_agent_ids"] == []
    assert "差异表达" in selected["matched_capabilities"]

    fallback = OverdrivePlanningService.select_lead_planner("帮我梳理一个新课题", catalog)
    assert fallback["lead_planner_agent_id"] == "agent-general"


def test_independent_qc_is_added_before_plan_freeze_when_available() -> None:
    tasks = OverdrivePlanningService.ensure_independent_qc_task(
        [_task("analysis"), _task("visual", agent_id="agent-viz")],
        {"agent-rnaseq", "agent-viz", "agent-qc"},
    )

    qc_task = tasks[-1]
    assert qc_task["task_id"] == "independent-qc"
    assert qc_task["agent_id"] == "agent-qc"
    assert qc_task["depends_on"] == ["analysis", "visual"]
    validate_plan(_plan_content(tasks), tasks, {"agent-rnaseq", "agent-viz", "agent-qc"})


def test_independent_qc_is_not_fabricated_when_auditor_is_unavailable() -> None:
    tasks = OverdrivePlanningService.ensure_independent_qc_task(
        [_task()], {"agent-rnaseq"}
    )

    assert [task["task_id"] for task in tasks] == ["analysis"]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"depends_on": ["missing"]}, "未知依赖"),
        ({"agent_id": "agent-unknown"}, "未知 Agent"),
        ({"produces_outputs": []}, "produces_outputs"),
        ({"completion_criteria": None}, "completion_criteria"),
        ({"tools": None}, "tools"),
        ({"requires_approval": None}, "requires_approval"),
        ({"timeout_seconds": 0}, "timeout_seconds"),
        ({"retry": {}}, "retry"),
    ],
)
def test_plan_validation_rejects_invalid_task_contracts(
    mutation: dict[str, object], message: str
) -> None:
    task = _task(**mutation)
    with pytest.raises(ValidationError, match=message):
        validate_plan(_plan_content([task]), [task], {"agent-rnaseq"})


def test_plan_validation_rejects_missing_section_and_cycle() -> None:
    content = _plan_content()
    with pytest.raises(ValidationError, match="缺少章节"):
        validate_plan(content.replace("## 10. 质量门与验收标准", "### 质量门"), [_task()], {"agent-rnaseq"})

    tasks = [
        _task("a", depends_on=["b"]),
        _task("b", depends_on=["a"]),
    ]
    with pytest.raises(ValidationError, match="循环依赖"):
        validate_plan(_plan_content(tasks), tasks, {"agent-rnaseq"})


@pytest.mark.asyncio
async def test_planning_service_persists_research_then_freezes_plan() -> None:
    calls: list[object] = []
    run = SimpleNamespace(
        run_id="run-1",
        session_id="session-1",
        root_request="分析 RNA-seq 数据",
        lead_planner_agent_id="agent-rnaseq",
        plan={"version": 0},
    )

    class FakeRunService:
        async def transition(self, _run: object, status: str) -> None:
            calls.append(("transition", status))

        async def save_research(
            self,
            _run: object,
            evidence: list[dict[str, object]],
            statuses: dict[str, str],
            *,
            source_details: dict[str, dict[str, object]],
        ) -> None:
            calls.append(("research", statuses, evidence, source_details))

        async def append_event(self, *args: object, **kwargs: object) -> None:
            calls.append(("event", args[1], args[2]))

        async def write_plan_draft(self, _run: object, content: str) -> dict[str, object]:
            assert "# 执行计划" in content
            calls.append(("write_plan_draft", content))
            return {"version": 1, "path": "output/overdrive/session-1/run-1/plan.md"}

        async def freeze_plan(self, _run: object, **kwargs: object) -> dict[str, object]:
            validate_plan(
                str(kwargs["content"]),
                kwargs["tasks"],  # type: ignore[arg-type]
                kwargs["known_agent_ids"],  # type: ignore[arg-type]
            )
            calls.append(("freeze", kwargs))
            return {"version": 1, "status": "awaiting_confirmation"}

    async def empty(_query: str, **_: object) -> list[object]:
        return []

    task = _task()
    builder = AsyncMock(return_value={"tasks": [task], "deliverables": ["报告"]})
    planner = OverdrivePlanningService(
        FakeRunService(),  # type: ignore[arg-type]
        ResearchBundleService(
            knowledge_search=empty,
            web_search=empty,
            model_knowledge=empty,
        ),
        builder,
    )

    result = await planner.prepare_plan(run, known_agent_ids={"agent-rnaseq"})  # type: ignore[arg-type]

    assert result == {"version": 1, "status": "awaiting_confirmation"}
    assert [call[:2] for call in calls if call[0] == "transition"] == [
        ("transition", "RESEARCHING"),
        ("transition", "PLAN_DRAFTED"),
        ("transition", "PLAN_REVIEWING"),
    ]
    assert next(call for call in calls if call[0] == "write_plan_draft")
    events = [call[1] for call in calls if call[0] == "event"]
    assert events == ["plan_ready", "plan_review_passed"]
    plan_ready = next(call[2] for call in calls if call[:2] == ("event", "plan_ready"))
    assert plan_ready["plan_path"] == "output/overdrive/session-1/run-1/plan.md"
    frozen = next(call[1] for call in calls if call[0] == "freeze")
    assert frozen["tasks"] == [task]
    assert frozen["summary"]["wave_count"] == 1


@pytest.mark.asyncio
async def test_save_research_keeps_failure_details_in_evidence_ledger(monkeypatch, tmp_path) -> None:
    from omichub.application.services.overdrive_run_service import OverdriveRunService

    monkeypatch.setattr(
        "omichub.application.services.overdrive_run_service.overdrive_run_root",
        lambda _session_id, _run_id: tmp_path,
    )
    service = OverdriveRunService(AsyncMock())
    service.append_event = AsyncMock()  # type: ignore[method-assign]
    service._write_snapshot = AsyncMock()  # type: ignore[method-assign]
    run = SimpleNamespace(session_id="session-1", run_id="run-1", research={})

    await service.save_research(
        run,  # type: ignore[arg-type]
        [],
        {"knowledge_base": "failed", "web": "timed_out", "model_knowledge": "completed"},
        source_details={
            "knowledge_base": {"status": "failed", "error": "db unavailable", "items": []},
            "web": {"status": "timed_out", "error": "deadline", "items": []},
            "model_knowledge": {"status": "completed", "items": []},
        },
    )

    ledger = json.loads((tmp_path / "evidence.json").read_text(encoding="utf-8"))
    assert ledger["sources"]["knowledge_base"]["error"] == "db unavailable"
    assert run.research["web"]["status"] == "timed_out"
    assert run.research["web"]["error"] == "deadline"
    assert "items" not in run.research["web"]


@pytest.mark.asyncio
async def test_write_plan_draft_makes_plan_ready_path_real(monkeypatch, tmp_path) -> None:
    from omichub.application.services.overdrive_run_service import OverdriveRunService

    monkeypatch.setattr(
        "omichub.application.services.overdrive_run_service.overdrive_run_root",
        lambda _session_id, _run_id: tmp_path,
    )
    service = OverdriveRunService(AsyncMock())
    service._write_snapshot = AsyncMock()  # type: ignore[method-assign]
    run = SimpleNamespace(session_id="session-1", run_id="run-1", plan={"version": 0})

    draft = await service.write_plan_draft(run, "# 执行计划\r\n\r\n草稿   ")  # type: ignore[arg-type]

    assert draft == {
        "path": "output/overdrive/session-1/run-1/plan.md",
        "version": 1,
    }
    assert (tmp_path / "plan.md").read_bytes() == b"# \xe6\x89\xa7\xe8\xa1\x8c\xe8\xae\xa1\xe5\x88\x92\n\n\xe8\x8d\x89\xe7\xa8\xbf\n"
    assert run.plan["status"] == "reviewing"
    assert run.plan["draft_version"] == 1
