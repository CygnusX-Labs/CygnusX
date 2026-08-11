from omichub.application.services.case_room_projector import CaseRoomProjector
from omichub.application.services.chat_service import _fanout_ask_request


def test_fanout_awaiting_input_becomes_ask_request() -> None:
    request = _fanout_ask_request(
        {
            "ui_payload": {"progress": [{"index": 2, "status": "awaiting_input"}]},
            "llm_payload": {
                "results": [
                    {
                        "index": 2,
                        "agent_id": "agent-rnaseq",
                        "task_id": "task-2",
                        "status": "awaiting_input",
                        "packet": {
                            "needs_user_input": True,
                            "questions": [{"question": "请补充分组信息", "options": ["A/B"]}],
                        },
                    }
                ]
            },
        }
    )

    assert request == {
        "questions": [{"question": "请补充分组信息", "options": ["A/B"]}],
        "question": "请补充分组信息",
        "options": ["A/B"],
        "agent_id": "agent-rnaseq",
        "task_id": "task-2",
        "status": "awaiting_input",
    }


def test_projects_worker_assignment_to_speech_and_progress() -> None:
    events = _projector().project(
        {
            "event_id": "event-1",
            "case_id": "case-1",
            "actor": "workflow-operator",
            "event_type": "work_item.assigned",
            "payload": {"work_item_id": "run-1", "objective": "运行 RNA-seq 流程"},
        },
        session_id="session-1",
    )

    assert [event["type"] for event in events] == ["room_speech", "overdrive_progress"]
    assert events[0]["sender"]["agent_id"] == "agent-rnaseq"
    assert events[1]["tasks"] == [
        {"taskId": "run-1", "agentId": "agent-rnaseq", "status": "pending"}
    ]


def test_projects_claimed_progress_and_hard_gate_speech() -> None:
    projector = _projector()
    claimed = projector.project(
        {
            "event_id": "event-claimed",
            "case_id": "case-1",
            "actor": "workflow-operator",
            "event_type": "work_item.claimed",
            "payload": {"work_item_id": "run-1"},
        },
        session_id="session-1",
    )
    hard_gate = projector.project(
        {
            "event_id": "event-gate",
            "case_id": "case-1",
            "actor": "quality-auditor",
            "event_type": "quality.hard_gate",
            "payload": {"decision": "BLOCKED", "reason": "mapping_rate 低于阈值"},
        },
        session_id="session-1",
    )

    assert [event["type"] for event in claimed] == ["room_speech", "overdrive_progress"]
    assert claimed[1]["tasks"][0]["status"] == "running"
    assert "BLOCKED" in hard_gate[0]["content"]


def test_projects_specialist_roles_to_real_platform_agents() -> None:
    projector = _projector()
    expected = {
        "data-steward": "agent-data",
        "quality-auditor": "agent-qc",
        "delivery-reporter": "agent-delivery",
    }

    for actor, agent_id in expected.items():
        events = projector.project(
            {
                "event_id": f"event-{actor}",
                "case_id": "case-1",
                "actor": actor,
                "event_type": "work_item.assigned",
                "payload": {"work_item_id": f"{actor}-01"},
            },
            session_id="session-1",
        )
        assert events[0]["sender"]["agent_id"] == agent_id


def test_projects_approval_and_case_close() -> None:
    projector = _projector()
    approval = projector.project(
        {
            "event_id": "event-2",
            "case_id": "case-1",
            "event_type": "approval.requested",
            "payload": {"approval_id": "approval-1", "action": "submit_task"},
        },
        session_id="session-1",
    )
    closed = projector.project(
        {
            "event_id": "event-3",
            "case_id": "case-1",
            "event_type": "case.closed",
            "payload": {"manifest_uri": "output/manifest.json"},
        },
        session_id="session-1",
    )

    assert approval[-1]["type"] == "overdrive_approval_request"
    assert approval[-1]["approval"]["case_id"] == "case-1"
    assert closed[-1]["type"] == "mode_changed"
    assert closed[-1]["idempotency_key"] == "case-1:event-3:mode_changed:1"


def test_projected_events_carry_stable_publish_dedup_keys() -> None:
    events = _projector().project(
        {
            "event_id": "event-4",
            "case_id": "case-1",
            "actor": "workflow-operator",
            "event_type": "work_item.assigned",
            "payload": {"work_item_id": "run-1"},
        },
        session_id="session-1",
    )

    assert [event["idempotency_key"] for event in events] == [
        "case-1:event-4:room_speech:0",
        "case-1:event-4:overdrive_progress:1",
    ]


def test_projects_execution_failure_with_error_excerpt_and_retry_guidance() -> None:
    events = _projector().project(
        {
            "event_id": "event-failed",
            "case_id": "case-1",
            "actor": "workflow-operator",
            "event_type": "case.execution_failed",
            "payload": {
                "error_excerpt": "Snakemake rule align exited with code 1",
                "recommendation": "检查 FASTQ 输入后按冻结计划重试。",
            },
        },
        session_id="session-1",
    )

    assert len(events) == 1
    assert events[0]["type"] == "room_speech"
    assert "Snakemake rule align exited with code 1" in events[0]["content"]
    assert "按冻结计划重试" in events[0]["content"]


def test_projects_approval_timeout_reminder_and_auto_cancel() -> None:
    reminder = _projector().project(
        {
            "event_id": "event-reminder",
            "case_id": "case-1",
            "actor": "bioops-manager",
            "event_type": "approval.reminder",
            "payload": {"auto_cancel_after_days": 7},
        },
        session_id="session-1",
    )
    cancelled = _projector().project(
        {
            "event_id": "event-cancelled",
            "case_id": "case-1",
            "actor": "bioops-manager",
            "event_type": "case.cancelled",
            "payload": {"reason": "approval_timeout_7d", "automatic": True},
        },
        session_id="session-1",
    )

    assert "超过 24 小时" in reminder[0]["content"]
    assert "超过 7 天已自动取消" in cancelled[0]["content"]


class _Registry:
    def role_agent_map(self):
        return {
            "data-steward": "agent-data",
            "quality-auditor": "agent-qc",
            "delivery-reporter": "agent-delivery",
        }

    def role_labels(self):
        return {
            role: {
                "agent_id": agent_id,
                "name": role,
                "avatar": "💬",
                "color": "#123456",
                "role": "worker",
            }
            for role, agent_id in self.role_agent_map().items()
        } | {
            "agent-rnaseq": {
                "agent_id": "agent-rnaseq",
                "name": "RNA-seq",
                "avatar": "🧬",
                "color": "#123456",
                "role": "worker",
            }
        }

    def agent_for_flow(self, flow_id):
        return "agent-rnaseq"


def _projector():
    return CaseRoomProjector(_Registry())
