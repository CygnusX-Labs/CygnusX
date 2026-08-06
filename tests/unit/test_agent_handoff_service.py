"""Agent Handoff 无数据库协议测试。"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from omichub.application.services.agent_handoff_service import (
    MAX_HANDOFF_PACKET_BYTES,
    AgentHandoffService,
    extract_handoff_directive,
)
from omichub.application.services.agent_service import AgentService
from omichub.core.exceptions import BusinessError
from omichub.infrastructure.database.models.agent import AgentTemplateModel
from omichub.infrastructure.database.models.chat import ChatSessionModel


def test_runtime_communication_contract_applies_to_every_standard_agent() -> None:
    agent = AgentTemplateModel(agent_id="agent-custom", name="自定义专家", is_active=True)

    prompt = AgentService._append_communication_contract("原始提示词", agent)

    assert prompt.startswith("原始提示词")
    assert "平台沟通与执行规范" in prompt
    assert "自己在助手列表中猜测" in prompt


def test_router_uses_a_strict_routing_communication_contract() -> None:
    router = AgentTemplateModel(
        agent_id="agent-router", name="星尘 AI", features={"router": True}, is_active=True
    )

    prompt = AgentService._append_communication_contract("路由提示词", router)

    assert "路由输出纪律" in prompt
    assert "不要执行分析" in prompt
    assert "前端规则替你" in prompt


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
    assert (
        extract_handoff_directive(
            {"success": True, "result": {"llm_payload": {"handoff": directive}}}
        )
        == directive
    )


@pytest.mark.asyncio
async def test_prepare_handoff_enforces_agent_whitelist_and_builds_packet() -> None:
    db = AsyncMock()
    source = AgentTemplateModel(
        agent_id="agent-scrna",
        name="单细胞分析师",
        features={"handoff": {"allowed_targets": ["agent-rnaseq"], "max_hops_per_session": 3}},
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


@pytest.mark.asyncio
async def test_prepare_handoff_allows_any_active_non_router_target_for_dynamic_dispatch() -> None:
    db = AsyncMock()
    source = AgentTemplateModel(
        agent_id="agent-general",
        name="通用助手",
        features={"handoff": {"allowed_targets": ["*"], "max_hops_per_session": 3}},
        is_active=True,
    )
    target = AgentTemplateModel(agent_id="agent-viz", name="可视化专家", is_active=True)
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
        source_agent_id="agent-general",
        target_agent_id="agent-viz",
        reason="该任务需要专业科研绘图能力",
        handoff_summary="尚未执行分析。",
        user_intent="画一个样本间相关性热图",
    )

    assert directive["target_agent_id"] == "agent-viz"


@pytest.mark.asyncio
async def test_dynamic_handoff_catalog_includes_current_active_agents_only() -> None:
    db = AsyncMock()
    source = AgentTemplateModel(
        agent_id="agent-general",
        name="通用助手",
        features={"handoff": {"allowed_targets": ["*"]}},
        is_active=True,
    )
    active_expert = AgentTemplateModel(
        agent_id="agent-custom-qc",
        name="质控专家",
        description="自定义质量控制流程",
        category="analysis",
        is_active=True,
    )
    router = AgentTemplateModel(
        agent_id="agent-router",
        name="星尘 AI",
        features={"router": True},
        is_active=True,
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [source, active_expert, router]
    db.execute.return_value = result

    catalog_prompt = await AgentService(db)._build_handoff_catalog(source)
    payload = catalog_prompt.split("\n\n")[1]
    entries = json.loads(payload)

    assert [entry["agent_id"] for entry in entries] == ["agent-custom-qc"]


@pytest.mark.asyncio
async def test_record_handoff_anchor_commits_in_independent_session(monkeypatch) -> None:
    import omichub.application.services.agent_handoff_service as handoff_module

    class FakeDb:
        def __init__(self) -> None:
            self.added: list[object] = []
            self.commit = AsyncMock()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def add(self, value: object) -> None:
            self.added.append(value)

    db = FakeDb()
    monkeypatch.setattr(handoff_module, "get_session_factory", lambda: lambda: db)
    directive = {
        "source_agent_id": "agent-a",
        "target_agent_id": "agent-b",
        "reason": "进入下一专项阶段",
        "handoff_summary": "已完成前序分析。",
        "user_intent": "继续交付结果",
        "artifacts": ["output/qc.html"],
        "constraints": ["GRCh38"],
        "hop_index": 1,
    }

    event = await AgentHandoffService.record_handoff_anchor(
        user_id="user-1", session_id="session-1", directive=directive
    )

    assert event.session_id == "session-1"
    assert event.target_agent_id == "agent-b"
    assert db.added == [event]
    db.commit.assert_awaited_once()
