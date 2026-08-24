"""LangGraph Agent Runtime。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from loguru import logger

from cygnusx.application.services.agent_handoff_service import HANDOFF_TOOL_NAME
from cygnusx.application.services.chat.configuration import (
    RESEARCH_TOOL_CHANNEL,
    RESEARCH_TOOL_NAMES,
)
from cygnusx.application.services.chat.utils import (
    _cap_tool_invocation_payload,
    _fanout_ask_request,
    _normalize_ask_questions,
)
from cygnusx.application.services.chat_sandbox_tools import (
    CHAT_SANDBOX_TOOL_NAME,
    execute_chat_sandbox,
)
from cygnusx.application.services.execution_events import execution_chunk, execution_metadata
from cygnusx.application.services.parallel_subagent_service import PARALLEL_SUBAGENTS_TOOL_NAME
from cygnusx.domain.skill.services import SKILL_TOOL_NAMES
from cygnusx.infrastructure.ai_provider.openai_compatible import (
    ChatChunk,
    merge_token_usage,
    provider_manager,
)

from cygnusx.application.services.chat.runtimes.delegating_runtime import DelegatingAgentRuntime


class LangGraphChatRuntime(DelegatingAgentRuntime):
    """LangGraph 请求的显式 Runtime 身份与通用 ReAct 流循环。"""

    async def _stream_agent_chat_langgraph(
        self,
        *,
        user_id: str,
        session_id: str,
        ai_message_id: str,
        model_config: Any,
        llm_messages: list[dict[str, Any]],
        system_prompt: str | None,
        tools: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        deep_thinking: bool,
        active_mcp_servers: list[Any],
        mcp_client: Any,
        tool_context: Any,
        skills: list[Any] | None = None,
        skill_pins: dict[str, int] | None = None,
        web_sources: list[dict[str, Any]] | None = None,
        handoff_handler: Any | None = None,
        extend_max_rounds: bool = False,
    ) -> AsyncIterator[ChatChunk]:
        """LangGraph 引擎路径：状态图驱动 ReAct 循环，事件协议与手写循环一致

        tool_executor 复刻 legacy 非 Studio 工具路由：技能内部工具（use_skill /
        skill_resource）→ self._service._execute_skill_tool；ask_user → 澄清信封（图经
        state["ask_request"] 收尾，由本函数产出 ask_request 事件）；knowledge_search →
        self._service._knowledge_search_chat；MCP server 匹配 → MCPClient.call_tool；
        web_search → self._service._web_search；未挂载 → 报错信封。
        """
        runtime_state: dict[str, Any] = {
            "model_config": model_config,
            "llm_messages": list(llm_messages),
            "system_prompt": system_prompt,
            "tools": list(tools),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "active_mcp_servers": list(active_mcp_servers),
            "tool_context": tool_context,
            "skills": list(skills or []),
            "skill_pins": skill_pins or {},
        }
        persisted_web_sources = web_sources if web_sources is not None else []
        from cygnusx.infrastructure.execution.langgraph_nodes import NodeDeps
        from cygnusx.infrastructure.execution.langgraph_runtime import (
            LangGraphRuntimeService,
        )

        def _find_server(tool_name: str) -> Any:
            return next(
                (
                    s
                    for s in runtime_state["active_mcp_servers"]
                    if any(t.tool_name == tool_name for t in s.tools)
                ),
                None,
            )

        def _resolve_channel(tool_name: str) -> str | None:
            if tool_name == HANDOFF_TOOL_NAME:
                return "handoff"
            if tool_name == CHAT_SANDBOX_TOOL_NAME:
                return "chat-sandbox"
            if tool_name in SKILL_TOOL_NAMES:
                return "skills"
            if tool_name in RESEARCH_TOOL_NAMES:
                return RESEARCH_TOOL_CHANNEL
            server = _find_server(tool_name)
            return server.name if server else None

        async def _tool_executor(
            tool_name: str, args: dict[str, Any], tool_call_id: str
        ) -> dict[str, Any]:
            if tool_name == HANDOFF_TOOL_NAME:
                from cygnusx.application.services.tool_bridge_service import (
                    get_tool_bridge_service,
                )

                bridge_result = await get_tool_bridge_service().execute(
                    user_id=user_id,
                    tool_name=tool_name,
                    arguments=args,
                    context=runtime_state["tool_context"],
                )
                return {
                    "success": bool(bridge_result.get("success")),
                    "result": bridge_result,
                }
            if tool_name in SKILL_TOOL_NAMES:
                return await self._service._execute_skill_tool(
                    tool_name,
                    args,
                    runtime_state["skills"],
                    skill_pins=runtime_state.get("skill_pins"),
                )
            if tool_name == "ask_user":
                # 与 legacy stop_after_tools 同一信封；图经 state["ask_request"]
                # 结束后由下方产出 ask_request 事件并收尾本轮。
                questions = _normalize_ask_questions(args)
                first = questions[0]
                ask_payload: dict[str, Any] = {
                    "questions": questions,
                    "question": first["question"],
                    "options": first["options"],
                    "message": "问题已展示给用户，用户将在下一条消息中回答。本轮回复到此结束，请等待用户答复。",
                }
                return {
                    "success": True,
                    "result": {"llm_payload": ask_payload, "ui_payload": dict(ask_payload)},
                }
            if tool_name == "knowledge_search":
                session = await self._service.get_session(session_id, user_id)
                return await self._service._knowledge_search_chat(
                    args, project_id=session.project_id if session else None
                )
            if tool_name == "web_search":
                result = await self._service._web_search(args)
                search_payload = result.get("result") if isinstance(result, dict) else None
                search_results = (
                    search_payload.get("results", []) if isinstance(search_payload, dict) else []
                )
                if isinstance(search_results, list):
                    persisted_web_sources.extend(
                        item for item in search_results if isinstance(item, dict)
                    )
                return result
            if tool_name == CHAT_SANDBOX_TOOL_NAME:
                # 与 legacy 手写循环同一执行本体；LangGraph 执行器只回单个信封，
                # 不走 stream_chat_sandbox_tool 的增量 tool_output 事件，
                # stdout/stderr/产物随最终 ui_payload 一次性透出。
                return await execute_chat_sandbox(args, user_id)
            server = _find_server(tool_name)
            if server is None:
                return {"success": False, "error": f"工具 {tool_name} 未挂载到该 Agent"}
            return await mcp_client.call_tool(
                server,
                tool_name,
                args,
                user_id=user_id,
                context=runtime_state["tool_context"],
            )

        full_content = ""
        update_counter = 0
        first_chunk_sent = False
        accumulated_usage: dict[str, Any] | None = None
        # 轮次上限与手写循环对齐：默认 100 轮；前端弹窗确认继续后传
        # extend_max_rounds=True 扩展到 1000 轮。
        max_rounds = 1000 if extend_max_rounds else 100
        # 历史重载重建工具卡片/图表所需（对齐 legacy 手写循环）：
        # timeline 记录正文段/工具段的交错顺序，persisted_tool_invocations 保存
        # 每次工具调用的 arguments/result/ui_payload——Plotly 图表等就在 ui_payload 里，
        # 不落库则重开会话后卡片与图全部丢失。
        persisted_tool_invocations: list[dict[str, Any]] = []
        timeline: list[dict[str, Any]] = []
        timeline_text_buffer = ""
        pending_tool_args: dict[str, dict[str, Any]] = {}
        pending_fanout_ask: dict[str, Any] | None = None
        execution_path = "chat_langgraph"
        execution_run_id = f"agent-langgraph:{ai_message_id}"
        execution_agent_id = str(
            getattr(tool_context, "agent_id", None)
            or getattr(getattr(tool_context, "agent", None), "agent_id", None)
            or "router"
        )
        execution_round = 0

        yield execution_chunk(
            "agent_turn_started",
            session_id=session_id,
            run_id=execution_run_id,
            agent_id=execution_agent_id,
            round_number=0,
            execution_path=execution_path,
            message_id=ai_message_id,
            tool_count=len(tools),
        )

        def _flush_timeline_text() -> None:
            nonlocal timeline_text_buffer
            text = timeline_text_buffer
            timeline_text_buffer = ""
            if text:
                timeline.append({"kind": "text", "text": text})

        def _failed_terminal_events(error: str) -> tuple[ChatChunk, ChatChunk]:
            return (
                execution_chunk(
                    "agent_turn_failed",
                    session_id=session_id,
                    run_id=execution_run_id,
                    agent_id=execution_agent_id,
                    round_number=execution_round,
                    execution_path=execution_path,
                    error=error,
                ),
                ChatChunk(
                    type="done",
                    metadata={
                        "session_id": session_id,
                        "message_id": ai_message_id,
                        "status": "error",
                    },
                ),
            )

        try:
            while True:
                deps = NodeDeps(
                    model_config=runtime_state["model_config"],
                    system_prompt=runtime_state["system_prompt"],
                    temperature=runtime_state["temperature"],
                    max_tokens=runtime_state["max_tokens"],
                    tools=runtime_state["tools"] or None,
                    deep_thinking=deep_thinking,
                    tool_executor=_tool_executor,
                    channel_resolver=_resolve_channel,
                    chat_stream=provider_manager.chat_stream,
                    emit_execution_events=True,
                    session_id=session_id,
                    run_id=execution_run_id,
                    agent_id=execution_agent_id,
                    execution_path=execution_path,
                )
                runtime = LangGraphRuntimeService(deps, max_rounds=max_rounds)
                async for chunk in runtime.stream(runtime_state["llm_messages"]):
                    if chunk.type == "text":
                        if chunk.metadata.get("is_reasoning"):
                            # 推理过程不并入最终正文，但仍透传给前端
                            yield chunk
                            continue
                        full_content += chunk.content
                        timeline_text_buffer += chunk.content
                        update_counter += 1
                        if update_counter % 5 == 0:
                            await self._service.update_message_content(
                                ai_message_id, full_content, "streaming"
                            )
                        if not first_chunk_sent:
                            chunk.metadata["session_id"] = session_id
                            chunk.metadata["message_id"] = ai_message_id
                            first_chunk_sent = True
                        yield chunk
                    elif chunk.type == "error":
                        error = chunk.content or "LangGraph Runtime 返回错误"
                        await self._service.update_message_content(
                            ai_message_id,
                            full_content or f"生成失败: {error}",
                            "error",
                            {"error": error},
                        )
                        yield chunk
                        for terminal_chunk in _failed_terminal_events(error):
                            yield terminal_chunk
                        return
                    elif chunk.type == "tool_call":
                        execution_round = max(execution_round, int(chunk.metadata.get("round") or 1))
                        chunk.metadata.update(
                            {
                                "execution_path": execution_path,
                                "run_id": execution_run_id,
                                "round": execution_round,
                            }
                        )
                        # 正文段在工具调用前收口，保持"正文→工具"交错顺序
                        _flush_timeline_text()
                        tc_meta = chunk.metadata or {}
                        call_id = tc_meta.get("tool_call_id", "")
                        if call_id:
                            pending_tool_args[call_id] = tc_meta.get("arguments", {}) or {}
                        yield chunk
                    elif chunk.type == "tool_result":
                        tc_meta = chunk.metadata or {}
                        chunk.metadata.update(
                            {
                                "execution_path": execution_path,
                                "run_id": execution_run_id,
                                "round": execution_round,
                            }
                        )
                        call_id = tc_meta.get("tool_call_id", "")
                        tool_name = tc_meta.get("tool_name", "")
                        success = bool(tc_meta.get("success"))
                        llm_result = tc_meta.get("result")
                        ui_payload = tc_meta.get("ui_payload")
                        timeline.append(
                            {
                                "kind": "tool",
                                "tool_call_id": call_id,
                                "tool_name": tool_name,
                            }
                        )
                        persisted_tool_invocations.append(
                            {
                                "tool_call_id": call_id,
                                "tool_name": tool_name,
                                "arguments": pending_tool_args.pop(call_id, {}),
                                "success": success,
                                "result": _cap_tool_invocation_payload(llm_result),
                                "ui_payload": _cap_tool_invocation_payload(ui_payload),
                                "mcp_server": tc_meta.get("mcp_server"),
                            }
                        )
                        if tool_name == PARALLEL_SUBAGENTS_TOOL_NAME and isinstance(llm_result, dict):
                            envelope = {
                                "llm_payload": llm_result.get("llm_payload"),
                                "ui_payload": ui_payload,
                            }
                            pending_fanout_ask = _fanout_ask_request(envelope)
                        await self._service.update_message_content(
                            ai_message_id,
                            full_content,
                            "streaming",
                            {
                                "tool_invocations": persisted_tool_invocations,
                                "timeline": timeline,
                            },
                        )
                        yield chunk
                    else:
                        # 其余事件直接透传（metadata 已对齐 legacy）
                        yield chunk

                accumulated_usage = merge_token_usage(accumulated_usage, runtime.last_usage)
                # ask_user 澄清：问题经 ask_request 事件展示给用户，收尾本轮，
                # 等用户下一条消息回答（对齐 legacy stop_after_tools 语义）。
                ask_request = runtime.last_ask_request
                if ask_request is not None:
                    _flush_timeline_text()
                    questions = _normalize_ask_questions(ask_request.get("args") or {})
                    first = questions[0]
                    # ask_user 工具调用已在上方 tool_result 分支落库；这里把最终
                    # timeline 随完成态一并写入，保证历史重载能重建澄清卡片。
                    await self._service.update_message_content(
                        ai_message_id,
                        full_content,
                        "complete",
                        {
                            **({"usage": accumulated_usage} if accumulated_usage else {}),
                            **({"timeline": timeline} if timeline else {}),
                        }
                        or None,
                    )
                    yield ChatChunk(
                        type="ask_request",
                        metadata={
                            "tool_call_id": ask_request.get("tool_call_id", ""),
                            "questions": questions,
                            # 兼容旧前端：首问题的平铺字段
                            "question": first["question"],
                            "options": first["options"],
                        },
                    )
                    break
                if pending_fanout_ask is not None:
                    _flush_timeline_text()
                    first = pending_fanout_ask["questions"][0]
                    yield ChatChunk(
                        type="ask_request",
                        metadata={
                            "tool_call_id": "",
                            **pending_fanout_ask,
                            "question": first["question"],
                            "options": first["options"],
                        },
                    )
                    pending_fanout_ask = None
                    await self._service.update_message_content(
                        ai_message_id,
                        full_content,
                        "complete",
                        {"timeline": timeline} if timeline else None,
                    )
                    break
                directive = runtime.last_handoff
                if directive is None:
                    break
                if handoff_handler is None:
                    error = "Agent 转交未被当前运行时处理"
                    await self._service.update_message_content(
                        ai_message_id,
                        full_content or error,
                        "error",
                        {"error": error},
                    )
                    yield ChatChunk(type="error", content=error)
                    for terminal_chunk in _failed_terminal_events(error):
                        yield terminal_chunk
                    return
                next_state = await handoff_handler(directive)
                runtime_state.update(next_state)
                execution_round += 1
                yield execution_chunk(
                    "agent_turn_continued",
                    session_id=session_id,
                    run_id=execution_run_id,
                    agent_id=execution_agent_id,
                    round_number=execution_round,
                    execution_path=execution_path,
                    reason="handoff",
                )
                yield ChatChunk(
                    type="handoff",
                    metadata={
                        **directive,
                        "session_id": session_id,
                        "message_id": ai_message_id,
                    },
                )
            if (
                not full_content.strip()
                and runtime.last_handoff is None
                and runtime.last_ask_request is None
            ):
                diagnostic = (
                    "模型请求已完成，但没有返回可展示的正文；"
                    f"model={runtime_state['model_config'].model}, "
                    f"usage={accumulated_usage or {}}, runtime_error={runtime.error or ''}"
                )
                logger.error("[Agent空响应] session={} {}", session_id, diagnostic)
                await self._service.update_message_content(
                    ai_message_id,
                    diagnostic,
                    "error",
                    {"error": diagnostic, "usage": accumulated_usage or {}},
                )
                yield ChatChunk(
                    type="error",
                    content="模型完成了请求，但没有返回正文。请稍后重试；若持续出现，请检查模型的思考开关和输出上限。",
                    metadata={
                        "session_id": session_id,
                        "message_id": ai_message_id,
                        "model": runtime_state["model_config"].model,
                        "usage": accumulated_usage or {},
                    },
                )
                yield execution_chunk(
                    "agent_turn_failed",
                    session_id=session_id,
                    run_id=execution_run_id,
                    agent_id=execution_agent_id,
                    round_number=execution_round,
                    execution_path=execution_path,
                    error=diagnostic,
                )
                yield ChatChunk(
                    type="done",
                    metadata={
                        "session_id": session_id,
                        "message_id": ai_message_id,
                        "status": "error",
                    },
                )
                return
        except Exception as e:  # noqa: BLE001
            error = str(e)
            await self._service.update_message_content(
                ai_message_id,
                full_content or f"生成失败: {error}",
                "error",
                {"error": error},
            )
            yield ChatChunk(
                type="error",
                content=f"生成失败: {error}",
                metadata={
                    "session_id": session_id,
                    "message_id": ai_message_id,
                    **execution_metadata(
                        "agent_turn_failed",
                        session_id=session_id,
                        run_id=execution_run_id,
                        agent_id=execution_agent_id,
                        round_number=execution_round,
                        execution_path=execution_path,
                        error=error,
                    ),
                },
            )
            for terminal_chunk in _failed_terminal_events(error):
                yield terminal_chunk
            return

        # 收尾：complete + usage + 会话用量累计 + done（与 legacy 一致）
        _flush_timeline_text()
        last_usage = accumulated_usage
        await self._service.update_message_content(
            ai_message_id,
            full_content,
            "complete",
            {
                **({"usage": last_usage} if last_usage else {}),
                **({"web_sources": persisted_web_sources} if persisted_web_sources else {}),
                **({"timeline": timeline} if timeline else {}),
            }
            or None,
        )
        if (
            runtime.rounds_exhausted
            and runtime.last_handoff is None
            and runtime.last_ask_request is None
        ):
            # 轮次触顶：与手写循环一致，通知前端弹窗选择是否以扩展上限继续
            yield ChatChunk(
                type="round_limit",
                content=f"工具调用轮次达到上限（{max_rounds}），任务提前结束",
                metadata={
                    "session_id": session_id,
                    "message_id": ai_message_id,
                    "max_rounds": max_rounds,
                    "can_extend": max_rounds < 1000,
                },
            )
        await self._service._apply_usage_to_session(ai_message_id, last_usage)
        yield execution_chunk(
            "agent_final_result",
            session_id=session_id,
            run_id=execution_run_id,
            agent_id=execution_agent_id,
            round_number=execution_round,
            execution_path=execution_path,
            message_id=ai_message_id,
            status="round_limit" if runtime.rounds_exhausted else "completed",
        )
        yield ChatChunk(
            type="done",
            metadata={
                "session_id": session_id,
                "message_id": ai_message_id,
                "usage": last_usage,
            },
        )
