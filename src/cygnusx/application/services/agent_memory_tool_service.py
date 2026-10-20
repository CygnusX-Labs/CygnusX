"""将 AgentMemoryService 暴露为 ToolBridge 后端同步工具。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from cygnusx.application.schemas.tool_invocation import ToolInvocationContext
from cygnusx.application.services.agent_memory_service import AgentMemoryService
from cygnusx.core.exceptions import BusinessError
from cygnusx.infrastructure.database.models.chat import ChatSessionModel


class AgentMemoryToolService:
    """记忆工具必须在 builtin 调用上下文中执行，确保用户与会话可追溯。"""

    @staticmethod
    def _service(context: ToolInvocationContext | None) -> AgentMemoryService:
        if context is None:
            raise BusinessError("长期记忆工具需要受控的会话调用上下文")
        return AgentMemoryService(context.db)

    @staticmethod
    async def _assert_runtime(context: ToolInvocationContext | None, user_id: str) -> None:
        from cygnusx.application.services.memory_runtime_policy import is_memory_runtime_enabled

        if context is None:
            raise BusinessError("长期记忆工具需要受控的会话调用上下文")
        if context.user_id != user_id:
            raise BusinessError("记忆身份与调用上下文不一致")
        if not await is_memory_runtime_enabled(context.db):
            raise BusinessError("平台记忆功能当前不可用或已被管理员关闭")

    @staticmethod
    def _memory_agent_id(scope: str, context: ToolInvocationContext | None) -> str | None:
        """画像与偏好跨 Agent 共享，项目和摘要按执行 Agent 隔离。"""
        if scope.strip().lower() in {"profile", "preference"}:
            return None
        return context.agent_id if context else None

    @staticmethod
    async def _project_id(context: ToolInvocationContext | None) -> str | None:
        if context is None:
            return None
        session = await context.db.scalar(
            select(ChatSessionModel).where(
                ChatSessionModel.session_id == context.session_id,
                ChatSessionModel.user_id == context.user_id,
            )
        )
        return session.project_id if session else None

    async def save_memory(
        self,
        *,
        user_id: str,
        content: str,
        scope: str,
        keywords: list[str] | None = None,
        context: ToolInvocationContext | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        await self._assert_runtime(context, user_id)
        result = await self._service(context).save_memory(
            user_id=user_id,
            content=content,
            scope=scope,
            keywords=keywords,
            agent_id=self._memory_agent_id(scope, context),
            project_id=await self._project_id(context),
            source_session=context.session_id if context else None,
        )
        return {
            "success": True,
            "memory_id": result["memory"]["id"],
            "action": result["action"],
            "content": result["memory"]["content"],
            "summary": f"已记住：{result['memory']['content']}",
        }

    async def update_memory(
        self,
        *,
        user_id: str,
        memory_id: str,
        content: str,
        keywords: list[str] | None = None,
        context: ToolInvocationContext | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        await self._assert_runtime(context, user_id)
        result = await self._service(context).update_memory(
            user_id=user_id,
            memory_id=memory_id,
            content=content,
            keywords=keywords,
            source_session=context.session_id if context else None,
        )
        return {
            "success": True,
            "memory_id": result["memory"]["id"],
            "action": result["action"],
            "summary": "已更新跨会话记忆。",
        }

    async def forget_memory(
        self,
        *,
        user_id: str,
        memory_id: str,
        context: ToolInvocationContext | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        await self._assert_runtime(context, user_id)
        result = await self._service(context).forget_memory(
            user_id=user_id, memory_id=memory_id,
            agent_id=context.agent_id if context else None,
            project_id=await self._project_id(context),
        )
        summary = "已归档该条记忆；词面检查不能保证清除所有复述。"
        if result.get("residual_hints"):
            summary = "已归档该条，但摘要、画像或其他事实中可能仍有相关表述，请确认是否清理。"
        elif result.get("scan_status") in {"disabled", "failed"}:
            summary = "已归档该条，残留检查未启用或未完成；其他载体可能仍有相关表述。"
        return {"success": True, **result, "summary": summary}

    async def search_memory(
        self,
        *,
        user_id: str,
        query: str,
        scope: str | None = None,
        limit: int = 5,
        context: ToolInvocationContext | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        await self._assert_runtime(context, user_id)
        result = await self._service(context).search_memory(
            user_id=user_id,
            query=query,
            scope=scope,
            limit=limit,
            agent_id=context.agent_id if context else None,
            project_id=await self._project_id(context),
        )
        return {"success": True, **result, "summary": f"找到 {result['count']} 条相关记忆。"}

    async def update_memory_block(
        self,
        *,
        user_id: str,
        block_name: str,
        content: str,
        expected_version: int,
        context: ToolInvocationContext | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if context is None or not context.agent_id:
            raise BusinessError("更新记忆块需要当前 Agent 上下文")
        await self._assert_runtime(context, user_id)
        result = await self._service(context).update_memory_block(
            user_id, context.agent_id, block_name, content, expected_version,
            project_id=await self._project_id(context) if block_name == "current_focus" else None,
        )
        await context.db.commit()
        return {
            "success": True, "block_name": block_name, "version": result["version"],
            "summary": "记忆块已更新。",
        }
