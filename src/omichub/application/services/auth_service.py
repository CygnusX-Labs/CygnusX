"""认证应用服务"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.schemas.auth import UserRegisterRequest
from omichub.application.services.notification_service import NotificationService
from omichub.application.services.site_content_service import SiteContentService
from omichub.core.config import get_settings
from omichub.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
)
from omichub.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from omichub.domain.user.entities import User
from omichub.domain.user.repositories import IUserRepository
from omichub.domain.user.value_objects import UserStatus
from omichub.infrastructure.database.repositories.notification_repository import (
    SqlAlchemyNotificationRepository,
)

logger = logging.getLogger(__name__)


async def create_welcome_notification(db: AsyncSession, user_id: str) -> None:
    """为新用户创建一条定向欢迎通知：先引导前往「实验室知识库」，再提示联系管理员。

    管理员联系方式取自 data/OmicHub.yaml 的 registration.admin_contact；
    通知创建失败仅记录日志，不影响登录主流程。
    """
    try:
        admin_contact = (
            SiteContentService().get_content().registration.admin_contact.strip()
        )
        content = (
            "欢迎使用 OmicHub！建议先前往「实验室知识库」查阅组内标准操作规范与服务器使用指南；"
            "若仍有其他问题，可联系管理员获取帮助。"
        )
        if admin_contact:
            content = f"{content}（管理员联系方式：{admin_contact}）"
        repo = SqlAlchemyNotificationRepository(db)
        await NotificationService(repo).create(
            created_by=user_id,
            title="欢迎来到 OmicHub 🚀",
            content=content,
            level="info",
            is_global=False,
            target_user_id=user_id,
        )
    except Exception:
        logger.exception("为新用户 %s 创建欢迎通知失败", user_id)


class AuthService:
    """认证应用服务"""

    def __init__(self, user_repository: IUserRepository, db: AsyncSession):
        self.user_repo = user_repository
        self._db = db
        self.settings = get_settings()

    async def register(self, req: UserRegisterRequest) -> User:
        """用户注册"""
        # 检查用户名是否已存在
        existing_user = await self.user_repo.get_by_username(req.username)
        if existing_user:
            raise ConflictError(f"用户名 {req.username} 已存在")

        # 检查邮箱是否已存在
        existing_email = await self.user_repo.get_by_email(req.email)
        if existing_email:
            raise ConflictError(f"邮箱 {req.email} 已被注册")

        # 哈希密码
        hashed_pwd = hash_password(req.password)

        # 创建用户实体 — 默认 pending 状态，需管理员审批
        user = User(
            username=req.username,
            email=req.email,
            hashed_password=hashed_pwd
        )
        user.status = UserStatus.PENDING

        # 保存用户
        return await self.user_repo.save(user)

    async def login(self, username: str, password: str) -> tuple[str, str, User, bool]:
        """用户登录

        返回 (access_token, refresh_token, user, is_first_login)。
        is_first_login 在更新 last_login_at 之前判定（为 None 即首次）。
        """
        # 获取用户
        user = await self.user_repo.get_by_username(username)
        if not user:
            raise AuthenticationError("用户名或密码错误")

        # 验证密码
        if not verify_password(password, user.hashed_password):
            raise AuthenticationError("用户名或密码错误")

        # 验证用户状态
        if user.status != UserStatus.ACTIVE:
            raise AuthenticationError("账户未激活")

        # 首次登录判定：在更新 last_login_at 之前检查
        is_first_login = user.last_login_at is None

        # 更新最后登录时间
        user.last_login_at = datetime.now(UTC)
        await self.user_repo.save(user)

        # 首次登录：创建定向欢迎通知（失败不阻断登录）
        if is_first_login:
            await create_welcome_notification(self._db, str(user.id))

        # 创建令牌
        access_token = create_access_token(subject=str(user.id))
        refresh_token = create_refresh_token(subject=str(user.id))

        return access_token, refresh_token, user, is_first_login

    async def refresh_token(self, refresh_token: str) -> tuple[str, str]:
        """刷新访问令牌"""
        # 解码刷新令牌
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise AuthenticationError("无效的刷新令牌")

        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationError("令牌中缺少用户信息")

        # 验证用户存在
        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if not user:
            raise NotFoundError("用户不存在")

        # 创建新的访问令牌
        access_token = create_access_token(subject=user_id)
        new_refresh_token = create_refresh_token(subject=user_id)

        return access_token, new_refresh_token

    async def get_current_user(self, user_id: str) -> User:
        """获取当前用户"""
        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if not user:
            raise NotFoundError("用户不存在")

        return user
