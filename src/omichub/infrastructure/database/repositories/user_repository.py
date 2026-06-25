"""用户仓储的 SQLAlchemy 实现"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omichub.domain.user.entities import User
from omichub.domain.user.repositories import IUserRepository
from omichub.domain.user.value_objects import Role, UserStatus
from omichub.infrastructure.database.models.user import UserModel


class SqlAlchemyUserRepository(IUserRepository):
    """用户仓储的 SQLAlchemy 实现"""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _to_domain(db_user: UserModel) -> User:
        """ORM 模型 → 领域实体"""
        return User(
            id=db_user.id,
            username=db_user.username,
            email=db_user.email,
            hashed_password=db_user.hashed_password,
            role=Role(db_user.role),
            status=UserStatus(db_user.status),
            workspace_id=db_user.workspace_id,
            avatar_url=db_user.avatar_url,
            preferences=db_user.preferences or {},
            last_login_at=db_user.last_login_at,
            created_at=db_user.created_at,
            updated_at=db_user.updated_at,
        )

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """根据 ID 获取用户"""
        stmt = select(UserModel).where(UserModel.id == user_id)
        result = await self.session.execute(stmt)
        db_user = result.scalar_one_or_none()
        return self._to_domain(db_user) if db_user else None

    async def get_by_username(self, username: str) -> User | None:
        """根据用户名获取用户"""
        stmt = select(UserModel).where(UserModel.username == username)
        result = await self.session.execute(stmt)
        db_user = result.scalar_one_or_none()
        return self._to_domain(db_user) if db_user else None

    async def get_by_email(self, email: str) -> User | None:
        """根据邮箱获取用户"""
        stmt = select(UserModel).where(UserModel.email == email)
        result = await self.session.execute(stmt)
        db_user = result.scalar_one_or_none()
        return self._to_domain(db_user) if db_user else None

    async def save(self, user: User) -> User:
        """保存用户（新建或更新）"""
        if user.id is not None:
            # 尝试更新已有用户
            stmt = select(UserModel).where(UserModel.id == user.id)
            result = await self.session.execute(stmt)
            db_user = result.scalar_one_or_none()
        else:
            db_user = None

        if db_user:
            # 更新现有用户
            db_user.username = user.username
            db_user.email = user.email
            db_user.hashed_password = user.hashed_password
            db_user.role = user.role.value if isinstance(user.role, Role) else user.role
            db_user.status = user.status.value if isinstance(user.status, UserStatus) else user.status
            db_user.workspace_id = user.workspace_id
            db_user.avatar_url = user.avatar_url
            db_user.preferences = user.preferences
            db_user.last_login_at = user.last_login_at
        else:
            # 创建新用户
            db_user = UserModel(
                id=user.id,
                username=user.username,
                email=user.email,
                hashed_password=user.hashed_password,
                role=user.role.value if isinstance(user.role, Role) else user.role,
                status=user.status.value if isinstance(user.status, UserStatus) else user.status,
                workspace_id=user.workspace_id,
                avatar_url=user.avatar_url,
                preferences=user.preferences,
                last_login_at=user.last_login_at,
            )
            self.session.add(db_user)

        await self.session.commit()
        await self.session.refresh(db_user)
        return self._to_domain(db_user)

    async def delete(self, user_id: uuid.UUID) -> bool:
        """删除用户"""
        stmt = select(UserModel).where(UserModel.id == user_id)
        result = await self.session.execute(stmt)
        db_user = result.scalar_one_or_none()

        if db_user:
            await self.session.delete(db_user)
            await self.session.commit()
            return True
        return False
