"""ORM 模型

各域 ORM 表模型，对应 domain/entities.py 中的实体。
导入即注册到 Base.metadata，供 create_all / alembic 使用。
"""

from omichub.infrastructure.database.models.ai import ConversationModel, MessageModel
from omichub.infrastructure.database.models.ai_provider import AIProviderConfigModel
from omichub.infrastructure.database.models.chat import (
    ChatAssistantModel,
    ChatMessageModel,
    ChatSessionModel,
)
from omichub.infrastructure.database.models.cookie import (
    ConsumptionLogModel,
    CookieAccountModel,
    CookiePricingModel,
    CookieTransactionModel,
    LedgerEntryModel,
)
from omichub.infrastructure.database.models.mcp import MCPServerModel
from omichub.infrastructure.database.models.notification import NotificationModel
from omichub.infrastructure.database.models.sandbox import SandboxSessionModel
from omichub.infrastructure.database.models.site_settings import SiteSettingModel
from omichub.infrastructure.database.models.skill import SkillModel
from omichub.infrastructure.database.models.task import TaskModel
from omichub.infrastructure.database.models.user import UserModel, WorkspaceModel

__all__ = [
    "UserModel",
    "WorkspaceModel",
    "TaskModel",
    "CookieAccountModel",
    "CookieTransactionModel",
    "CookiePricingModel",
    "ConsumptionLogModel",
    "LedgerEntryModel",
    "ConversationModel",
    "MessageModel",
    "ChatSessionModel",
    "ChatMessageModel",
    "ChatAssistantModel",
    "AIProviderConfigModel",
    "MCPServerModel",
    "SandboxSessionModel",
    "NotificationModel",
    "SiteSettingModel",
    "SkillModel",
]
