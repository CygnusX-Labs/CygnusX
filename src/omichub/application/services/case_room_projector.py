"""把 AgentTeams Case 审计事件投影为超频房间消息。"""

from __future__ import annotations

from typing import Any

from loguru import logger

ROLE_AGENT_MAP = {
    # Keep in sync with integrations/agentteams/bridge/.../config.py ROLE_AGENT_MAP.
    "data-steward": "agent-data",
    "workflow-operator": "agent-rnaseq",
    "quality-auditor": "agent-qc",
    "delivery-reporter": "agent-delivery",
    "agent-code": "agent-code",
    "agent-viz": "agent-viz",
    "agent-scrna": "agent-scrna",
    "agent-rnaseq": "agent-rnaseq",
}

ROLE_LABELS = {
    "bioops-manager": ("星尘 AI", "✨", "#4f8ef7", "manager"),
    "data-steward": ("数据管家", "🧾", "#0ea5a4", "worker"),
    "workflow-operator": ("流程执行员", "⚙️", "#7c3aed", "worker"),
    "quality-auditor": ("质控审计员", "🔎", "#d97706", "worker"),
    "delivery-reporter": ("交付报告员", "📦", "#2563eb", "worker"),
}


class CaseRoomProjector:
    """纯函数式事件适配器；不持有 DB/Bridge 状态，便于单测与重放。"""

    def project(self, event: dict[str, Any], *, session_id: str, flow_id: str = "") -> list[dict[str, Any]]:
        event_type = str(event.get("event_type") or event.get("type") or "")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        case_id = str(event.get("case_id") or payload.get("case_id") or "")
        event_id = str(event.get("event_id") or "")
        actor = str(event.get("actor") or payload.get("actor") or "bioops-manager")
        sender = self._sender(actor, flow_id=flow_id)
        message_id = f"case-room-{case_id}-{event_id}" if event_id else f"case-room-{case_id}-{event_type}"
        result: list[dict[str, Any]] = []

        speech = self._speech(event_type, payload, sender, session_id, message_id, case_id)
        if speech:
            result.append(speech)
        if event_type == "work_item.assigned":
            result.append(
                {
                    "type": "overdrive_progress",
                    "session_id": session_id,
                    "case_id": case_id,
                    "phase": "worker_running",
                    "label": f"{sender['name']} 已领取工作项",
                    "completed": 0,
                    "total": 1,
                    "waveMode": "serial",
                    "tasks": [{
                        "taskId": str(payload.get("work_item_id") or event_id),
                        "agentId": sender["agent_id"],
                        "status": "running",
                    }],
                }
            )
        elif event_type in {"skill.finished", "quality.decision"}:
            task_id = str(payload.get("work_item_id") or event_id)
            result.append(
                {
                    "type": "overdrive_progress",
                    "session_id": session_id,
                    "case_id": case_id,
                    "phase": "worker_finished" if event_type == "skill.finished" else "peer_reviewing",
                    "label": "Case 质控中" if event_type == "skill.finished" else "Case 质控已完成",
                    "completed": 1,
                    "total": 1,
                    "waveMode": "serial",
                    "tasks": [{"taskId": task_id, "agentId": sender["agent_id"], "status": "succeeded"}],
                }
            )
        elif event_type in {"approval.requested", "approval_pending"} or (
            event_type == "case.state_changed" and payload.get("status") == "approval_pending"
        ):
            result.append(
                {
                    "type": "overdrive_approval_request",
                    "session_id": session_id,
                    "case_id": case_id,
                    "approval": {
                        "approval_id": str(payload.get("approval_id") or event_id),
                        "tool_name": str(payload.get("action") or "submit_task"),
                        "arguments": payload,
                        "status": "pending",
                        "reason": str(payload.get("reason") or "AgentTeams Case 需要你的审批"),
                        "case_id": case_id,
                    },
                    "agentId": sender["agent_id"],
                }
            )
        elif event_type == "case.closed":
            result.append({"type": "mode_changed", "mode": "overdrive", "session_id": session_id, "enabled": False})
        if event_id:
            for index, projected in enumerate(result):
                projected["event_id"] = event_id
                projected["idempotency_key"] = f"{case_id}:{event_id}:{projected['type']}:{index}"
        return result

    def _sender(self, actor: str, *, flow_id: str) -> dict[str, str]:
        name, avatar, color, role = ROLE_LABELS.get(actor, (actor or "协作成员", "💬", "#64748b", "worker"))
        if actor not in ROLE_AGENT_MAP:
            logger.warning("AgentTeams 未命中角色映射，降级为 agent-general: actor={}", actor)
        return {
            "agent_id": ROLE_AGENT_MAP.get(actor, actor or "agent-general"),
            "name": name,
            "avatar": avatar,
            "color": color,
            "role": role,
        }

    @staticmethod
    def _speech(
        event_type: str,
        payload: dict[str, Any],
        sender: dict[str, str],
        session_id: str,
        message_id: str,
        case_id: str,
    ) -> dict[str, Any] | None:
        labels = {
            "case.created": f"已确认协作 Case「{str(payload.get('intent') or '正式分析任务')[:80]}」，开始分派团队工作。",
            "work_item.assigned": f"我已领取工作项：{str(payload.get('objective') or payload.get('skill_name') or '开始处理')[:180]}。",
            "skill.finished": str(payload.get("summary") or "本阶段工作已完成，已提交结果供团队继续处理。"),
            "quality.decision": f"质控结论：{str(payload.get('decision') or '已完成审核')}。{str(payload.get('summary') or '')}",
            "case.closed": f"Case 已关闭，交付清单已生成：{str(payload.get('manifest_uri') or '')}".rstrip("："),
        }
        content = labels.get(event_type)
        if not content:
            return None
        return {
            "type": "room_speech",
            "content": content,
            "sender": sender,
            "round": 0,
            "session_id": session_id,
            "message_id": message_id,
            "case_id": case_id,
        }


__all__ = ["CaseRoomProjector", "ROLE_AGENT_MAP"]
