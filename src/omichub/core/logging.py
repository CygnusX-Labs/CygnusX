"""日志配置 - 基于 loguru"""

import sys

from loguru import logger

from omichub.core.config import get_settings


def setup_logging() -> None:
    """初始化日志配置"""
    settings = get_settings()
    level = "DEBUG" if settings.app_debug else "INFO"

    logger.remove()
    logger.add(
        sys.stdout,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
        backtrace=True,
        diagnose=settings.app_debug,
    )

    if settings.is_production:
        logger.add(
            "logs/omichub.log",
            level="INFO",
            rotation="50 MB",
            retention="30 days",
            compression="zip",
            format=(
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
                "{name}:{function}:{line} | {message}"
            ),
        )
