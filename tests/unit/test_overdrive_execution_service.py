from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from omichub.application.services.overdrive_execution_service import (
    DeliveryAssembler,
    ManagerReviewService,
    OverdrivePreflightService,
    approved_queued_instances,
    deterministic_nickname,
    mark_artifacts_process_on_termination,
    persona_snapshot,
    ready_tasks,
    requeue_repair_instances,
)
from omichub.application.services.overdrive_run_service import OverdriveRunService
from omichub.core.exceptions import ValidationError


def make_run(tasks):
    return SimpleNamespace(
        run_id="overdrive:test",
        session_id="session-1",
        tasks=tasks,
        plan={"version_path": "output/plan.v1.md"},
        artifact_index=[],
    )


def test_ready_tasks_unlock_per_dependency_without_wave_barrier() -> None:
    run = make_run(
        [
            {"task_id": "fast", "status": "succeeded", "depends_on": []},
            {"task_id": "slow", "status": "running", "depends_on": []},
            {"task_id": "downstream", "status": "pending", "depends_on": ["fast"]},
            {"task_id": "blocked", "status": "pending", "depends_on": ["slow"]},
        ]
    )

    assert [task["task_id"] for task in ready_tasks(run)] == ["downstream"]


def test_persona_snapshot_never_copies_permissions_or_tools() -> None:
    snapshot = persona_snapshot(
        {
            "persona": {
                "version": "agent-qc@1",
                "archetype": "审计员",
                "traits": ["审慎"],
                "tools": ["dangerous"],
                "permissions": {"admin": True},
            },
            "tool_packs": ["workspace"],
        }
    )

    assert snapshot == {
        "version": "agent-qc@1",
        "archetype": "审计员",
        "traits": ["审慎"],
    }


def test_nickname_is_stable_and_unique_with_used_set() -> None:
    first = deterministic_nickname("run", "agent-qc", "qc", set())
    assert deterministic_nickname("run", "agent-qc", "qc", set()) == first
    second = deterministic_nickname("run", "agent-qc", "qc", {first})
    assert second != first


def test_rule_review_accepts_only_real_paths_and_completed_criteria() -> None:
    task = {"completion_criteria": ["file_exists", "schema_valid"]}
    accepted = ManagerReviewService().review(
        task,
        {
            "status": "succeeded",
            "artifacts": [{"path": "output/result.tsv"}],
            "self_check": {"file_exists": True, "schema_valid": True},
        },
    )
    escalated = ManagerReviewService().review(
        task,
        {
            "status": "succeeded",
            "artifacts": [{"path": ""}],
            "self_check": {"file_exists": True, "schema_valid": True},
        },
    )

    assert accepted["accepted"] is True
    assert accepted["review_mode"] == "rule"
    assert escalated["accepted"] is False
    assert escalated["review_mode"] == "llm_required"

    missing_file = ManagerReviewService().review(
        task,
        {
            "status": "succeeded",
            "artifacts": [{"path": "output/not-really-there.tsv"}],
            "artifact_paths_valid": False,
            "self_check": {"file_exists": True, "schema_valid": True},
        },
    )
    assert missing_file["accepted"] is False
    assert missing_file["review_mode"] == "llm_required"


def test_rule_review_preserves_branch_local_user_and_approval_waits() -> None:
    service = ManagerReviewService()

    ask = service.review({}, {"status": "awaiting_input", "artifacts": []})
    approval = service.review({}, {"status": "approval_pending", "artifacts": []})

    assert ask["decision"] == "ask_user"
    assert approval["decision"] == "await_approval"
    # 等待态不是失败：basis 不得出现失败措辞
    assert "未成功完成" not in ask["basis"]
    assert "未全部命中" not in ask["basis"]
    assert "未成功完成" not in approval["basis"]
    assert "未全部命中" not in approval["basis"]


def test_independent_qc_adverse_or_missing_conclusion_blocks_delivery() -> None:
    task = {
        "task_id": "independent-qc",
        "completion_criteria": ["audit"],
    }
    failed_gate = ManagerReviewService().review(
        task,
        {
            "status": "succeeded",
            "answer": "已检查全部输出。质量结论：返工",
            "artifacts": [{"path": "output/qc.md"}],
            "self_check": {"audit": True},
        },
    )
    missing_gate = ManagerReviewService().review(
        task,
        {
            "status": "succeeded",
            "answer": "已检查全部输出。",
            "artifacts": [{"path": "output/qc.md"}],
            "self_check": {"audit": True},
        },
    )

    assert failed_gate["decision"] == "quality_gate_failed"
    assert failed_gate["review_mode"] == "rule"
    assert failed_gate["accepted"] is False
    assert missing_gate["review_mode"] == "llm_required"


