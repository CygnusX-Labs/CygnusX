"""认证路由 - 登录、注册、令牌刷新"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from omichub.api.deps import CurrentUserId, DbSession
from omichub.application.schemas.auth import (
    RefreshTokenRequest,
    TokenResponse,
    UserRegisterRequest,
)
from omichub.application.schemas.user import UserResponse
from omichub.application.services import AuthService
from omichub.core.config import get_settings
from omichub.infrastructure.database.repositories import SqlAlchemyUserRepository

router = APIRouter()


def get_auth_service(db: DbSession) -> AuthService:
    """获取认证服务实例"""
    return AuthService(SqlAlchemyUserRepository(db))


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    """用户登录（OAuth2 密码模式）"""
    access_token, refresh_token, _user = await auth_service.login(
        form_data.username, form_data.password
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=30 * 60,
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    req: UserRegisterRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    db: DbSession,
) -> UserResponse:
    """用户注册"""
    user = await auth_service.register(req)
    # 集成点#1: 注册时自动创建饼干账户 + 赠送初始饼干
    if get_settings().enable_cookie_system:
        from omichub.application.services.cookie_service import CookieService

        cookie_service = CookieService(db)
        await cookie_service.get_or_create_account(user.id)
    return UserResponse.model_validate(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    req: RefreshTokenRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    """刷新访问令牌"""
    access_token, refresh_token = await auth_service.refresh_token(req.refresh_token)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=30 * 60,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user_id: CurrentUserId,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    """获取当前登录用户信息"""
    user = await auth_service.get_current_user(current_user_id)
    return UserResponse.model_validate(user)
