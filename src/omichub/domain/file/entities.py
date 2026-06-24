"""文件域实体 - 聚合根"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from omichub.domain.file.value_objects import FileType


class DataFile(BaseModel):
    """数据文件"""

    id: UUID
    path: str
    original_name: str
    size: int
    checksum: str = ""
    file_type: FileType = FileType.OTHER
    metadata: dict[str, Any] = {}
    created_at: datetime = Field(default_factory=datetime.now)


class ResultArchive(BaseModel):
    """结果归档"""

    id: UUID
    task_id: UUID
    archive_path: str
    size: int
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class Sample(BaseModel):
    """样本聚合根"""

    id: UUID
    name: str
    user_id: UUID
    species: str = ""
    tissue: str = ""
    description: str = ""
    metadata: dict[str, Any] = {}
    file_ids: list[UUID] = []
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
