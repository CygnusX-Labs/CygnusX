"""Cherry Studio 架构聊天系统 Pydantic DTO"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChatAttachment(BaseModel):
    """聊天附件（多模态消息用）"""

    type: str = Field("file", description="image 或 file")
    url: str
    name: str = ""
    mime_type: str = ""


class ChatStreamRequest(BaseModel):
    """流式聊天请求"""

    messages: list[dict[str, str]] = Field(..., description="消息列表 [{role, content}]")
    model_id: UUID | None = Field(None, description="使用的模型配置 ID（与 agent_id 至少传一个）")
    agent_id: str | None = Field(None, description="Agent ID：传入则走 Agent 调度中枢")
    session_id: str | None = Field(None, description="会话 ID，新建则传 null")
    assistant_id: str | None = Field(None, description="助手 ID")
    system_prompt: str | None = Field(None, description="自定义系统提示词")
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool = Field(True, description="是否流式返回")
    attachments: list[ChatAttachment] = Field(default_factory=list, description="当前用户消息的附件")
    enable_web_search: bool = Field(False, description="是否启用联网搜索")
    enable_code_execution: bool = Field(False, description="是否启用代码执行（仅前端 Pyodide，后端透传标记）")


class ChatMessageDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: str
    role: str
    content: str
    content_type: str = "text"
    status: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ChatSessionDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    title: str
    assistant_id: str | None = None
    model_id: UUID
    message_count: int
    status: str
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None = None


class ChatAssistantDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assistant_id: str
    name: str
    description: str | None = None
    system_prompt: str
    default_model_id: UUID | None = None
    default_temperature: float
    default_max_tokens: int
    icon: str
    color: str
    category: str
    is_builtin: bool
    is_active: bool
    is_default: bool = False


class CreateSessionRequest(BaseModel):
    title: str | None = "新对话"
    assistant_id: str | None = None
    model_id: UUID


class CreateAssistantRequest(BaseModel):
    assistant_id: str
    name: str
    description: str = ""
    system_prompt: str
    icon: str = "\U0001F916"
    color: str = "#4f8ef7"
    category: str = "general"
    default_temperature: float = 0.3
    default_max_tokens: int = 4096


class UpdateAssistantRequest(BaseModel):
    """更新助手请求"""

    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    default_temperature: float | None = None
    default_max_tokens: int | None = None
    icon: str | None = None
    color: str | None = None
    category: str | None = None
    is_active: bool | None = None
    is_default: bool | None = None
