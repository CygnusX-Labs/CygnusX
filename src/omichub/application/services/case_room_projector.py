"""把 AgentTeams Case 审计事件投影为超频房间消息。"""

from __future__ import annotations

from typing import Any

from loguru import logger

from omichub.application.services.agentteams_capability_registry import (
    AgentTeamsCapabilityRegistry,
    get_agentteams_capability_registry,
)


class CaseRoomProjector:
    """纯函数式事件适配器；不持有 DB/Bridge 状态，便于单测与重放。"""

    def __init__(self, registry: AgentTeamsCapabilityRegistry | None = None) -> None:
        self._registry = registry or get_agentteams_capability_registry()

    def project(self, event: dict[str, Any], *, session_id: str, flow_id: str = "") -> list[dict[str, Any]]:
        event_type = str(event.get("event_type") or event.get("type") or "")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        case_id = str(event.get("case_id") or payload.get("case_id") or "")
        event_id = str(event.get("event_id") or "")
        actor = str(event.get("actor") or payload.get("actor") or "bioops-manager")
        sender = self._sender(actor, flow_id=flow_id)
        message_id = f"case-room-{case_id}-{event_id}" if event_id else f"case-room-{case_id}-{event_type}"
        result: list[dict[str, Any]] = []

        speech_type = event_type
        if event_type == "case.state_changed" and payload.get("status") in {
            "remediation_pending",
            "delivery_ready",
        }:
            speech_type = str(payload["status"])
        speech = self._speech(speech_type, payload, sender, session_id, message_id, case_id)
        if speech:
            result.append(speech)
        if event_type.startswith("work_item."):
            task_status = {
                "work_item.assigned": "pending",
                "work_item.claimed": "running",
                "work_item.running": "running",
                "work_item.finished": "succeeded",
                "work_item.failed": "failed",
                "work_item.blocked": "failed",
            }.get(event_type, "running")
            result.append(
                {
                    "type": "overdrive_progress",
                    "session_id": session_id,
                    "case_id": case_id,
                    "phase": "worker_running",
                    "label": self._work_item_label(event_type, sender),
                    "completed": 1 if task_status == "succeeded" else 0,
                    "total": 1,
                    "waveMode": "serial",
                    "tasks": [{
                        "taskId": str(payload.get("work_item_id") or event_id),
                        "agentId": sender["agent_id"],
                        "status": task_status,
                    }],
                }
            )
        elif event_type in {"skill.finished", "quality.decision"}:
            task_id = str(payload.get("work_item_id") or event_id)
            artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else []
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
                    "artifacts": [
                        {
                            "path": str(item.get("path") or ""),
                            "kind": str(item.get("kind") or "file"),
                            "status": "ready",
                            "source": "agentteams",
                        }
                        for item in artifacts
                        if isinstance(item, dict) and item.get("path")
                    ],
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
        if actor == "bioops-manager":
            return {"agent_id": "agent-general", "name": "星尘 AI", "avatar": "✨", "color": "#4f8ef7", "role": "manager"}
        labels = self._registry.role_labels()
        sender = labels.get(actor)
        if sender is not None:
            return dict(sender)
        if actor == "workflow-operator":
            flow_agent = self._registry.agent_for_flow(flow_id)
            sender = next((item for item in labels.values() if item["agent_id"] == flow_agent), None)
            if sender is not None:
                return dict(sender)
        mapping = self._registry.role_agent_map()
        if actor not in mapping:
            logger.warning("AgentTeams 未命中角色映射，降级为 agent-general: actor={}", actor)
        return {
            "agent_id": mapping.get(actor, "agent-general"),
            "name": actor or "协作成员",
            "avatar": "💬",
            "color": "#64748b",
            "role": "worker",
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
            "work_item.claimed": f"已认领工作项 {str(payload.get('work_item_id') or '')}，开始执行。",
            "work_item.running": f"工作项 {str(payload.get('work_item_id') or '')} 正在执行。",
            "omic_task.submitted": f"OmicHub 任务 {str(payload.get('omic_task_id') or '')} 已提交，正在等待执行资源。",
            "omic_task.progress": f"任务进度已更新：{str(payload.get('progress') or payload.get('summary') or '处理中')}。",
            "remediation_pending": "失败诊断已完成，修复工作项正在等待执行。",
            "delivery_ready": "质量门已通过，交付文件已经可以核验和下载。",
            "quality.hard_gate": f"硬规则门结论：{str(payload.get('decision') or 'MANUAL_REVIEW')}。{str(payload.get('reason') or '')}",
            "skill.finished": str(payload.get("summary") or "本阶段工作已完成，已提交结果供团队继续处理。"),
            "quality.decision": f"质控结论：{str(payload.get('decision') or '已完成审核')}。{str(payload.get('summary') or '')}",
            "approval.reminder": "Case 已等待审批超过 24 小时，请确认冻结计划；超过 7 天将自动取消。",
            "remediation.requested": f"质控已发起修复请求，由 {str(payload.get('target') or '协作角色')} 处理：{str(payload.get('objective') or '')}",
            "remediation.completed": "修复工作已完成，Case 已重新进入人工审批；批准后将生成新执行版本并再次质控。",
            "omic_task.failed": CaseRoomProjector._failure_message(payload),
            "case.execution_failed": CaseRoomProjector._failure_message(payload),
            "case.cancelled": (
                "Case 因等待审批超过 7 天已自动取消。"
                if payload.get("reason") == "approval_timeout_7d"
                else f"Case 已取消：{str(payload.get('reason') or '未提供原因')}"
            ),
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

    @staticmethod
    def _failure_message(payload: dict[str, Any]) -> str:
        excerpt = str(payload.get("error_excerpt") or "任务未返回可用错误摘要")[:500]
        recommendation = str(
            payload.get("recommendation")
            or "请检查失败日志与输入；确认后可点击重试，系统会复用冻结计划并生成新提交版本。"
        )[:300]
        return f"执行失败：{excerpt}\n建议：{recommendation}"

    @staticmethod
    def _work_item_label(event_type: str, sender: dict[str, str]) -> str:
        return {
            "work_item.assigned": f"{sender['name']} 已收到工作项",
            "work_item.claimed": f"{sender['name']} 已认领工作项",
            "work_item.running": f"{sender['name']} 正在执行工作项",
            "work_item.finished": f"{sender['name']} 已完成工作项",
            "work_item.failed": f"{sender['name']} 的工作项执行失败",
            "work_item.blocked": f"{sender['name']} 的工作项被阻断",
        }.get(event_type, f"{sender['name']} 更新了工作项")


__all__ = ["CaseRoomProjector"]
