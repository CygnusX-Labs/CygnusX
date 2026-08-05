"""超频模式第一期的编排与容错契约测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import omichub.application.services.chat_service as chat_module
from omichub.application.services.chat_service import (
    ChatService,
    _effective_overdrive,
    _extract_route_json,
    _resolve_overdrive_keyword_toggle,
)
from omichub.infrastructure.ai_provider.openai_compatible import ChatChunk


class _FakeAgentService:
    agents: list[object] = []

    def __init__(self, _db) -> None:
        pass

    async def list_agents(self, *, active_only: bool = False):
        assert active_only
        return self.agents


def _agent(agent_id: str, name: str) -> object:
    return SimpleNamespace(
        agent_id=agent_id,
        name=name,
        avatar="🧬",
        color="#2a8",
        description=f"{name} 专家",
        category="analysis",
        features={},
    )


def _manager_ctx() -> object:
    return SimpleNamespace(
        agent=_agent("manager", "Manager"),
        model_config=SimpleNamespace(name="test-model"),
    )


@pytest.mark.parametrize(
    ("raw", "expected_ids"),
    [
        ('{"speech":"分工","assignments":[]}', []),
        ('思考\n{"speech":"分工","assignments":[{"agent_id":"a","task":"A"},{"agent_id":"b","task":"B"}]}', ["a", "b"]),
        ("纯文本", []),
        ('{"speech":"分工","assignments":[{"agent_id":"a","task":"A"}]}', ["a"]),
    ],
)
def test_extract_overdrive_manager_json_shapes(raw: str, expected_ids: list[str]) -> None:
    parsed = _extract_route_json(raw)
    if expected_ids:
        assert parsed is not None
        assert [item["agent_id"] for item in parsed["assignments"]] == expected_ids
    elif raw == "纯文本":
        assert parsed is None
    else:
        assert parsed == {"speech": "分工", "assignments": []}


@pytest.mark.parametrize(
    ("text", "enabled", "expected"),
    [
        ("请进入超频模式", False, True),
        ("OVERDRIVE", False, True),
        ("退出超频模式", True, False),
        ("关闭超频后继续", True, False),
        ("别进超频模式，正常回答", False, None),
        ("已经在超频模式", True, None),
    ],
)
def test_overdrive_keyword_toggle_priority(text: str, enabled: bool, expected: bool | None) -> None:
    assert _resolve_overdrive_keyword_toggle(text, enabled) is expected


@pytest.mark.parametrize(
    ("request_value", "stored_value", "expected"),
    [
        (True, False, True),
        (False, True, False),
        (None, True, True),
        (None, False, False),
    ],
)
def test_overdrive_request_value_has_priority(
    request_value: bool | None, stored_value: bool, expected: bool
) -> None:
    assert _effective_overdrive(request_value, {"overdrive": stored_value}) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize("assignment_count", [0, 2, 5])
async def test_overdrive_room_speech_sequence_and_persistence(monkeypatch, assignment_count: int) -> None:
    candidates = [_agent(f"agent-{index}", f"专家{index}") for index in range(5)]
    _FakeAgentService.agents = candidates
    monkeypatch.setattr("omichub.application.services.agent_service.AgentService", _FakeAgentService)

    manager_response = {
        "speech": "我先拆分任务。",
        "assignments": [
            {"agent_id": f"agent-{index}", "task": f"子任务 {index}"}
            for index in range(assignment_count)
        ],
    }
    llm_outputs = [str(manager_response).replace("'", '"')]
    if assignment_count:
        llm_outputs.append("汇总结论")

    async def fake_stream(**_kwargs):
        yield ChatChunk(type="text", content=llm_outputs.pop(0))

    monkeypatch.setattr(chat_module.provider_manager, "chat_stream", fake_stream)

    fanout_calls: list[list[dict[str, str]]] = []

    async def fake_fanout(self, *, tasks, **_kwargs):
        fanout_calls.append(tasks)
        return {
            "success": True,
            "llm_payload": {
                "results": [
                    {"index": position, "agent_id": task["agent_id"], "status": "ok", "answer": f"{task['agent_id']} 结论"}
                    for position, task in enumerate(tasks, start=1)
                ]
            },
        }

    monkeypatch.setattr(
        "omichub.application.services.parallel_subagent_tool_service.ParallelSubAgentToolService.run_parallel_subagents",
        fake_fanout,
    )

    service = ChatService(MagicMock(spec=AsyncSession))
    persisted: list[dict] = []

    async def fake_add_message(_session, _role, content, **kwargs):
        persisted.append({"content": content, **kwargs})
        return SimpleNamespace(message_id=f"message-{len(persisted)}")

    service.add_message = fake_add_message  # type: ignore[method-assign]
    chunks = [
        chunk
        async for chunk in service._run_overdrive_turn(
            user_id="user-1",
            session_id="session-1",
            user_content="请协作分析",
            manager_ctx=_manager_ctx(),
        )
    ]

    assert [chunk.type for chunk in chunks] == ["room_speech"] * (1 if not assignment_count else assignment_count + 2)
    assert chunks[0].metadata["sender"]["role"] == "manager"
    assert all(
        item["metadata"]["senderAgent"] == chunk.metadata["sender"]
        for item, chunk in zip(persisted, chunks, strict=True)
    )
    if assignment_count:
        assert len(fanout_calls) == 1
        assert [chunk.metadata["sender"]["role"] for chunk in chunks] == ["manager"] + ["worker"] * assignment_count + ["manager"]
    else:
        assert fanout_calls == []


@pytest.mark.asyncio
async def test_overdrive_worker_failure_becomes_room_speech(monkeypatch) -> None:
    _FakeAgentService.agents = [_agent("agent-1", "专家1"), _agent("agent-2", "专家2")]
    monkeypatch.setattr("omichub.application.services.agent_service.AgentService", _FakeAgentService)

    responses = iter([
        '{"speech":"开始分工","assignments":[{"agent_id":"agent-1","task":"A"},{"agent_id":"agent-2","task":"B"}]}',
        "最终汇总",
    ])

    async def fake_stream(**_kwargs):
        yield ChatChunk(type="text", content=next(responses))

    async def fake_fanout(self, **_kwargs):
        return {"success": True, "llm_payload": {"results": [
            {"index": 1, "agent_id": "agent-1", "status": "failed", "error": "模型不可用"},
            {"index": 2, "agent_id": "agent-2", "status": "ok", "answer": "正常结论"},
        ]}}

    monkeypatch.setattr(chat_module.provider_manager, "chat_stream", fake_stream)
    monkeypatch.setattr(
        "omichub.application.services.parallel_subagent_tool_service.ParallelSubAgentToolService.run_parallel_subagents",
        fake_fanout,
    )

    service = ChatService(MagicMock(spec=AsyncSession))

    async def fake_add_message(_session, _role, _content, **_kwargs):
        return SimpleNamespace(message_id="message")

    service.add_message = fake_add_message  # type: ignore[method-assign]
    chunks = [chunk async for chunk in service._run_overdrive_turn(
        user_id="user", session_id="session", user_content="协作", manager_ctx=_manager_ctx(),
    )]

    assert "子任务执行失败：模型不可用" in chunks[1].content
    assert chunks[1].metadata["sender"]["role"] == "worker"


@pytest.mark.asyncio
async def test_overdrive_same_agent_clones_run_independent_tasks(monkeypatch) -> None:
    """同一专家可被指派多个独立子任务（分身并行）：结果按下标对齐，身份以 #n 区分。"""
    _FakeAgentService.agents = [_agent("agent-1", "专家1")]
    monkeypatch.setattr("omichub.application.services.agent_service.AgentService", _FakeAgentService)

    responses = iter([
        '{"speech":"拆成两个分身","assignments":[{"agent_id":"agent-1","task":"任务A"},{"agent_id":"agent-1","task":"任务B"}]}',
        "最终汇总",
    ])

    async def fake_stream(**_kwargs):
        yield ChatChunk(type="text", content=next(responses))

    async def fake_fanout(self, *, tasks, **_kwargs):
        assert [task["agent_id"] for task in tasks] == ["agent-1", "agent-1"]
        return {"success": True, "llm_payload": {"results": [
            {"index": 1, "agent_id": "agent-1", "status": "ok", "answer": "A 结论"},
            {"index": 2, "agent_id": "agent-1", "status": "ok", "answer": "B 结论"},
        ]}}

    monkeypatch.setattr(chat_module.provider_manager, "chat_stream", fake_stream)
    monkeypatch.setattr(
        "omichub.application.services.parallel_subagent_tool_service.ParallelSubAgentToolService.run_parallel_subagents",
        fake_fanout,
    )

    service = ChatService(MagicMock(spec=AsyncSession))

    async def fake_add_message(_session, _role, _content, **_kwargs):
        return SimpleNamespace(message_id="message")

    service.add_message = fake_add_message  # type: ignore[method-assign]
    chunks = [chunk async for chunk in service._run_overdrive_turn(
        user_id="user", session_id="session", user_content="协作", manager_ctx=_manager_ctx(),
    )]

    assert [chunk.metadata["sender"]["role"] for chunk in chunks] == ["manager", "worker", "worker", "manager"]
    assert chunks[1].metadata["sender"]["name"] == "专家1 #1"
    assert chunks[1].content == "A 结论"
    assert chunks[2].metadata["sender"]["name"] == "专家1 #2"
    assert chunks[2].content == "B 结论"


