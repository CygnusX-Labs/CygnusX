"""ORM 模型

各域 ORM 表模型，对应 domain/entities.py 中的实体。
导入即注册到 Base.metadata，供 create_all / alembic 使用。
"""

from omichub.infrastructure.database.models.agent import AgentTemplateModel
from omichub.infrastructure.database.models.ai import ConversationModel, MessageModel
from omichub.infrastructure.database.models.ai_provider import AIProviderConfigModel
from omichub.infrastructure.database.models.announcement import AnnouncementModel
from omichub.infrastructure.database.models.audit_log import AuditLogModel
from omichub.infrastructure.database.models.blast import (
    BlastDatabaseModel,
    BlastTaskModel,
)
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
from omichub.infrastructure.database.models.festival import FestivalClaimModel
from omichub.infrastructure.database.models.file import (
    DirectoryModel,
    FileRecordModel,
    SampleModel,
    UploadSessionModel,
)
from omichub.infrastructure.database.models.knowledge_audit_log import DocAuditLogModel
from omichub.infrastructure.database.models.knowledge_document import KbDocumentModel
from omichub.infrastructure.database.models.knowledge_editor import DocEditorModel
from omichub.infrastructure.database.models.knowledge_issue import KbIssueModel
from omichub.infrastructure.database.models.knowledge_revision import DocRevisionModel
from omichub.infrastructure.database.models.mcp import MCPServerModel
from omichub.infrastructure.database.models.notification import NotificationModel
from omichub.infrastructure.database.models.report import ReportFileModel, ReportModel
from omichub.infrastructure.database.models.sandbox import SandboxSessionModel
from omichub.infrastructure.database.models.site_settings import SiteSettingModel
from omichub.infrastructure.database.models.skill import SkillModel
from omichub.infrastructure.database.models.task import TaskModel
from omichub.infrastructure.database.models.terminal import TerminalSessionModel
from omichub.infrastructure.database.models.user import UserModel, WorkspaceModel

__all__ = [
    "AgentTemplateModel",
    "UserModel",
    "WorkspaceModel",
    "TaskModel",
    "CookieAccountModel",
    "CookieTransactionModel",
    "CookiePricingModel",
    "ConsumptionLogModel",
    "LedgerEntryModel",
    "FestivalClaimModel",
    "ConversationModel",
    "MessageModel",
    "ChatSessionModel",
    "ChatMessageModel",
    "ChatAssistantModel",
    "AIProviderConfigModel",
    "AnnouncementModel",
    "AuditLogModel",
    "BlastDatabaseModel",
    "BlastTaskModel",
    "KbDocumentModel",
    "DocRevisionModel",
    "DocEditorModel",
    "KbIssueModel",
    "DocAuditLogModel",
    "MCPServerModel",
    "ReportModel",
    "ReportFileModel",
    "SandboxSessionModel",
    "TerminalSessionModel",
    "NotificationModel",
    "SiteSettingModel",
    "SkillModel",
    "FileRecordModel",
    "UploadSessionModel",
    "SampleModel",
    "DirectoryModel",
]
