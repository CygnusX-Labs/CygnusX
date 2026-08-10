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
    events = CaseRoomProjector().project(
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
    assert events[1]["tasks"] == [{"taskId": "run-1", "agentId": "agent-rnaseq", "status": "running"}]


def test_projects_specialist_roles_to_real_platform_agents() -> None:
    projector = CaseRoomProjector()
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
    projector = CaseRoomProjector()
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
    events = CaseRoomProjector().project(
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