def test_approved_branch_requeues_the_same_assistant_instance() -> None:
    run = make_run([{
        "task_id": "task-a",
        "status": "queued",
        "depends_on": [],
        "pending_approval": {"status": "approved"},
    }])
    run.assistant_instances = [
        {"assistant_instance_id": "asst:1", "task_id": "task-a", "status": "queued"},
        {"assistant_instance_id": "asst:2", "task_id": "task-a", "status": "awaiting_approval"},
    ]

    instances = approved_queued_instances(run)

    assert [item["assistant_instance_id"] for item in instances] == ["asst:1"]


def test_repair_reuses_original_instance_then_fails_when_budget_is_exhausted() -> None:
    run = make_run([{
        "task_id": "task-a",
        "status": "pending",
        "attempt": 1,
        "repair_feedback": "补充证据链",
        "depends_on": [],
    }])
    run.assistant_instances = [
        {"assistant_instance_id": "asst:original", "task_id": "task-a", "status": "pending"},
    ]

    requeued, exhausted = requeue_repair_instances(run, max_repair_rounds=1)

    assert [item["assistant_instance_id"] for item in requeued] == ["asst:original"]
    assert exhausted == []
    run.tasks[0].update({"status": "pending", "attempt": 2, "repair_feedback": "仍缺证据"})
    run.assistant_instances[0]["status"] = "pending"
    requeued, exhausted = requeue_repair_instances(run, max_repair_rounds=1)
    assert requeued == []
    assert exhausted == ["task-a"]
    assert run.tasks[0]["status"] == "failed"


def test_delivery_excludes_process_and_failed_artifacts() -> None:
    run = make_run([{"task_id": "failed", "status": "failed", "error_summary": "boom"}])
    run.artifact_index = [
        {"path": "output/final.tsv", "status": "validated", "kind": "result", "source": "agent"},
        {"path": "output/debug.log", "status": "failed", "kind": "failed", "source": "agent"},
    ]

    content, official = DeliveryAssembler().assemble(run)

    assert [item["path"] for item in official] == ["output/final.tsv"]
    assert "failed: boom" in content


def test_termination_preserves_prior_files_as_process_artifacts() -> None:
    run = make_run([])
    run.artifact_index = [
        {"path": "output/final.tsv", "kind": "result", "status": "validated"},
        {"path": "output/error.log", "kind": "failed", "status": "failed"},
    ]

    mark_artifacts_process_on_termination(run)

    assert run.artifact_index[0] == {
        "path": "output/final.tsv",
        "kind": "process",
        "status": "process",
        "termination_status": "validated",
    }
    assert run.artifact_index[1]["kind"] == "failed"


def test_preflight_verifies_explicit_workspace_inputs_before_recruitment(monkeypatch, tmp_path) -> None:
    from omichub.application.services import overdrive_execution_service as module

    run_root = tmp_path / "workspace" / "output" / "overdrive" / "session-1" / "run-1"
    (tmp_path / "workspace" / "input").mkdir(parents=True)
    (tmp_path / "workspace" / "input" / "samples.csv").write_text("sample\nS1\n")
    monkeypatch.setattr(module, "overdrive_run_root", lambda *_: run_root)

    class Runs:
        def assert_execution_allowed(self, _run):
            return None

        async def append_event(self, *_args, **_kwargs):
            return None

    run = make_run([
        {
            "task_id": "input-check", "accepts_inputs": ["input/samples.csv"],
            "produces_outputs": ["validated-samples"],
        },
        {
            "task_id": "analysis", "accepts_inputs": ["validated-samples"],
            "produces_outputs": ["analysis-result"],
        },
    ])

    result = asyncio.run(OverdrivePreflightService(Runs()).run(run))

    assert result["status"] == "passed"
    assert any(check.get("path") == "input/samples.csv" and check["status"] == "passed" for check in result["checks"])
    run.tasks[0]["accepts_inputs"] = ["input/missing.csv"]
    with pytest.raises(Exception, match="串行前置检查失败"):
        asyncio.run(OverdrivePreflightService(Runs()).run(run))
    assert run.status == "FAILED"


def test_projected_events_are_session_scoped_and_replay_deduplicable() -> None:
    event = {
        "run_id": "overdrive:test",
        "session_id": "session-1",
        "sequence": 7,
        "event_type": "assistant_result_ready",
        "payload": {
            "assistant_instance_id": "asst:1",
            "task_id": "task-a",
            "result": {"status": "ok", "answer": "已完成"},
        },
    }

    projected = OverdriveRunService.project_event(event)

    assert projected is not None
    assert projected["session_id"] == "session-1"
    assert projected["message_id"] == "overdrive-event-overdrive:test-7"
    assert OverdriveRunService.project_event(event) == projected


