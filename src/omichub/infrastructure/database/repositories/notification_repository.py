"""通知提醒仓储"""

import uuid
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from omichub.infrastructure.database.models.notification import NotificationModel


class SqlAlchemyNotificationRepository:
    """通知提醒仓储的 SQLAlchemy 实现"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_for_user(self, user_id: uuid.UUID) -> list[NotificationModel]:
        """获取指定用户可见且未过期的通知，按创建时间倒序"""
        now = datetime.now().astimezone()
        stmt = (
            select(NotificationModel)
            .where(
                (NotificationModel.is_global.is_(True))
                | (NotificationModel.target_user_id == user_id)
            )
            .where(
                (NotificationModel.expires_at.is_(None))
                | (NotificationModel.expires_at > now)
            )
            .order_by(desc(NotificationModel.created_at))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, notification_id: uuid.UUID) -> NotificationModel | None:
        return await self.session.get(NotificationModel, notification_id)

    async def create(self, notification: NotificationModel) -> NotificationModel:
        self.session.add(notification)
        await self.session.flush()
        await self.session.refresh(notification)
        return notification

    async def mark_read(
        self, notification_id: uuid.UUID, user_id: uuid.UUID
    ) -> NotificationModel | None:
        notification = await self.get_by_id(notification_id)
        if notification is None:
            return None
        read_by = notification.read_by or []
        if str(user_id) not in [str(uid) for uid in read_by]:
            read_by.append(user_id)
            notification.read_by = read_by
            await self.session.flush()
            await self.session.refresh(notification)
        return notification

    async def delete(self, notification_id: uuid.UUID) -> bool:
        notification = await self.get_by_id(notification_id)
        if notification is None:
            return False
        await self.session.delete(notification)
        await self.session.flush()
        return True
