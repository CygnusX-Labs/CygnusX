"""One runtime gate for automated memory reads and writes."""

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.core.telemetry import get_meter

_gate_degraded = get_meter("cygnusx.memory").create_counter(
    "memory.runtime_gate_degraded", description="记忆运行闸门读取失败，按关闭处理"
)


async def is_memory_runtime_enabled(db: AsyncSession | None) -> bool:
    from cygnusx.application.services.site_settings_service import SiteSettingsService
    from cygnusx.core.config import get_settings

    if not get_settings().memory_v2_enabled or db is None:
        return False
    try:
        return await SiteSettingsService(db).is_agent_memory_enabled()
    except Exception as exc:
        _gate_degraded.add(1)
        logger.warning("memory.runtime_gate_degraded error_type={}", type(exc).__name__)
        return False