@pytest.mark.asyncio
async def test_overdrive_gateway_unreachable_degrades_to_internal_room(monkeypatch) -> None:
    _FakeAgentService.agents = [_agent("agent-1", "专家1")]
    monkeypatch.setattr("omichub.application.services.agent_service.AgentService", _FakeAgentService)

    async def fake_stream(**_kwargs):
        yield ChatChunk(type="text", content='{"speech":"直接处理","assignments":[]}')

    class UnreachableGateway:
        available = True

        async def create_room(self, *_args, **_kwargs):
            raise RuntimeError("gateway unavailable")

    monkeypatch.setattr(chat_module.provider_manager, "chat_stream", fake_stream)
    monkeypatch.setattr(
        "omichub.application.services.agentteams_room_gateway_service.AgentTeamsRoomGatewayService",
        UnreachableGateway,
    )
    service = ChatService(MagicMock(spec=AsyncSession))
    service.get_session = AsyncMock(return_value=SimpleNamespace(sandbox_meta={}))  # type: ignore[method-assign]
    service.add_message = AsyncMock(return_value=SimpleNamespace(message_id="message-1"))  # type: ignore[method-assign]

    chunks = [chunk async for chunk in service._run_overdrive_turn(
        user_id="user", session_id="session", user_content="协作", manager_ctx=_manager_ctx(),
    )]

    assert [chunk.type for chunk in chunks] == ["mode_changed", "room_speech"]
    assert chunks[0].metadata["degraded"] is True
    assert chunks[1].content == "直接处理"
    assert "matrix_room_id" not in chunks[1].metadata


