"""聊天 Runtime 可独立评估的运行时开关。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class ChatRuntimeFeatureGates:
    """集中读取不依赖具体 Runtime 的后台能力开关。"""

    _db: AsyncSession | None

    async def _memory_runtime_enabled(self) -> bool:
        """记忆功能是否处于可用状态（配置能力闸门 + 管理员运行时开关）。"""
        from cygnusx.application.services.memory_runtime_policy import is_memory_runtime_enabled

        return await is_memory_runtime_enabled(self._db)

    async def _admin_subagent_fanout_enabled(self) -> bool:
        """返回后台「对话内并行子 Agent」灰度开关状态。"""
        from cygnusx.application.services.site_settings_service import SiteSettingsService
        from cygnusx.core.config import get_settings

        if get_settings().subagent_fanout_enabled:
            return True
        if self._db is None:
            return False
        try:
            return bool(
                (await SiteSettingsService(self._db).get_settings()).subagent_fanout_enabled
            )
        except Exception:  # noqa: BLE001
            return False
