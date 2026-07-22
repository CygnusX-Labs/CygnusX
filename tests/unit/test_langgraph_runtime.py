"""LangGraph 运行时单元测试：假 provider + 假 tool_executor"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from omichub.infrastructure.ai_provider.openai_compatible import ChatChunk
from omichub.infrastructure.execution.langgraph_nodes import NodeDeps
from omichub.infrastructure.execution.langgraph_runtime import LangGraphRuntimeService

USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


def _make_stream(rounds: list[list[ChatChunk]]) -> tuple[Any, list[list[dict[str, Any]]]]:
    """构造假 chat_stream：第 N 次调用返回 rounds[N]，并记录收到的 messages"""
    calls: list[list[dict[str, Any]]] = []

    async def _stream(**kwargs: Any) -> AsyncIterator[ChatChunk]:
        calls.append(kwargs["messages"])
        for chunk in rounds[len(calls) - 1]:
            yield chunk

    return _stream, calls


def _tool_calls_chunk(name: str, args: dict[str, Any], call_id: str = "call_1") -> ChatChunk:
    return ChatChunk(
        type="tool_calls",
        metadata={
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }
            ]
        },
    )


def _make_runtime(
    rounds: list[list[ChatChunk]],
    tool_executor: Any = None,
) -> tuple[LangGraphRuntimeService, list[list[dict[str, Any]]]]:
    stream, calls = _make_stream(rounds)
    deps = NodeDeps(
        model_config=None,
        system_prompt="sys",
        chat_stream=stream,
        tool_executor=tool_executor,
    )
    return LangGraphRuntimeService(deps), calls


async def _collect(runtime: LangGraphRuntimeService) -> list[ChatChunk]:
    return [
        chunk
        async for chunk in runtime.stream([{"role": "user", "content": "你好"}])
    ]


async def test_no_tool_call_single_round() -> None:
    """无工具调用：一轮结束，text chunk 按序产出"""
    runtime, _ = _make_runtime(
        [
            [
                ChatChunk(type="text", content="你"),
                ChatChunk(type="text", content="好"),
                ChatChunk(type="done", metadata={"usage": USAGE}),
            ]
        ]
    )

    chunks = await _collect(runtime)

    assert [c.type for c in chunks] == ["text", "text"]
    assert [c.content for c in chunks] == ["你", "好"]
    assert runtime.last_usage == USAGE
    assert runtime.error is None
    # state 消息序列：user → assistant
    assert [m["role"] for m in runtime.last_messages] == ["user", "assistant"]
    assert runtime.last_messages[-1]["content"] == "你好"


async def test_one_tool_round_then_finish() -> None:
    """一轮工具调用回灌后第二轮结束：消息序列 assistant(tool_calls) → tool"""
    executed: list[tuple[str, dict[str, Any], str]] = []

    async def _executor(
        tool_name: str, args: dict[str, Any], tool_call_id: str
    ) -> dict[str, Any]:
        executed.append((tool_name, args, tool_call_id))
        return {"success": True, "result": {"value": 42}}

    runtime, calls = _make_runtime(
        [
            [
                _tool_calls_chunk("get_gene", {"gene": "TP53"}),
                ChatChunk(type="done", metadata={"usage": USAGE}),
            ],
            [
                ChatChunk(type="text", content="TP53 是抑癌基因"),
                ChatChunk(type="done", metadata={"usage": USAGE}),
            ],
        ],
        tool_executor=_executor,
    )

    chunks = await _collect(runtime)

    assert [c.type for c in chunks] == ["tool_call", "tool_result", "text"]
    assert chunks[0].metadata["tool_name"] == "get_gene"
    assert chunks[1].metadata["success"] is True
    assert chunks[1].metadata["result"] == {"value": 42}
    assert executed == [("get_gene", {"gene": "TP53"}, "call_1")]

    # 第二轮 LLM 收到的 messages 末尾：assistant(tool_calls) → role:tool
    second_round = calls[1]
    assert second_round[-2]["role"] == "assistant"
    assert second_round[-2]["tool_calls"][0]["function"]["name"] == "get_gene"
    assert second_round[-1]["role"] == "tool"
    assert second_round[-1]["tool_call_id"] == "call_1"
    assert json.loads(second_round[-1]["content"]) == {"value": 42}

    # 最终 state 消息序列完整
    assert [m["role"] for m in runtime.last_messages] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    # 两轮 usage 累计合并
    assert runtime.last_usage == {
        "prompt_tokens": 20,
        "completion_tokens": 10,
        "total_tokens": 30,
    }


async def test_tool_executor_exception_yields_error_chunk() -> None:
    """tool_executor 抛异常：产 error chunk 优雅结束，不向外抛错"""

    async def _executor(
        tool_name: str, args: dict[str, Any], tool_call_id: str
    ) -> dict[str, Any]:
        raise RuntimeError("MCP 连接断开")

    runtime, _ = _make_runtime(
        [
            [
                _tool_calls_chunk("get_gene", {"gene": "TP53"}),
                ChatChunk(type="done", metadata={"usage": USAGE}),
            ]
        ],
        tool_executor=_executor,
    )

    chunks = await _collect(runtime)

    assert [c.type for c in chunks] == ["tool_call", "error"]
    assert "MCP 连接断开" in chunks[-1].content
    assert runtime.error == "MCP 连接断开"
