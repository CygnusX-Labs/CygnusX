"""AI 域值对象"""

from enum import Enum


class RoleType(str, Enum):
    """消息角色"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCallStatus(str, Enum):
    """工具调用状态"""

    PENDING = "pending"
    EXECUTING = "executing"
    SUCCESS = "success"
    FAILED = "failed"
