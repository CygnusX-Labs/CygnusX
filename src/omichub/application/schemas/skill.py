"""Skill Pydantic DTO"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SkillDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    skill_id: str
    name: str
    description: str = ""
    prompt: str = ""
    tool_definition: dict[str, Any] | None = None
    icon: str = "\U0001f527"
    category: str = "general"
    is_active: bool = True
    is_builtin: bool = False
    version: str | None = None
    author: str | None = None
    source_type: str = "json"
    source_ref: str | None = None
    source_commit: str | None = None
    has_scripts: bool = False
    frontmatter: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class CreateSkillDTO(BaseModel):
    skill_id: str
    name: str
    description: str = ""
    prompt: str = ""
    tool_definition: dict[str, Any] | None = None
    icon: str = "\U0001f527"
    category: str = "general"
    is_active: bool = True


class UpdateSkillDTO(BaseModel):
    name: str | None = None
    description: str | None = None
    prompt: str | None = None
    tool_definition: dict[str, Any] | None = None
    icon: str | None = None
    category: str | None = None
    is_active: bool | None = None


# --- 导入层 DTO（Part A） ---


class SkillFileEntryDTO(BaseModel):
    path: str
    size: int
    kind: str  # skill_md | script | reference | asset | other
    content: str | None = None


class SkillImportPreviewDTO(BaseModel):
    """统一导入预览：四个入口解析后产出，确认后才入库"""

    skill_id: str
    name: str
    description: str = ""
    body: str = ""
    frontmatter: dict[str, Any] = {}
    icon: str = "\U0001f9e9"
    category: str = "general"
    version: str = ""
    author: str = ""
    source_type: str = "json"  # market | github | zip | json
    source_ref: str = ""
    source_commit: str = ""
    has_scripts: bool = False
    warnings: list[str] = []
    files: list[SkillFileEntryDTO] = []


class SkillImportConfirmDTO(BaseModel):
    """确认导入：回传预览内容（多 worker 无状态，不落服务端会话）"""

    preview: SkillImportPreviewDTO
    overwrite: bool = False  # skill_id 已存在时是否覆盖升级


class GithubImportRequest(BaseModel):
    url: str


class JsonImportRequest(BaseModel):
    text: str


class SkillMarketplaceItemDTO(BaseModel):
    """技能市场条目：随仓库发布的内置可安装技能"""

    skill_id: str
    name: str
    description: str = ""
    icon: str = "\U0001f9e9"
    category: str = "general"
    version: str = ""
    author: str = ""
    has_scripts: bool = False
    installed: bool = False


class SkillUpdateCheckDTO(BaseModel):
    has_update: bool
    current_version: str = ""
    current_commit: str = ""
    latest_commit: str = ""
    source_ref: str = ""
    message: str = ""
