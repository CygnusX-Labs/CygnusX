"""Agent Handoff 无数据库协议测试。"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from omichub.application.services.agent_handoff_service import (
    MAX_HANDOFF_PACKET_BYTES,
    AgentHandoffService,
    extract_handoff_directive,
)
from omichub.core.exceptions import BusinessError
from omichub.infrastructure.database.models.agent import AgentTemplateModel
from omichub.infrastructure.database.models.chat import ChatSessionModel


def test_handoff_packet_stays_within_budget() -> None:
    packet = AgentHandoffService._build_packet(
        source_name="单细胞分析师",
        reason="质控完成，需要差异表达与富集分析",
        user_intent="完成差异表达与富集",
        handoff_summary="已完成过滤和双细胞处理。" * 300,
        artifacts=["workspace/qc/report.html"],
        constraints=["使用 GRCh38"],
    )

    assert len(packet.encode("utf-8")) <= MAX_HANDOFF_PACKET_BYTES
    assert packet.startswith("## 会话交接")


def test_handoff_artifacts_must_stay_in_relative_workspace_paths() -> None:
    with pytest.raises(BusinessError, match="相对路径"):
        AgentHandoffService._normalize_artifacts(["../other-user/report.html"])


def test_handoff_directive_is_extracted_from_toolbridge_envelope() -> None:
    directive = {"target_agent_id": "agent-rnaseq"}
    assert extract_handoff_directive(
        {"success": True, "result": {"llm_payload": {"handoff": directive}}}
    ) == directive


@pytest.mark.asyncio
async def test_prepare_handoff_enforces_agent_whitelist_and_builds_packet() -> None:
    db = AsyncMock()
    source = AgentTemplateModel(
        agent_id="agent-scrna",
        name="单细胞分析师",
        features={
            "handoff": {"allowed_targets": ["agent-rnaseq"], "max_hops_per_session": 3}
        },
        is_active=True,
    )
    target = AgentTemplateModel(agent_id="agent-rnaseq", name="RNA-seq 分析师", is_active=True)
    db.scalar.side_effect = [
        ChatSessionModel(session_id="session-1", user_id="user-1", status="active"),
        source,
        target,
    ]
    history_result = MagicMock()
    history_result.all.return_value = []
    db.scalars.return_value = history_result

    directive = await AgentHandoffService(db).prepare_handoff(
        user_id="user-1",
        session_id="session-1",
        source_agent_id="agent-scrna",
        target_agent_id="agent-rnaseq",
        reason="质控已完成，进入差异表达阶段",
        handoff_summary="完成过滤、双细胞检测和细胞注释。",
        user_intent="继续做差异表达与富集",
        artifacts=["workspace/qc/report.html"],
        constraints=["使用 GRCh38"],
    )

    assert directive["hop_index"] == 1
    assert directive["target_agent_name"] == "RNA-seq 分析师"
    assert "workspace/qc/report.html" in directive["packet"]
