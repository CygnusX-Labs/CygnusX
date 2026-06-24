"""用户域仓储接口"""

from uuid import UUID

from typing import Protocol

from omichub.domain.user.entities import User


class IUserRepository(Protocol):
    """用户仓储接口"""

    async def get_by_id(self, user_id: UUID) -> User | None: ...

    async def get_by_username(self, username: str) -> User | None: ...

    async def get_by_email(self, email: str) -> User | None: ...

    async def save(self, user: User) -> User: ...

    async def delete(self, user_id: UUID) -> bool: ...