@pytest.mark.asyncio
async def test_overdrive_single_matrix_post_failure_keeps_room_speech(monkeypatch) -> None:
    _FakeAgentService.agents = [_agent("agent-1", "专家1")]
    monkeypatch.setattr("omichub.application.services.agent_service.AgentService", _FakeAgentService)

    async def fake_stream(**_kwargs):
        yield ChatChunk(type="text", content='{"speech":"直接处理","assignments":[]}')

    class PartiallyFailingGateway:
        available = True

        async def create_room(self, *_args, **_kwargs):
            return {"room_id": "!room:test"}

        calls = 0

        async def post_message(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("single post failed")
            return {"event_id": "$event"}

    session = SimpleNamespace(sandbox_meta={})
    monkeypatch.setattr(chat_module.provider_manager, "chat_stream", fake_stream)
    monkeypatch.setattr(
        "omichub.application.services.agentteams_room_gateway_service.AgentTeamsRoomGatewayService",
        PartiallyFailingGateway,
    )
    service = ChatService(MagicMock(spec=AsyncSession))
    service.get_session = AsyncMock(return_value=session)  # type: ignore[method-assign]
    service.add_message = AsyncMock(return_value=SimpleNamespace(message_id="message-1"))  # type: ignore[method-assign]

    chunks = [chunk async for chunk in service._run_overdrive_turn(
        user_id="user", session_id="session", user_content="协作", manager_ctx=_manager_ctx(),
    )]

    assert [chunk.type for chunk in chunks] == ["room_speech"]
    assert chunks[0].metadata["degraded"] is True
    assert chunks[0].metadata["matrix_room_id"] == "!room:test"
    assert chunks[0].content == "直接处理"


@pytest.mark.asyncio
async def test_room_events_returns_404_when_session_has_no_matrix_room(monkeypatch) -> None:
    """会话未绑定 matrix_room_id 时，room-events 返回 404 + 单条错误事件（前端静默降级）。"""
    import omichub.api.v1.chat as chat_api

    service = MagicMock()
    service.get_session = AsyncMock(return_value=SimpleNamespace(sandbox_meta={}))
    monkeypatch.setattr(chat_api, "ChatService", lambda _db: service)

    response = await chat_api.room_events("session", current_user_id="user", db=MagicMock())

    assert response.status_code == 404
    chunks = [chunk async for chunk in response.body_iterator]
    assert len(chunks) == 1
    assert "尚未绑定 Matrix 房间" in chunks[0]


@pytest.mark.asyncio
async def test_overdrive_creates_matrix_room_when_session_has_no_room_id(monkeypatch) -> None:
    _FakeAgentService.agents = [_agent("agent-1", "专家1")]
    monkeypatch.setattr("omichub.application.services.agent_service.AgentService", _FakeAgentService)

    async def fake_stream(**_kwargs):
        yield ChatChunk(type="text", content='{"speech":"直接处理","assignments":[]}')

    class Gateway:
        available = True

        async def create_room(self, *_args, **_kwargs):
            return {
                "room_id": "!new-room:test",
                "element_room_url": "https://element.test/#/room/!new-room:test",
            }

        async def post_message(self, *_args, **_kwargs):
            return {"event_id": "$event"}

    session = SimpleNamespace(sandbox_meta={})
    monkeypatch.setattr(chat_module.provider_manager, "chat_stream", fake_stream)
    monkeypatch.setattr(
        "omichub.application.services.agentteams_room_gateway_service.AgentTeamsRoomGatewayService",
        Gateway,
    )
    service = ChatService(MagicMock(spec=AsyncSession))
    service.get_session = AsyncMock(return_value=session)  # type: ignore[method-assign]
    service.add_message = AsyncMock(return_value=SimpleNamespace(message_id="message-1"))  # type: ignore[method-assign]

    chunks = [chunk async for chunk in service._run_overdrive_turn(
        user_id="user", session_id="session", user_content="协作", manager_ctx=_manager_ctx(),
    )]

    assert session.sandbox_meta["matrix_room_id"] == "!new-room:test"
    assert session.sandbox_meta["element_room_url"].endswith("!new-room:test")
    assert chunks[0].metadata["matrix_room_id"] == "!new-room:test"