def test_control_rejects_unconfirmed_plan_before_any_execution_transition() -> None:
    db = SimpleNamespace(get=AsyncMock(return_value=None), add=lambda _item: None)
    service = OverdriveRunService(db)  # type: ignore[arg-type]
    service.get_for_user = AsyncMock(return_value=SimpleNamespace(  # type: ignore[method-assign]
        status="AWAITING_PLAN_CONFIRMATION", run_id="overdrive:test", control={}, version=0,
    ))

    with pytest.raises(ValidationError, match="计划尚未进入执行阶段"):
        asyncio.run(service.apply_control(
            run_id="overdrive:test", user_id="user-1", command_id="command-1", action="pause",
        ))


def test_control_persists_action_payload_for_execution_run() -> None:
    command_rows = []
    db = SimpleNamespace(get=AsyncMock(return_value=None), add=command_rows.append)
    service = OverdriveRunService(db)  # type: ignore[arg-type]
    run = SimpleNamespace(
        status="RUNNING", run_id="overdrive:test", control={}, version=0,
    )
    service.get_for_user = AsyncMock(return_value=run)  # type: ignore[method-assign]
    service.append_event = AsyncMock()  # type: ignore[method-assign]
    service._write_snapshot = AsyncMock()  # type: ignore[method-assign]

    result = asyncio.run(service.apply_control(
        run_id="overdrive:test", user_id="user-1", command_id="command-1", action="pause",
    ))

    assert result["status"] == "PAUSED"
    assert len(command_rows) == 1
    assert command_rows[0].command_type == "control_pause"
    assert command_rows[0].payload == {"action": "pause"}


def test_projected_manager_review_suppresses_wait_state_speech() -> None:
    base = {
        "run_id": "overdrive:test",
        "session_id": "session-1",
        "sequence": 9,
        "event_type": "manager_review_ready",
    }
    for decision in ("ask_user", "await_approval"):
        event = {**base, "payload": {"decision": decision, "basis": "ignored"}}
        assert OverdriveRunService.project_event(event) is None

    failure = {
        **base,
        "payload": {"decision": "repair_or_review", "basis": "worker 未成功完成"},
    }
    projected = OverdriveRunService.project_event(failure)
    assert projected is not None
    assert projected["type"] == "room_speech"
    assert projected["content"] == "worker 未成功完成"


def test_projected_plan_cancellation_updates_progress_card() -> None:
    event = {
        "run_id": "overdrive:test",
        "session_id": "session-1",
        "sequence": 10,
        "event_type": "run_cancelled",
        "payload": {},
    }

    projected = OverdriveRunService.project_event(event)

    assert projected is not None
    assert projected["type"] == "overdrive_progress"
    assert projected["phase"] == "terminated"
    assert projected["label"] == "用户已取消本轮超频协作，计划不会执行"


def test_projected_worker_approval_keeps_run_and_exact_call_context() -> None:
    event = {
        "run_id": "overdrive:test",
        "session_id": "session-1",
        "sequence": 8,
        "event_type": "assistant_result_ready",
        "payload": {
            "result": {"status": "approval_pending"},
            "approval": {
                "approval_id": "overdrive-v2-approval:overdrive:test:task-a:1",
                "run_id": "overdrive:test",
                "task_id": "task-a",
                "attempt": 1,
                "tool_name": "workspace_write",
                "arguments": {"path": "output/a.txt", "content": "x"},
                "status": "pending",
            },
        },
    }

    projected = OverdriveRunService.project_event(event)

    assert projected == {
        "type": "overdrive_approval_request",
        "run_id": "overdrive:test",
        "session_id": "session-1",
        "sequence": 8,
        "message_id": "overdrive-approval-overdrive:test-8",
        "approval": event["payload"]["approval"],
    }


def test_artifact_index_keeps_official_process_and_failed_entries_separate() -> None:
    run = make_run([])
    run.artifact_index = [
        {"path": "output/final.md", "kind": "delivery", "status": "validated"},
        {"path": "output/evidence.json", "kind": "process", "status": "passed"},
        {"path": "output/failed.log", "kind": "failed", "status": "failed"},
    ]

    _content, official = DeliveryAssembler().assemble(run)

    assert [item["path"] for item in official] == ["output/final.md"]
    assert {item["path"] for item in run.artifact_index if item["kind"] == "process"} == {
        "output/evidence.json"
    }
    assert {item["path"] for item in run.artifact_index if item["status"] == "failed"} == {
        "output/failed.log"
    }


def test_latest_run_lookup_includes_terminal_runs_for_history_recovery() -> None:
    terminal_run = SimpleNamespace(run_id="overdrive:completed", status="COMPLETED")
    result = SimpleNamespace(scalar_one_or_none=lambda: terminal_run)
    db = SimpleNamespace(execute=AsyncMock(return_value=result))

    restored = asyncio.run(
        OverdriveRunService(db).get_latest_for_session("session-1", "user-1")
    )

    assert restored is terminal_run
    statement = db.execute.await_args.args[0]
    rendered = str(statement)
    assert "overdrive_runs.session_id" in rendered
    assert "overdrive_runs.user_id" in rendered
    assert "overdrive_runs.status NOT IN" not in rendered
