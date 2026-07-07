"""日志配置 - 基于 loguru 的统一日志管理

目标：
- 所有服务（web/beat/worker）使用统一日志格式与落盘路径。
- 同时输出可读文本、结构化 JSON、ERROR 独立日志。
- 支持通过环境变量控制服务名、日志级别与落盘目录。

环境变量：
- SERVICE_NAME: 服务标识，如 web/beat/worker，默认 app
- OMICHUB_LOG_LEVEL: 日志级别，默认 INFO
- OMICHUB_LOG_DIR: 日志根目录，默认 /app/logs；本地开发无法写入时自动回退到 ./logs
"""

import os
import sys
from pathlib import Path

from loguru import logger

from omichub.core.config import get_settings

# 容器内统一落盘路径；本地开发可覆盖
DEFAULT_LOG_DIR = "/app/logs"
# 本地开发回退路径（项目根目录下的 logs/）
FALLBACK_LOG_DIR = "logs"

SERVICE_NAME = os.getenv("SERVICE_NAME", "app")
LOG_LEVEL = os.getenv("OMICHUB_LOG_LEVEL", "INFO").upper()


def _resolve_log_dir() -> Path:
    """解析日志根目录。

    优先使用 OMICHUB_LOG_DIR 环境变量；未设置时使用 /app/logs。
    若 /app/logs 无法创建/写入（常见于本地开发），回退到当前工作目录的 logs/。
    """
    raw_dir = os.getenv("OMICHUB_LOG_DIR", DEFAULT_LOG_DIR)
    path = Path(raw_dir).resolve()
    try:
        path.mkdir(parents=True, exist_ok=True)
        # 测试是否可写
        test_file = path / ".write_test"
        test_file.write_text("")
        test_file.unlink()
        return path
    except OSError:
        fallback = Path(FALLBACK_LOG_DIR).resolve()
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def _text_format() -> str:
    """文本日志格式：包含服务名、时间、级别、位置信息。"""
    return (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
        "{extra[service]} | {name}:{function}:{line} | {message}"
    )


def _console_format() -> str:
    """控制台日志格式：带颜色，便于开发调试。"""
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{extra[service]}</cyan> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )


def setup_logging() -> None:
    """初始化日志配置。

    配置 4 个 sink：
    1. stdout：开发可读，带颜色。
    2. omichub.log：文本主日志，按 50 MB 轮转，保留 30 天。
    3. omichub.json.log：结构化 JSON，供后续 Loki/Promtail 抓取。
    4. error.log：仅 ERROR 及以上，便于快速定位故障。
    """
    settings = get_settings()
    # 每次初始化时重新读取环境变量，便于测试与运行时覆盖
    log_level = os.getenv("OMICHUB_LOG_LEVEL", LOG_LEVEL).upper()
    level = log_level if log_level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"} else "INFO"
    if not os.getenv("OMICHUB_LOG_LEVEL"):
        # 未显式设置时，开发环境允许 DEBUG
        level = "DEBUG" if settings.app_debug else "INFO"

    service_name = os.getenv("SERVICE_NAME", SERVICE_NAME)
    log_dir = _resolve_log_dir()

    # 移除默认 handler
    logger.remove()

    # 1. stdout
    logger.add(
        sys.stdout,
        level=level,
        format=_console_format(),
        colorize=True,
        backtrace=True,
        diagnose=settings.app_debug,
    )

    # 2. 主日志文件
    logger.add(
        log_dir / "omichub.log",
        level="INFO",
        rotation="50 MB",
        retention="30 days",
        compression="zip",
        format=_text_format(),
        enqueue=True,
        backtrace=True,
        diagnose=settings.app_debug,
    )

    # 3. JSON 结构化日志（供 Loki 抓取）
    logger.add(
        log_dir / "omichub.json.log",
        level="INFO",
        rotation="50 MB",
        retention="30 days",
        compression="zip",
        serialize=True,
        enqueue=True,
    )

    # 4. ERROR 级别单独抽离
    logger.add(
        log_dir / "error.log",
        level="ERROR",
        rotation="50 MB",
        retention="30 days",
        compression="zip",
        format=_text_format(),
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )

    # 绑定服务名到上下文
    logger.configure(extra={"service": service_name})


# 全局默认 logger；调用方优先使用 setup_logging() 重新初始化
#（web/beat/worker 的入口均已调用）。
setup_logging()
