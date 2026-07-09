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

import logging
import os
import sys
from pathlib import Path

from loguru import logger

from omichub.core.config import get_settings

# 容器内统一落盘路径；本地开发可覆盖
DEFAULT_LOG_DIR = "/app/logs"
# 本地开发回退路径（项目根目录下的 logs/）
FALLBACK_LOG_DIR = "logs"
# 最后一层兜底，避免容器 bind mount 权限异常导致服务启动失败。
LAST_RESORT_LOG_DIR = "/tmp/omichub/logs"

SERVICE_NAME = os.getenv("SERVICE_NAME", "app")
LOG_LEVEL = os.getenv("OMICHUB_LOG_LEVEL", "INFO").upper()
LOG_ROTATION = os.getenv("OMICHUB_LOG_ROTATION", "50 MB")
LOG_RETENTION = os.getenv("OMICHUB_LOG_RETENTION", "30 days")
LOG_COMPRESSION = os.getenv("OMICHUB_LOG_COMPRESSION", "zip")


class InterceptHandler(logging.Handler):
    """将标准库 logging 转发到 loguru，避免日志分散到 root logger。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame = logging.currentframe()
        depth = 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _is_writable_log_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        test_file = path / ".write_test"
        test_file.write_text("")
        test_file.unlink()
        return True
    except OSError:
        return False


def _resolve_log_dir() -> Path:
    """解析日志根目录。

    优先使用 OMICHUB_LOG_DIR；不可写时回退到本地 logs/，再回退到 /tmp。
    这样 bind mount 权限异常时服务仍能启动，问题会通过 stdout 日志暴露。
    """
    raw_dir = os.getenv("OMICHUB_LOG_DIR", DEFAULT_LOG_DIR)
    candidates = [Path(raw_dir), Path(FALLBACK_LOG_DIR), Path(LAST_RESORT_LOG_DIR)]
    tried: set[Path] = set()

    for candidate in candidates:
        path = candidate.resolve()
        if path in tried:
            continue
        tried.add(path)
        if _is_writable_log_dir(path):
            return path

    # /tmp 理论上应始终可写；保留 fail-fast 以暴露极端环境问题。
    raise PermissionError(f"No writable log directory found: {', '.join(str(p) for p in tried)}")


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
    rotation = os.getenv("OMICHUB_LOG_ROTATION", LOG_ROTATION)
    retention = os.getenv("OMICHUB_LOG_RETENTION", LOG_RETENTION)
    compression = os.getenv("OMICHUB_LOG_COMPRESSION", LOG_COMPRESSION)

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
        rotation=rotation,
        retention=retention,
        compression=compression,
        format=_text_format(),
        enqueue=True,
        backtrace=True,
        diagnose=settings.app_debug,
    )

    # 3. JSON 结构化日志（供 Loki 抓取）
    logger.add(
        log_dir / "omichub.json.log",
        level="INFO",
        rotation=rotation,
        retention=retention,
        compression=compression,
        serialize=True,
        enqueue=True,
    )

    # 4. ERROR 级别单独抽离
    logger.add(
        log_dir / "error.log",
        level="ERROR",
        rotation=rotation,
        retention=retention,
        compression=compression,
        format=_text_format(),
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )

    # 绑定服务名到上下文
    logger.configure(extra={"service": service_name})

    # 兼容仍使用 logging.getLogger(...) 的旧代码和第三方库日志。
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)


# 全局默认 logger；调用方优先使用 setup_logging() 重新初始化
# （web/beat/worker 的入口均已调用）。
setup_logging()
