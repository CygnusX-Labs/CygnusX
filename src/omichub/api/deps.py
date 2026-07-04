"""API 依赖注入"""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.services.totp_service import MfaService
from omichub.core.exceptions import AuthenticationError, AuthorizationError
from omichub.core.security import decode_token
from omichub.domain.user.value_objects import Role
from omichub.infrastructure.database.repositories import SqlAlchemyUserRepository
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


async def require_admin_totp(
    current_user_id: CurrentUserId,
    db: DbSession,
    x_totp_code: Annotated[str | None, Header(alias="X-TOTP-Code")] = None,
) -> str:
    """管理员敏感操作二次校验：请求头 X-TOTP-Code 须为最新的 6 位 TOTP 码。

    用法：在被保护端点的依赖里加 ``AdminTotpRequired``。
    - 非管理员 → 403
    - 管理员未开启 2FA → 403（强制先在个人中心开启）
    - 缺少/错误验证码 → 401
    返回 user_id 供端点继续使用。
    """
    repo = SqlAlchemyUserRepository(db)
    user = await repo.get_by_id(uuid.UUID(current_user_id))
    if not user:
        raise AuthenticationError("无效的访问令牌")
    if user.role != Role.ADMIN:
        raise AuthorizationError("仅管理员可执行此操作")
    if not user.is_2fa_enabled:
        raise AuthorizationError("请先在个人中心开启 2FA 后再执行敏感操作")
    mfa = MfaService(repo, db)
    if not x_totp_code or not mfa.verify_user_code(user, x_totp_code):
        raise AuthenticationError("二次验证码错误或已过期")
    return current_user_id


AdminTotpRequired = Annotated[str, Depends(require_admin_totp)]
