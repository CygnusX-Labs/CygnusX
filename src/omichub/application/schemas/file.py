"""Pydantic v2 DTO"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from omichub.domain.file.value_objects import FileType


class DataFileDTO(BaseModel):
    """文件列表项 DTO"""

    id: UUID
    original_name: str
    size: int
    file_type: FileType = FileType.OTHER
    created_at: datetime


class FileListResponse(BaseModel):
    """文件列表响应"""

    items: list[DataFileDTO] = Field(default_factory=list)
    total: int = 0
