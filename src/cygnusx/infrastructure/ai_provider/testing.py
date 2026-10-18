"""Explicitly gated deterministic provider for isolated runtime acceptance."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from cygnusx.infrastructure.ai_provider.openai_compatible import ChatChunk


class DeterministicTestProvider:
    """Return scripted tool calls and echo only tool results supplied by Runtime."""

    def __init__(self, config: Any) -> None:
        self.update_config(config)
        self.name = config.name
        self.model = config.model
        self.calls = 0

    def update_config(self, config: Any) -> None:
        self.config = config
        self.name = config.name
        self.model = config.model

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 65536,
        tools: list[dict[str, Any]] | None = None,
        deep_thinking: bool = False,
    ) -> AsyncIterator[ChatChunk]:
        del system_prompt, temperature, max_tokens, deep_thinking
        self.calls += 1
        last_user_index = max(
            (index for index, message in enumerate(messages) if message.get("role") == "user"),
            default=-1,
        )
        tool_call_positions: dict[str, int] = {}
        for index, message in enumerate(messages[last_user_index + 1 :], start=last_user_index + 1):
            if message.get("role") != "assistant":
                continue
            for call in message.get("tool_calls", []):
                if isinstance(call, dict) and isinstance(call.get("id"), str):
                    tool_call_positions[call["id"]] = index
        tool_results = [
            message
            for index, message in enumerate(messages[last_user_index + 1 :], start=last_user_index + 1)
            if message.get("role") == "tool"
            and message.get("tool_call_id") in tool_call_positions
            and index > tool_call_positions[message["tool_call_id"]]
        ]
        if not tool_results:
            yield self._tool_call(tools)
            yield ChatChunk(type="done", metadata={"finish_reason": "tool_calls"})
            return

        content = "\n".join(str(message.get("content", "")) for message in tool_results)
        yield ChatChunk(type="text", content=content)
        yield ChatChunk(type="done", metadata={"finish_reason": "stop"})

    def _tool_call(self, tools: list[dict[str, Any]] | None) -> ChatChunk:
        script = self.config.extra_params.get("deterministic_test_script")
        if not isinstance(script, dict):
            raise RuntimeError("DETERMINISTIC_TEST_SCRIPT_INVALID")
        name = script.get("name")
        arguments = script.get("arguments", {})
        call_id = script.get("call_id")
        declared_names = {
            item.get("function", {}).get("name")
            for item in tools or []
            if isinstance(item, dict)
        }
        if (
            not isinstance(name, str)
            or name not in declared_names
            or not isinstance(arguments, dict)
            or not isinstance(call_id, str)
            or not call_id
        ):
            raise RuntimeError("DETERMINISTIC_TEST_SCRIPT_INVALID")
        return ChatChunk(
            type="tool_calls",
            metadata={
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": json.dumps(arguments, separators=(",", ":")),
                        },
                    }
                ]
            },
        )
