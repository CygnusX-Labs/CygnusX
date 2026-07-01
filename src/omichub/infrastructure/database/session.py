"""数据库会话管理 - 异步 SQLAlchemy"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from omichub.core.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """获取异步引擎（单例）"""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.app_debug,
            pool_pre_ping=True,
            # Celery 任务用 asyncio.run() 每次新建事件循环；QueuePool 会跨循环保留连接，
            # 复用时抛 "Future attached to a different loop"。NullPool 不保留连接、每次新建，
            # web(FastAPI 单循环) 与 celery(每任务新循环) 共用本单例引擎均安全。
            poolclass=NullPool,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """获取会话工厂（单例）"""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


# 别名，供 deps.py 导入
async_session_factory = get_session_factory


async def init_db() -> None:
    """初始化数据库连接"""
    engine = get_engine()
    async with engine.begin() as conn:
        # 开发环境自动建表（生产环境用 alembic 迁移）
        if not get_settings().is_production:
            from omichub.infrastructure.database.base import Base

            # 导入所有模型以注册到 metadata
            from omichub.infrastructure.database.models import (  # noqa: F401
                ai,
                cookie,
                mcp,
                sandbox,
                task,
                user,
            )

            await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """关闭数据库连接"""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def get_db() -> AsyncIterator[AsyncSession]:
    """获取数据库会话（FastAPI 依赖）"""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
