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
from omichub.core.exceptions import AuthorizationError, ConflictError
from omichub.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
)
from omichub.domain.user.entities import User
from omichub.domain.user.value_objects import Role, UserStatus
from omichub.infrastructure.database.repositories import SqlAlchemyUserRepository

router = APIRouter()


def get_auth_service(db: DbSession) -> AuthService:
    """获取认证服务实例"""
    return AuthService(SqlAlchemyUserRepository(db), db)


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    """用户登录（OAuth2 密码模式）"""
    access_token, refresh_token, _user, first_login = await auth_service.login(
        form_data.username, form_data.password
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=30 * 60,
        first_login=first_login,
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    req: UserRegisterRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    db: DbSession,
) -> UserResponse:
    """用户注册"""
    # 平台级开关：未开放注册时拒绝
    from omichub.application.services.site_settings_service import SiteSettingsService

    if not await SiteSettingsService(db).is_registration_enabled():
        raise AuthorizationError("平台已关闭注册，请联系管理员")

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
) -> TokenResponse:
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
) -> UserResponse:
    """获取当前登录用户信息"""
    user = await auth_service.get_current_user(current_user_id)
    return UserResponse.model_validate(user)


@router.get("/setup-required")
async def setup_required(db: DbSession) -> dict[str, bool]:
    """检查是否需要初始化第一个管理员账号"""
    repo = SqlAlchemyUserRepository(db)
    return {"setup_required": not await repo.has_any_admin()}


@router.post("/setup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def setup_first_admin(
    req: UserRegisterRequest,
    db: DbSession,
) -> TokenResponse:
    """创建第一个管理员账号（仅在系统无管理员时可用）"""
    repo = SqlAlchemyUserRepository(db)

    if await repo.has_any_admin():
        raise ConflictError("系统已存在管理员账号，请通过登录页访问")

    # 检查用户名/邮箱是否已被占用
    if await repo.get_by_username(req.username):
        raise ConflictError(f"用户名 {req.username} 已存在")
    if await repo.get_by_email(req.email):
        raise ConflictError(f"邮箱 {req.email} 已被注册")

    admin = User(
        username=req.username,
        email=req.email,
        hashed_password=hash_password(req.password),
        role=Role.ADMIN,
        status=UserStatus.ACTIVE,
    )
    created = await repo.save(admin)

    # 如果启用饼干系统，自动创建饼干账户
    if get_settings().enable_cookie_system:
        from omichub.application.services.cookie_service import CookieService

        cookie_service = CookieService(db)
        await cookie_service.get_or_create_account(created.id)

    # 首位管理员也是新用户：创建定向欢迎通知并触发迎新引导
    from omichub.application.services.auth_service import create_welcome_notification

    await create_welcome_notification(db, str(created.id))

    access_token = create_access_token(subject=str(created.id))
    refresh_token = create_refresh_token(subject=str(created.id))
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=30 * 60,
        first_login=True,
    )
