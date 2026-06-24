"""文件域仓储接口"""

from typing import Protocol
from uuid import UUID

from omichub.domain.file.entities import DataFile, ResultArchive, Sample


class ISampleRepository(Protocol):
    """样本仓储接口"""

    async def get_by_id(self, sample_id: UUID) -> Sample | None: ...

    async def list_by_user(self, user_id: UUID) -> list[Sample]: ...

    async def save(self, sample: Sample) -> Sample: ...

    async def delete(self, sample_id: UUID) -> bool: ...


class IFileRepository(Protocol):
    """文件仓储接口"""

    async def get_by_id(self, file_id: UUID) -> DataFile | None: ...

    async def save(self, file: DataFile) -> DataFile: ...

    async def delete(self, file_id: UUID) -> bool: ...

    async def calculate_checksum(self, path: str) -> str: ...


class IResultArchiveRepository(Protocol):
    """结果归档仓储接口"""

    async def get_by_task(self, task_id: UUID) -> ResultArchive | None: ...

    async def save(self, archive: ResultArchive) -> ResultArchive: ...

    async def cleanup_expired(self) -> int: ...
