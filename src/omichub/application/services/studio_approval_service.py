"""OmicStudio 工具审批服务 —— supervised 权限模式的人机协作闸（HITL）。

设计文档 docs/26.7.21/studio_hitl_design.md §3：
- supervised 模式下写/执行类工具（APPROVAL_REQUIRED_TOOLS）需用户批准后才进沙盒；
- 记录存 Redis（``studio:approval:{id}``，TTL 1800s），多进程安全，
  规避 tool_confirmation_service 进程内内存无法跨进程消费的坑；
- chat_service 发出 approval_request 事件后 await BLPOP
  （``studio:approval:result:{id}``）等 REST 端点写入的决议；
  超时按拒绝处理（action="timeout"）。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable
from typing import Any, cast

from loguru import logger

from omichub.infrastructure.cache.redis_client import get_redis

APPROVAL_REQUIRED_TOOLS: frozenset[str] = frozenset(
    {
        "sandbox_execute",
        "workspace_write",
        "workspace_edit",
        "artifact_register",
    }
)

APPROVAL_TTL_SECONDS = 1800

_RECORD_KEY = "studio:approval:{approval_id}"
_RESULT_KEY = "studio:approval:result:{approval_id}"


class StudioApprovalService:
    """Studio 工具审批记录与决议等待（Redis 存储，跨进程安全）。"""

    async def create(
        self,
        user_id: str,
        session_id: str,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        risk_hint: str = "",
    ) -> dict[str, Any]:
        """创建 pending 审批记录并写入 Redis（TTL 1800s），返回记录字典。"""
        record: dict[str, Any] = {
            "approval_id": uuid.uuid4().hex,
            "user_id": str(user_id),
            "session_id": session_id,
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "risk_hint": risk_hint,
            "status": "pending",
        }
        await get_redis().setex(
            _RECORD_KEY.format(approval_id=record["approval_id"]),
            APPROVAL_TTL_SECONDS,
            json.dumps(record, ensure_ascii=False, default=str),
        )
        return record

    async def get(self, approval_id: str) -> dict[str, Any] | None:
        raw = await get_redis().get(_RECORD_KEY.format(approval_id=approval_id))
        if raw is None:
            return None
        try:
            record = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return record if isinstance(record, dict) else None

    async def wait_resolution(
        self,
        approval_id: str,
        timeout: int = APPROVAL_TTL_SECONDS,  # noqa: ASYNC109 - 透传 BLPOP 等待秒数
    ) -> dict[str, Any]:
        """BLPOP 等待 REST 端点写入的决议；超时返回 {"action": "timeout"}。

        BLPOP 本身是 await，不阻塞事件循环。决议 JSON 由 resolve() 以
        RPUSH 写入 ``studio:approval:result:{id}``。
        """
        key = _RESULT_KEY.format(approval_id=approval_id)
        # redis.asyncio 类型标注为 Awaitable[T] | T，async 客户端实际恒为 Awaitable
        item = await cast(Awaitable[tuple[str, str] | None], get_redis().blpop([key], timeout=timeout))
        if item is None:
            return {"action": "timeout"}
        _, raw = item
        try:
            resolution = json.loads(raw)
        except (TypeError, ValueError):
            logger.warning(f"[Studio] 审批 {approval_id} 决议 JSON 非法，按超时处理")
            return {"action": "timeout"}
        if not isinstance(resolution, dict):
            return {"action": "timeout"}
        return resolution

    async def resolve(
        self,
        approval_id: str,
        user_id: str,
        action: str,
        modified_args: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> dict[str, Any] | None:
        """消费审批：校验归属与 pending 状态，写决议 list 并更新记录状态。

        返回更新后的记录；记录不存在、归属不符或已被消费（含超时落账）时返回 None。
        """
        redis = get_redis()
        record_key = _RECORD_KEY.format(approval_id=approval_id)
        record = await self.get(approval_id)
        if record is None:
            return None
        if record.get("user_id") != str(user_id) or record.get("status") != "pending":
            return None

        record["status"] = action
        if reason:
            record["reason"] = reason
        await redis.setex(
            record_key, APPROVAL_TTL_SECONDS, json.dumps(record, ensure_ascii=False, default=str)
        )

        resolution: dict[str, Any] = {"action": action}
        if modified_args is not None:
            resolution["modified_args"] = modified_args
        if reason:
            resolution["reason"] = reason
        result_key = _RESULT_KEY.format(approval_id=approval_id)
        await cast(Awaitable[int], redis.rpush(result_key, json.dumps(resolution, ensure_ascii=False, default=str)))
        await redis.expire(result_key, APPROVAL_TTL_SECONDS)
        return record


_studio_approval_service: StudioApprovalService | None = None


def get_studio_approval_service() -> StudioApprovalService:
    global _studio_approval_service
    if _studio_approval_service is None:
        _studio_approval_service = StudioApprovalService()
    return _studio_approval_service
