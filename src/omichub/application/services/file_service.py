"""File 应用服务"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid5

from omichub.application.schemas.file import DataFileDTO, FileListResponse
from omichub.core.config import get_settings
from omichub.domain.file.value_objects import FileType

# 用于从文件路径生成确定性 UUID 的命名空间
_FILE_NAMESPACE = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def _detect_file_type(filename: str) -> FileType:
    """根据扩展名猜测文件类型"""
    name_lower = filename.lower()
    if name_lower.endswith((".fastq", ".fastq.gz", ".fq", ".fq.gz")):
        return FileType.FASTQ
    if name_lower.endswith(".bam") or name_lower.endswith(".cram"):
        return FileType.BAM
    if name_lower.endswith(".vcf") or name_lower.endswith(".vcf.gz"):
        return FileType.VCF
    if name_lower.endswith((".csv", ".tsv", ".txt")) and "count" in name_lower:
        return FileType.COUNT_MATRIX
    if name_lower.endswith(".h5ad"):
        return FileType.H5AD
    if name_lower.endswith(".rds") or name_lower.endswith(".rdata"):
        return FileType.RDS
    if name_lower.endswith((".meta", "_metadata.csv", "_metadata.tsv", "_meta.txt")):
        return FileType.META
    if name_lower.endswith((".pdf", ".html", ".md", ".docx")):
        return FileType.REPORT
    if name_lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg")):
        return FileType.IMAGE
    return FileType.OTHER


class FileService:
    """文件应用服务 — 当前基于文件系统扫描提供最小列表能力"""

    def __init__(self, storage_path: str | None = None, upload_dir: str | None = None):
        settings = get_settings()
        self._upload_root = Path(storage_path or settings.storage_path) / (upload_dir or settings.upload_dir)

    def list_files(self, user_id: str) -> FileListResponse:
        """列出指定用户的上传文件"""
        user_dir = self._upload_root / user_id
        if not user_dir.exists():
            return FileListResponse(items=[], total=0)

        items: list[DataFileDTO] = []
        for path in sorted(user_dir.rglob("*")):
            if not path.is_file():
                continue
            rel_path = path.relative_to(user_dir)
            file_id = uuid5(_FILE_NAMESPACE, f"{user_id}/{rel_path.as_posix()}")
            items.append(
                DataFileDTO(
                    id=file_id,
                    original_name=path.name,
                    size=path.stat().st_size,
                    file_type=_detect_file_type(path.name),
                    created_at=path.stat().st_mtime,
                )
            )

        return FileListResponse(items=items, total=len(items))
