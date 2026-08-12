"""聊天模式轻量沙盒工具 — 复用 standalone sandbox pool，无工作区耦合。

与 Studio sandbox_execute 的区别：
 - 后端：走 SandboxService（容器池），不走 studio_sandbox_manager
 - 前端：ChatCodeCard（轻量卡片），不走 StudioCodeCard
 - 无审批、无工作区文件操作、无产物持久化
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from loguru import logger

from omichub.infrastructure.ai_provider.openai_compatible import ChatChunk

# ===== 工具 schema =====

CHAT_SANDBOX_EXECUTE_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "chat_sandbox_execute",
        "description": (
            "在轻量级沙盒中执行代码（python/r/bash），适合快速验证、简单计算和可视化。"
            "流式返回 stdout/stderr/图表。复杂分析（多文件协作、工作区管理）请使用工作台。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "enum": ["python", "r", "bash"],
                    "description": "执行语言，默认 python",
                },
                "code": {"type": "string", "description": "要执行的完整代码"},
                "timeout": {
                    "type": "integer",
                    "description": "超时秒数，缺省 300s",
                },
            },
            "required": ["language", "code"],
        },
    },
}

CHAT_SANDBOX_TOOL_NAME = "chat_sandbox_execute"

# ===== 内部工具 =====

_STREAM_QUEUE_MAX_CHUNKS = 64
_STREAM_HEARTBEAT_INTERVAL_SECONDS = 15.0


def _error_result(message: str) -> dict[str, Any]:
    payload = {"error": message}
    return {
        "success": False,
        "result": {"llm_payload": payload, "ui_payload": dict(payload)},
    }


def _ok_result(llm_payload: dict[str, Any], ui_payload: dict[str, Any]) -> dict[str, Any]:
    return {"success": True, "result": {"llm_payload": llm_payload, "ui_payload": ui_payload}}


def _tail(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[-limit:], True


def _append_bounded_text(current: str, data: str, limit: int) -> tuple[str, bool]:
    combined = f"{current}\n{data}" if current else data
    return _tail(combined, limit)


# ===== 执行器 =====


async def execute_chat_sandbox(
    args: dict[str, Any],
    user_id: str,
    on_output: Any | None = None,
) -> dict[str, Any]:
    """在 standalone sandbox pool 中执行代码，返回 llm_payload + ui_payload。"""
    from omichub.application.services.sandbox_service import SandboxService
    from omichub.infrastructure.database.session import get_session_factory

    language = str(args.get("language") or "python")
    code = str(args.get("code") or "")
    timeout = int(args.get("timeout") or 300)

    if not code.strip():
        return _error_result("code 不能为空")

    if language not in {"python", "r", "bash"}:
        return _error_result(f"不支持的语言: {language}")

    try:
        async with get_session_factory()() as db:
            service = SandboxService(db)

            session = await service.create_session(UUID(user_id), language)
            await db.commit()

            stdout_parts: list[str] = []
            stderr_parts: list[str] = []
            images: list[str] = []
            echarts: list[Any] = []
            error: str | None = None

            async for event in service.execute_code(
                UUID(user_id), session.id, code, timeout, language=language
            ):
                etype = event.get("type")
                if etype == "stdout":
                    data = str(event.get("data", ""))
                    stdout_parts.append(data)
                    if on_output:
                        await on_output("stdout", data)
                elif etype == "stderr":
                    data = str(event.get("data", ""))
                    stderr_parts.append(data)
                    if on_output:
                        await on_output("stderr", data)
                elif etype == "image":
                    images.append(str(event.get("data", "")))
                elif etype == "echarts":
                    echarts.append(event.get("data", {}))
                elif etype == "error":
                    error = str(event.get("detail", "执行错误"))
                elif etype == "done":
                    pass

            # SandboxService 只负责状态流转并 flush；该工具使用独立 session，
            # 必须显式提交，才能让 5 分钟回收任务看到最新 last_activity/status。
            await db.commit()

            stdout_full = "".join(stdout_parts)
            stderr_full = "".join(stderr_parts)

            llm_stdout, _ = _tail(stdout_full, 2000)
            llm_stderr, _ = _tail(stderr_full, 1000)

            llm_payload: dict[str, Any] = {
                "success": error is None,
                "stdout": llm_stdout,
                "stderr": llm_stderr,
                "images_count": len(images),
                "echarts_count": len(echarts),
            }
            if error:
                llm_payload["error"] = error

            ui_payload: dict[str, Any] = {
                "language": language,
                "stdout": stdout_full,
                "stderr": stderr_full,
                "images": images,
                "echarts": echarts,
            }
            if error:
                ui_payload["error"] = error

            return _ok_result(llm_payload, ui_payload)

    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ChatSandbox] 执行异常: {e}")
        return _error_result(f"沙盒执行失败: {e}")


# ===== 流式包装 =====


async def stream_chat_sandbox_tool(
    args: dict[str, Any],
    user_id: str,
    tool_call_id: str = "",
) -> AsyncIterator[ChatChunk | dict[str, Any]]:
    """流式执行聊天沙盒工具，产出 tool_output 事件 + 最终结果信封。"""
    queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue(maxsize=_STREAM_QUEUE_MAX_CHUNKS)

    async def _on_output(stream: str, data: str) -> None:
        await queue.put((stream, data))

    task = asyncio.create_task(execute_chat_sandbox(args, user_id, on_output=_on_output))

    last_emit = time.monotonic()
    while True:
        if task.done() and queue.empty():
            break
        try:
            stream, data = await asyncio.wait_for(queue.get(), timeout=0.05)
        except TimeoutError:
            if time.monotonic() - last_emit >= _STREAM_HEARTBEAT_INTERVAL_SECONDS:
                last_emit = time.monotonic()
                yield ChatChunk(type="heartbeat")
            continue
        last_emit = time.monotonic()
        yield ChatChunk(
            type="tool_output",
            metadata={
                "tool": CHAT_SANDBOX_TOOL_NAME,
                "tool_call_id": tool_call_id,
                "stream": stream,
                "data": data,
            },
        )
    try:
        yield await task
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ChatSandbox] 流式执行异常: {e}")
        yield _error_result(f"工具执行失败: {e}")
