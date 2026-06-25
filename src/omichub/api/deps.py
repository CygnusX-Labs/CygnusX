"""API 依赖注入"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from omichub.core.exceptions import AuthenticationError
from omichub.core.security import decode_token
from omichub.infrastructure.database.session import get_session_factory

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_db() -> AsyncIterator[AsyncSession]:
    """获取数据库会话"""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user_id(token: Annotated[str, Depends(oauth2_scheme)]) -> str:
    """从 JWT Token 中解析当前用户 ID"""
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise AuthenticationError("无效的访问令牌")
    user_id = payload.get("sub")
    if user_id is None:
        raise AuthenticationError("令牌中缺少用户信息")
    return str(user_id)


CurrentUserId = Annotated[str, Depends(get_current_user_id)]
