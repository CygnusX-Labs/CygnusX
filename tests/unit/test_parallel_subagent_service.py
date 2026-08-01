"""并行子 Agent fan-out 的无网络服务测试。

覆盖：并行成立、失败隔离、防递归工具剥离、超时、工具回环与独占 session、
开关与 spawnable 白名单校验。
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.services import parallel_subagent_service as pss
from omichub.infrastructure.ai_provider.openai_compatible import ChatChunk


# --- 桩件 -----------------------------------------------------------------


def _ctx(agent_id: str, tools: list | None = None, spawnable: bool = True):
    return SimpleNamespace(
        agent=SimpleNamespace(agent_id=agent_id, name=f"{agent_id} 名称"),
        model_config=SimpleNamespace(),
        system_prompt="系统提示",
        tools=tools or [],
        features={"subagents_spawnable": spawnable},
        max_tokens=4096,
    )


class AgentServiceStub:
    """按 agent_id 返回预置上下文；记录是否被顺序调用。"""

    def __init__(self, contexts: dict):
        self._contexts = contexts

    async def assemble_context(self, agent_id: str):
        return self._contexts.get(agent_id)


class FakeSession(AsyncSession):
    """ToolInvocationContext.db 按 isinstance(AsyncSession) 校验，故继承真类；
    不调用 super().__init__，仅作占位桩。"""

    created = 0

    def __init__(self):
        type(self).created += 1

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class FakeSessionCM:
    def __init__(self):
        self.session: FakeSession | None = None

    async def __aenter__(self) -> FakeSession:
        self.session = FakeSession()
        return self.session

    async def __aexit__(self, *exc) -> bool:
        return False


class FakeSessionFactory:
    def __call__(self) -> FakeSessionCM:
        return FakeSessionCM()


class FakeBridge:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, user_id, tool_name, arguments, context=None):
        self.calls.append((tool_name, dict(arguments or {})))
        return {"success": True, "llm_payload": {"echo": arguments}}


_SCHEMA_REGISTRY = {
    "workspace_read": SimpleNamespace(invocation_mode="backend_sync", requires_confirm=False),
    "parallel_subagents": SimpleNamespace(invocation_mode="backend_sync", requires_confirm=False),
    "transfer_to_agent": SimpleNamespace(invocation_mode="backend_sync", requires_confirm=False),
    "long_task": SimpleNamespace(invocation_mode="analysis_flow", requires_confirm=False),
    "danger_tool": SimpleNamespace(invocation_mode="backend_sync", requires_confirm=True),
}


@pytest.fixture
def env(monkeypatch, tmp_path):
    """统一打桩：settings / schema_loader / session factory / bridge。"""
    settings = pss.get_settings()
    monkeypatch.setattr(settings, "subagent_fanout_enabled", True)
    monkeypatch.setattr(settings, "subagent_max_parallel", 4)
    monkeypatch.setattr(settings, "subagent_max_concurrent", 3)
    monkeypatch.setattr(settings, "subagent_child_timeout_seconds", 60)
    monkeypatch.setattr(settings, "subagent_max_rounds_per_child", 6)
    monkeypatch.setattr(settings, "subagent_max_children_per_message", 1)
    monkeypatch.setattr(settings, "storage_path", str(tmp_path))

    monkeypatch.setattr(
        pss, "schema_loader", SimpleNamespace(get_tool=lambda name: _SCHEMA_REGISTRY.get(name))
    )
    bridge = FakeBridge()
    monkeypatch.setattr(
        "omichub.application.services.tool_bridge_service.get_tool_bridge_service",
        lambda: bridge,
    )
    FakeSession.created = 0
    monkeypatch.setattr(pss, "get_session_factory", lambda: FakeSessionFactory())

    # DB 平台设置开关桩：默认关（env 开关在 settings 上单独控制）
    class SiteSettingsServiceStub:
        db_flag = False

        def __init__(self, db):
            pass

        async def is_subagent_fanout_enabled(self) -> bool:
            return type(self).db_flag

    monkeypatch.setattr(
        "omichub.application.services.site_settings_service.SiteSettingsService",
        SiteSettingsServiceStub,
    )
    return SimpleNamespace(
        settings=settings, bridge=bridge, tmp_path=tmp_path, site=SiteSettingsServiceStub
    )


def _patch_provider(monkeypatch, handler):
    """handler(messages, kwargs) 为异步生成器函数，按 messages 首条内容路由子任务行为。"""
    seen: dict[str, object] = {"tools": []}

    async def fake_stream(*, config, messages, system_prompt=None, **kwargs):
        seen["tools"].append(kwargs.get("tools"))
        async for chunk in handler(messages, kwargs):
            yield chunk

    monkeypatch.setattr(pss, "provider_manager", SimpleNamespace(chat_stream=fake_stream))
    return seen


# --- 测试 -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_fanout_parallel_success_and_tool_filtering(env, monkeypatch) -> None:
    contexts = {
        "agent-a": _ctx(
            "agent-a",
            tools=[
                {"function": {"name": "parallel_subagents"}},  # C2 必须被剥离
                {"function": {"name": "transfer_to_agent"}},  # C3 必须被剥离
                {"function": {"name": "danger_tool"}},  # C4 必须被剥离
                {"function": {"name": "long_task"}},  # analysis_flow 必须被剥离
                {"function": {"name": "workspace_read"}},  # 唯一保留
                {"function": {"name": "some_mcp_tool"}},  # 桥外工具必须被剥离
            ],
        ),
        "agent-b": _ctx("agent-b"),
    }
    monkeypatch.setattr(pss, "AgentService", lambda db: AgentServiceStub(contexts))

    async def slow_text(messages, kwargs):
        await asyncio.sleep(0.1)
        first = messages[0]["content"]
        yield ChatChunk(type="text", content=f"结论：{'A' if 'task-a' in first else 'B'}")

    seen = _patch_provider(monkeypatch, slow_text)

    started = time.monotonic()
    result = await pss.ParallelSubAgentService().run(
        user_id="user-1",
        parent_agent_id="agent-general",
        parent_session_id="sess-1",
        context_summary="共享背景",
        tasks=[
            {"agent_id": "agent-a", "task": "task-a 内容"},
            {"agent_id": "agent-b", "task": "task-b 内容"},
        ],
        db=SimpleNamespace(),
    )
    elapsed = time.monotonic() - started

    assert result["success"] is True
    assert result["llm_payload"]["summary"].startswith("2/2 个子任务成功")
    statuses = [item["status"] for item in result["llm_payload"]["results"]]
    assert statuses == ["ok", "ok"]
    # 并行成立：两个各睡 0.1s 的子任务总墙钟应明显小于串行 0.2s
    assert elapsed < 0.19, f"fan-out 未并行执行，elapsed={elapsed:.3f}s"
    # 防递归/控制工具剥离：任何子循环都见不到被禁工具；agent-a 只保留 workspace_read
    forbidden = {
        "parallel_subagents",
        "transfer_to_agent",
        "danger_tool",
        "long_task",
        "some_mcp_tool",
    }
    name_sets = [
        {(t.get("function") or {}).get("name") for t in (tools or [])}
        for tools in seen["tools"]
    ]
    assert all(names.isdisjoint(forbidden) for names in name_sets)
    assert {"workspace_read"} in name_sets


@pytest.mark.asyncio
async def test_fanout_isolates_child_failure(env, monkeypatch) -> None:
    contexts = {"agent-a": _ctx("agent-a"), "agent-b": _ctx("agent-b")}
    monkeypatch.setattr(pss, "AgentService", lambda db: AgentServiceStub(contexts))

    async def handler(messages, kwargs):
        if "task-a" in messages[0]["content"]:
            yield ChatChunk(type="text", content="A 正常完成")
        else:
            raise RuntimeError("模型端点故障")

    _patch_provider(monkeypatch, handler)

    result = await pss.ParallelSubAgentService().run(
        user_id="user-1",
        parent_agent_id="agent-general",
        parent_session_id="sess-1",
        context_summary="",
        tasks=[
            {"agent_id": "agent-a", "task": "task-a"},
            {"agent_id": "agent-b", "task": "task-b"},
        ],
        db=SimpleNamespace(),
    )

    assert result["success"] is True  # 部分成功仍视为可用汇总
    assert result["llm_payload"]["summary"].startswith("1/2 个子任务成功")
    by_agent = {item["agent_id"]: item for item in result["llm_payload"]["results"]}
    assert by_agent["agent-a"]["status"] == "ok"
    assert by_agent["agent-b"]["status"] == "failed"
    assert "模型端点故障" in by_agent["agent-b"]["error"]


@pytest.mark.asyncio
async def test_fanout_disabled_flag(env, monkeypatch) -> None:
    env.settings.subagent_fanout_enabled = False
    result = await pss.ParallelSubAgentService().run(
        user_id="user-1",
        parent_agent_id="agent-general",
        parent_session_id="sess-1",
        context_summary="",
        tasks=[
            {"agent_id": "agent-a", "task": "x"},
            {"agent_id": "agent-b", "task": "y"},
        ],
        db=SimpleNamespace(),
    )
    assert result["success"] is False
    assert "未启用" in result["llm_payload"]["error"]


@pytest.mark.asyncio
async def test_fanout_enabled_by_db_flag_alone(env, monkeypatch) -> None:
    """env 关、管理端平台设置开 → 仍可 fan-out（运行时主开关语义）。"""
    env.settings.subagent_fanout_enabled = False
    env.site.db_flag = True
    contexts = {"agent-a": _ctx("agent-a"), "agent-b": _ctx("agent-b")}
    monkeypatch.setattr(pss, "AgentService", lambda db: AgentServiceStub(contexts))

    async def text(messages, kwargs):
        yield ChatChunk(type="text", content="完成")

    _patch_provider(monkeypatch, text)
    result = await pss.ParallelSubAgentService().run(
        user_id="user-1",
        parent_agent_id="agent-general",
        parent_session_id="sess-1",
        context_summary="",
        tasks=[
            {"agent_id": "agent-a", "task": "x"},
            {"agent_id": "agent-b", "task": "y"},
        ],
        db=SimpleNamespace(),
    )
    assert result["success"] is True
    assert result["llm_payload"]["summary"].startswith("2/2")


@pytest.mark.asyncio
async def test_fanout_rejects_non_spawnable(env, monkeypatch) -> None:
    contexts = {
        "agent-a": _ctx("agent-a", spawnable=False),
        "agent-b": _ctx("agent-b"),
    }
    monkeypatch.setattr(pss, "AgentService", lambda db: AgentServiceStub(contexts))
    result = await pss.ParallelSubAgentService().run(
        user_id="user-1",
        parent_agent_id="agent-general",
        parent_session_id="sess-1",
        context_summary="",
        tasks=[
            {"agent_id": "agent-a", "task": "x"},
            {"agent_id": "agent-b", "task": "y"},
        ],
        db=SimpleNamespace(),
    )
    assert result["success"] is False
    assert "subagents_spawnable" in result["llm_payload"]["error"]


@pytest.mark.asyncio
async def test_fanout_child_timeout(env, monkeypatch) -> None:
    env.settings.subagent_child_timeout_seconds = 1
    contexts = {"agent-a": _ctx("agent-a"), "agent-b": _ctx("agent-b")}
    monkeypatch.setattr(pss, "AgentService", lambda db: AgentServiceStub(contexts))

    async def hang(messages, kwargs):
        await asyncio.sleep(5)
        yield ChatChunk(type="text", content="不该出现")

    _patch_provider(monkeypatch, hang)
    started = time.monotonic()
    result = await pss.ParallelSubAgentService().run(
        user_id="user-1",
        parent_agent_id="agent-general",
        parent_session_id="sess-1",
        context_summary="",
        tasks=[
            {"agent_id": "agent-a", "task": "x"},
            {"agent_id": "agent-b", "task": "y"},
        ],
        db=SimpleNamespace(),
    )
    elapsed = time.monotonic() - started
    assert result["success"] is False
    assert {item["status"] for item in result["llm_payload"]["results"]} == {"timeout"}
    assert elapsed < 4, f"超时未生效，elapsed={elapsed:.3f}s"


@pytest.mark.asyncio
async def test_fanout_child_tool_roundtrip_with_dedicated_session(env, monkeypatch) -> None:
    contexts = {
        "agent-a": _ctx("agent-a", tools=[{"function": {"name": "workspace_read"}}]),
        "agent-b": _ctx("agent-b"),
    }
    monkeypatch.setattr(pss, "AgentService", lambda db: AgentServiceStub(contexts))

    call_counts: dict[str, int] = {}

    async def handler(messages, kwargs):
        first = messages[0]["content"]
        key = "a" if "task-a" in first else "b"
        call_counts[key] = call_counts.get(key, 0) + 1
        if key == "a" and call_counts[key] == 1:
            yield ChatChunk(
                type="tool_calls",
                metadata={
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "workspace_read",
                                "arguments": '{"path": "x.txt"}',
                            },
                        }
                    ]
                },
            )
        else:
            yield ChatChunk(type="text", content=f"{key} 完成")

    _patch_provider(monkeypatch, handler)

    result = await pss.ParallelSubAgentService().run(
        user_id="user-1",
        parent_agent_id="agent-general",
        parent_session_id="sess-1",
        context_summary="",
        tasks=[
            {"agent_id": "agent-a", "task": "task-a"},
            {"agent_id": "agent-b", "task": "task-b"},
        ],
        db=SimpleNamespace(),
    )

    assert result["success"] is True
    assert env.bridge.calls == [("workspace_read", {"path": "x.txt"})]
    # C1：子任务工具执行创建了独占 session
    assert FakeSession.created >= 1


@pytest.mark.asyncio
async def test_fanout_validation_rules(env, monkeypatch) -> None:
    service = pss.ParallelSubAgentService()
    kwargs = dict(
        user_id="user-1",
        parent_agent_id="agent-general",
        parent_session_id="sess-1",
        context_summary="",
        db=SimpleNamespace(),
    )
    single = await service.run(tasks=[{"agent_id": "a", "task": "x"}], **kwargs)
    assert single["success"] is False and "至少需要 2 个" in single["llm_payload"]["error"]

    too_many = await service.run(
        tasks=[{"agent_id": "a", "task": f"t{i}"} for i in range(5)], **kwargs
    )
    assert too_many["success"] is False and "最多" in too_many["llm_payload"]["error"]

    missing = await service.run(
        tasks=[{"agent_id": "a", "task": "x"}, {"agent_id": "", "task": "y"}], **kwargs
    )
    assert missing["success"] is False and "缺少" in missing["llm_payload"]["error"]
