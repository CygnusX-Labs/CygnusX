"""用户域实体 - 聚合根"""

import uuid
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from omichub.domain.user.value_objects import Role, UserStatus


class Workspace(BaseModel):
    """工作空间 - 用户数据隔离边界"""

    id: UUID = Field(default_factory=uuid.uuid4)
    owner_id: UUID
    name: str
    storage_quota: int = 1024 * 1024 * 1024 * 10  # 默认 10GB
    used_storage: int = 0


class User(BaseModel):
    """用户聚合根"""

    id: UUID = Field(default_factory=uuid.uuid4)
    username: str
    email: str
    hashed_password: str
    role: Role = Role.USER
    status: UserStatus = UserStatus.ACTIVE
    workspace_id: UUID | None = None
    avatar_url: str | None = None
    preferences: dict = Field(default_factory=dict)
    last_login_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def is_admin(self) -> bool:
        return self.role == Role.ADMIN

    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE
