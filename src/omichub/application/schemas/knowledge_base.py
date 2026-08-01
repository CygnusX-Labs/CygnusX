"""知识库资源管理 DTO。"""

from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeBaseDTO(BaseModel):
    id: str
    name: str
    description: str = ""
    show_in_lab: bool = True
    ai_searchable: bool = True
    is_enabled: bool = True
    doc_count: int = 0
    updated_at: datetime | None = None


class KnowledgeBaseCreateDTO(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    show_in_lab: bool = True
    ai_searchable: bool = True


class KnowledgeBaseUpdateDTO(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    show_in_lab: bool = True
    ai_searchable: bool = True
    is_enabled: bool = True


class KnowledgeBaseDocDTO(BaseModel):
    doc_id: str
    title: str
    category: str
    status: int
    updated_at: datetime | None = None
