"""文件应用服务 — DB 文件记录 + 分块上传 + 配额控制

落盘规范（统一由 StoragePathFactory 生成）：
  原始上传：{data_root}/users/{user_id}/inbox/{filename}
  分析输出：{data_root}/users/{user_id}/projects/{project}/runs/{analysis-time}/output/...
  下载产物：{data_root}/users/{user_id}/downloads/{filename}
  分片临时：{data_root}/system/.tmp/{upload_id}/{index}
"""

from __future__ import annotations

import fnmatch
import re
import uuid
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.schemas.file import (
    DataFileDTO,
    DirectoryCreateRequest,
    DirectoryDTO,
    DirectorySearchDTO,
    FileListResponse,
    FilePickerItemDTO,
    QuotaResponse,
    SampleCreateRequest,
    SampleDTO,
    SampleListResponse,
    SyncResponse,
    UploadChunkResponse,
    UploadInitRequest,
    UploadInitResponse,
    UploadMergeResponse,
)
from omichub.core.exceptions import (
    AuthorizationError,
    NotFoundError,
    ValidationError,
)
from omichub.domain.file.entities import DataFile, Sample
from omichub.domain.file.value_objects import FileType
from omichub.infrastructure.database.repositories import (
    DirectoryRepositoryImpl,
    FileRepositoryImpl,
    SampleRepositoryImpl,
    UploadSessionRepositoryImpl,
)
from omichub.infrastructure.database.repositories.user_repository import (
    SqlAlchemyUserRepository,
)
from omichub.infrastructure.storage.path_factory import get_path_factory

# 默认分片大小（客户端未传时兜底）
DEFAULT_CHUNK_SIZE = 5 * 1024 * 1024  # 5 MiB

# sync_user_files 跳过的系统内部目录（这些目录下的文件由各自服务登记，
# 不应作为普通 file_records 出现在"数据管理"视图里，否则会污染目录树）。
# 匹配规则：相对用户根的第一段目录名命中即跳过。
_SYNC_SKIP_USER_TOP_DIRS: frozenset[str] = frozenset(
    {
        "tasks",        # 任务产物（各工具/流程自行登记）
        "projects",     # 项目运行结果（由 pipeline/studio 服务登记）
        "temp",         # 临时文件
        "results",      # 旧版任务结果（legacy）
        "raw",          # 旧版上传目录（legacy，迁移后应清空）
    }
)
# workspace/ 下需要跳过的子目录（workspace/ 根允许登记，但 chat-uploads/ 由聊天服务登记）
_SYNC_SKIP_WORKSPACE_SUBDIRS: frozenset[str] = frozenset(
    {
        "chat-uploads",
        "sandbox",
    }
)

# 系统默认目录：用户首次访问时懒初始化，锁定不可删除/重命名
SYSTEM_DIRECTORIES: tuple[str, ...] = (
    "inbox",
    "projects",
    "raw_data",
    "workspace",
    "downloads",
    "temp",
)

_DEDUPE_SUFFIX_RE = re.compile(r"^(?P<stem>.+)_[0-9a-f]{8}$", re.IGNORECASE)
_LEGACY_GZIP_DEDUPE_RE = re.compile(
    r"^(?P<stem>.+\.(?:fastq|fq|vcf|gff|gtf|fa|fasta|fna))_[0-9a-f]{8}(?P<suffix>\.gz)$",
    re.IGNORECASE,
)
_COMPOUND_GZIP_SUFFIX_PARENTS = {
    ".fastq",
    ".fq",
    ".vcf",
    ".gff",
    ".gtf",
    ".fa",
    ".fasta",
    ".fna",
    ".tar",
}


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


def _split_display_suffix(filename: str) -> tuple[str, str]:
    """拆分文件名 stem/suffix，保留常见双后缀如 .fastq.gz。"""
    suffixes = Path(filename).suffixes
    if (
        len(suffixes) >= 2
        and suffixes[-1].lower() == ".gz"
        and suffixes[-2].lower() in _COMPOUND_GZIP_SUFFIX_PARENTS
    ):
        suffix = "".join(suffixes[-2:])
    elif suffixes:
        suffix = suffixes[-1]
    else:
        suffix = ""

    stem = filename[: -len(suffix)] if suffix else filename
    return stem, suffix


def _append_dedupe_suffix(path: Path, token: str) -> Path:
    """生成去重后的物理文件名，同时尽量保留复合扩展名。"""
    stem, suffix = _split_display_suffix(path.name)
    return path.with_name(f"{stem}_{token}{suffix}")


def canonical_original_name(filename: str) -> str:
    """把系统生成的短 UUID 去重后缀从展示名里剥掉。

    只处理本服务生成的 8 位十六进制后缀，避免误伤常见测序 lane 编号
    （如 _001）或用户自带数字。
    """
    name = Path(filename).name

    legacy_match = _LEGACY_GZIP_DEDUPE_RE.match(name)
    if legacy_match:
        return f"{legacy_match.group('stem')}{legacy_match.group('suffix')}"

    stem, suffix = _split_display_suffix(name)
    match = _DEDUPE_SUFFIX_RE.match(stem)
    if match:
        return f"{match.group('stem')}{suffix}"
    return name


async def ensure_directory_chain(session: AsyncSession, user_id: UUID, path: str) -> None:
    """确保 path 及其各级父目录在 user_directories 中存在（幂等）。

    path 形如 ``raw_data/PRJNA1259417``。逐段创建缺失的 Directory 记录；系统默认目录段
    （inbox/projects/raw_data/workspace/temp）标记 is_system=True，其余为用户数据目录。
    供文件同步与下载产物登记共用。
    """
    repo = DirectoryRepositoryImpl(session)
    parts = [p for p in path.split("/") if p and p not in ("", ".", "..")]
    parent: str | None = None
    cumulative: list[str] = []
    for p in parts:
        cumulative.append(p)
        cur_path = "/".join(cumulative)
        if await repo.get_by_path(user_id, cur_path) is not None:
            parent = cur_path
            continue
        await repo.save(
            Directory(
                id=uuid.uuid4(),
                user_id=user_id,
                path=cur_path,
                name=p,
                parent_path=parent,
                # 仅顶层系统默认目录标 is_system；同名嵌套子目录（如 downloads/raw_data）不算
                is_system=(p in SYSTEM_DIRECTORIES and parent is None),
            )
        )
        parent = cur_path


class FileService:
    """文件应用服务 — 配额校验、分块上传、断点续传、生命周期路径"""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._files = FileRepositoryImpl(session)
        self._samples = SampleRepositoryImpl(session)
        self._dirs = DirectoryRepositoryImpl(session)
        self._users = SqlAlchemyUserRepository(session)
        # 统一路径工厂：所有磁盘路径由此生成，禁止在本类中再硬编码拼接
        self._factory = get_path_factory()

    # ------------------------------------------------------------------
    # 路径工具（统一委托给 StoragePathFactory）
    # ------------------------------------------------------------------
    @property
    def _storage_root(self) -> Path:
        """向后兼容：等价于 path_factory.data_root。"""
        return self._factory.data_root

    def user_root(self, user_id: UUID) -> Path:
        """用户存储根目录：``{data_root}/users/{user_id}/``。"""
        return self._factory.user_root(str(user_id))

    @staticmethod
    def validate_workspace_path(path: str | None) -> str:
        """校验并规范工作区相对路径，显式拒绝绝对路径与 ``..``。"""
        raw = (path or "").strip().replace("\\", "/")
        if not raw or raw == ".":
            return ""
        if raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
            raise PermissionError("路径越权：仅允许当前用户工作区内的相对路径")
        parts = raw.split("/")
        if ".." in parts:
            raise PermissionError("路径越权：禁止使用 .. 访问工作区外目录")
        return "/".join(part for part in parts if part not in ("", "."))

    @staticmethod
    def _workspace_relative_path(storage_path: str, user_id: UUID) -> str:
        prefix = Path("users") / str(user_id)
        path = Path(storage_path)
        try:
            return path.relative_to(prefix).as_posix()
        except ValueError:
            return path.name

    def _resolve_abs(self, storage_path: str) -> Path:
        """storage_path 为相对 data_root 的路径；拼成绝对路径并做路径遍历校验。

        拒绝绝对路径输入，解析后必须仍位于 data_root 内，否则视为越权。
        """
        if not storage_path:
            raise NotFoundError("文件路径不能为空")
        if Path(storage_path).is_absolute():
            raise AuthorizationError("非法文件路径：禁止绝对路径")
        abs_path = (self._factory.data_root / storage_path).resolve()
        if not self._factory.is_within_root(abs_path):
            raise AuthorizationError("非法文件路径：路径越权")
        return abs_path

    def _normalize_directory(self, directory: str | None) -> str:
        """规整目录路径：去首尾斜杠、禁绝对路径越权"""
        if not directory:
            return ""
        d = directory.strip().strip("/")
        # 防止 .. 越权逃逸用户目录
        parts = [p for p in d.split("/") if p not in ("", ".", "..")]
        return "/".join(parts)

    def _inbox_subdir(self, user_id: UUID, directory: str) -> Path:
        """用户 inbox/ 下的指定子目录（自动创建）。

        ``directory`` 是相对 inbox 的路径；空串表示 inbox 根。兼容历史调用方
        传入 ``"inbox"`` 或 ``"inbox/xxx"`` 前缀的情况。
        """
        normalized_directory = self._normalize_directory(directory)
        if normalized_directory == "inbox":
            normalized_directory = ""
        elif normalized_directory.startswith("inbox/"):
            normalized_directory = normalized_directory.removeprefix("inbox/")
        base = self._factory.inbox_dir(str(user_id))
        target = base / normalized_directory if normalized_directory else base
        target.mkdir(parents=True, exist_ok=True)
        return target

    # 向后兼容：外部若还有 ``_raw_subdir`` / ``user_raw_dir`` 调用，转发到新方法
    def _raw_subdir(self, user_id: UUID, directory: str) -> Path:
        return self._inbox_subdir(user_id, directory)

    def user_raw_dir(self, user_id: UUID) -> Path:
        """用户上传入口 inbox/（历史方法名保留，仅做转发）。"""
        d = self._factory.inbox_dir(str(user_id))
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------
    # 列表 / 配额
    # ------------------------------------------------------------------
    async def list_files(
        self, user_id: UUID, directory: str | None = None, source: str | None = None
    ) -> FileListResponse:
        items = await self._files.list_by_user(user_id, status="active", directory=directory)
        if source:
            items = [f for f in items if getattr(f, "source", None) == source]
        dtos = [
            DataFileDTO(
                id=f.id,
                original_name=f.original_name,
                size=f.size,
                file_type=f.file_type,
                status=f.status,
                checksum=f.checksum,
                directory=f.directory,
                path=self._workspace_relative_path(f.path, user_id),
                created_at=f.created_at,
                modified_at=f.updated_at,
            )
            for f in items
        ]
        return FileListResponse(items=dtos, total=len(dtos))

    async def get_file_tree(self, user_id: UUID) -> dict:
        """聚合视图：按来源分组返回用户所有活跃文件。"""
        items = await self._files.list_by_user(user_id, status="active")
        tree: dict[str, list] = {}
        for f in items:
            src = getattr(f, "source", None) or "upload"
            tree.setdefault(src, []).append(
                {
                    "id": str(f.id),
                    "name": f.original_name,
                    "size": f.size,
                    "file_type": f.file_type.value if hasattr(f.file_type, "value") else str(f.file_type),
                    "directory": f.directory,
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                }
            )
        return {"user_id": str(user_id), "groups": tree, "total": len(items)}

    async def list_workspace_files(
        self,
        user_id: UUID,
        path: str | None = None,
        pattern: str | None = None,
    ) -> dict[str, object]:
        """列出工作区目录的直接子项，文件数据来自统一文件索引。"""
        directory = self.validate_workspace_path(path)
        normalized_pattern = (pattern or "").strip()
        prefix_parts = tuple(Path(directory).parts) if directory else ()
        indexed_files = await self._files.list_by_user(user_id, status="active")
        indexed_directories = await self._dirs.list_by_user(user_id)

        folders: dict[str, dict[str, object]] = {}
        files: list[dict[str, object]] = []
        for file in indexed_files:
            relative_path = self._workspace_relative_path(file.path, user_id)
            relative_parts = tuple(Path(relative_path).parts)
            if relative_parts[: len(prefix_parts)] != prefix_parts:
                continue
            remainder = relative_parts[len(prefix_parts) :]
            if not remainder:
                continue
            if len(remainder) > 1:
                folder_name = remainder[0]
                folder_path = "/".join((*prefix_parts, folder_name))
                existing = folders.get(folder_path)
                if existing is None or str(existing["modified_at"]) < file.updated_at.isoformat():
                    folders[folder_path] = {
                        "file_id": None,
                        "name": folder_name,
                        "type": "folder",
                        "size": None,
                        "relative_path": folder_path,
                        "modified_at": file.updated_at.isoformat(),
                    }
                continue
            files.append(
                {
                    "file_id": str(file.id),
                    "name": file.original_name,
                    "type": "file",
                    "file_type": file.file_type.value
                    if hasattr(file.file_type, "value")
                    else str(file.file_type),
                    "size": file.size,
                    "relative_path": relative_path,
                    "modified_at": file.updated_at.isoformat(),
                }
            )

        for child in indexed_directories:
            child_parts = tuple(Path(child.path).parts)
            if child_parts[: len(prefix_parts)] != prefix_parts:
                continue
            remainder = child_parts[len(prefix_parts) :]
            if len(remainder) != 1:
                continue
            folders.setdefault(
                child.path,
                {
                    "file_id": None,
                    "name": child.name,
                    "type": "folder",
                    "size": None,
                    "relative_path": child.path,
                    "modified_at": child.updated_at.isoformat(),
                },
            )

        items = [*folders.values(), *files]
        if normalized_pattern:
            items = [
                item
                for item in items
                if fnmatch.fnmatchcase(str(item["name"]).casefold(), normalized_pattern.casefold())
            ]

        items.sort(key=lambda item: (item["type"] != "folder", str(item["name"]).casefold()))
        return {
            "path": directory,
            "pattern": normalized_pattern or None,
            "items": items,
            "total": len(items),
        }

    async def search_files(
        self, user_id: UUID, query: str = "", limit: int = 50
    ) -> FileListResponse:
        """在当前用户根目录的已索引文件中递归搜索。"""
        root = self.user_root(user_id)
        if root.exists() and not root.is_dir():
            raise PermissionError("用户工作区根目录不可访问")
        if root.exists() and not root.stat().st_mode & 0o444:
            raise PermissionError("用户工作区根目录不可读")

        normalized_query = query.replace("\\", "/").strip("/").casefold()
        items = await self._files.list_by_user(user_id, status="active")
        directories = await self._dirs.list_by_user(user_id)
        excluded_parts = {".git", "node_modules", "__pycache__"}
        matches = []
        for file in items:
            relative_path = self._workspace_relative_path(file.path, user_id)
            parts = set(Path(relative_path).parts)
            if parts & excluded_parts:
                continue
            if normalized_query and normalized_query not in relative_path.casefold():
                continue
            matches.append(
                DataFileDTO(
                    id=file.id,
                    original_name=file.original_name,
                    size=file.size,
                    file_type=file.file_type,
                    status=file.status,
                    checksum=file.checksum,
                    directory=file.directory,
                    path=relative_path,
                    created_at=file.created_at,
                    modified_at=file.updated_at,
                )
            )
            if len(matches) >= limit:
                break
        directory_matches = [
            DirectorySearchDTO(
                path=directory.path,
                name=directory.name,
                parent_path=directory.parent_path,
                is_system=directory.is_system,
            )
            for directory in directories
            if not normalized_query or normalized_query in directory.path.casefold()
        ][:limit]
        return FileListResponse(
            items=matches,
            directories=directory_matches,
            total=len(matches) + len(directory_matches),
        )

    async def get_quota(self, user_id: UUID) -> QuotaResponse:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("用户不存在")
        total = user.storage_quota
        used = user.used_storage
        percent = round(used / total * 100, 2) if total > 0 else 100.0
        return QuotaResponse(used=used, total=total, percent=percent)

    # ------------------------------------------------------------------
    # 分块上传（委托给 UploadService）
    # ------------------------------------------------------------------
    @property
    def _upload_svc(self):
        """懒加载上传服务，避免循环导入。"""
        if not hasattr(self, "__upload_svc"):
            from omichub.application.services.upload_service import UploadService

            object.__setattr__(self, "_FileService__upload_svc", UploadService(self._session))
        return self.__upload_svc

    async def init_upload(self, user_id: UUID, req: UploadInitRequest) -> UploadInitResponse:
        return await self._upload_svc.init_upload(user_id, req)

    async def save_chunk(
        self, user_id: UUID, upload_id: UUID, index: int, chunk_bytes: bytes, md5: str
    ) -> UploadChunkResponse:
        return await self._upload_svc.save_chunk(user_id, upload_id, index, chunk_bytes, md5)

    async def merge_upload(self, user_id: UUID, upload_id: UUID) -> UploadMergeResponse:
        return await self._upload_svc.merge_upload(user_id, upload_id)

    async def cancel_upload(self, user_id: UUID, upload_id: UUID) -> bool:
        return await self._upload_svc.cancel_upload(user_id, upload_id)

    # ------------------------------------------------------------------
    # 下载 / 删除
    # ------------------------------------------------------------------
    async def get_file_path(self, user_id: UUID, file_id: UUID) -> Path:
        """获取文件绝对路径（下载用，强制归属校验）"""
        file = await self._files.get_by_id(user_id, file_id)
        if file is None:
            raise NotFoundError("文件不存在")
        abs_path = self._resolve_abs(file.path)
        if not abs_path.exists():
            raise NotFoundError("文件已被移除")
        return abs_path

    async def delete_file(self, user_id: UUID, file_id: UUID) -> bool:
        file = await self._files.get_by_id(user_id, file_id)
        if file is None:
            raise NotFoundError("文件不存在")
        # 删盘 + 删记录
        abs_path = self._resolve_abs(file.path)
        if abs_path.exists():
            abs_path.unlink()
        await self._files.delete(user_id, file_id)
        # 扣减配额（防负）
        user = await self._users.get_by_id(user_id)
        if user is not None:
            delta = -min(file.size, user.used_storage)
            if delta != 0:
                await self._users.add_used_storage(user_id, delta)
        await self._session.commit()
        return True

    async def move_file(self, user_id: UUID, file_id: UUID, directory: str) -> DataFileDTO:
        """移动文件到指定目录（改 storage_path + directory 字段 + 物理移动）"""
        file = await self._files.get_by_id(user_id, file_id)
        if file is None:
            raise NotFoundError("文件不存在")
        directory = self._normalize_directory(directory)
        old_abs = self._resolve_abs(file.path)
        new_subdir = self._inbox_subdir(user_id, directory)
        new_abs = new_subdir / old_abs.name
        if new_abs.exists() and new_abs != old_abs:
            # 目标已存在同名：追加短 uuid
            new_abs = _append_dedupe_suffix(new_abs, uuid.uuid4().hex[:8])
        if old_abs.exists() and new_abs != old_abs:
            shutil.move(str(old_abs), str(new_abs))
        file.directory = directory
        file.path = self._factory.relative_to_root(new_abs)
        saved = await self._files.save(file)
        await self._session.commit()
        return DataFileDTO(
            id=saved.id,
            original_name=saved.original_name,
            size=saved.size,
            file_type=saved.file_type,
            status=saved.status,
            checksum=saved.checksum,
            directory=saved.directory,
            path=self._workspace_relative_path(saved.path, user_id),
            created_at=saved.created_at,
            modified_at=saved.updated_at,
        )

    def _ensure_user_system_subdir(self, user_id: UUID, name: str) -> Path:
        """确保用户顶层系统子目录（inbox/projects/raw_data/workspace/downloads/temp）存在。"""
        mapping = {
            "inbox": self._factory.inbox_dir(str(user_id)),
            "projects": self._factory.projects_dir(str(user_id)),
            "raw_data": self._factory.user_root(str(user_id)) / "raw_data",
            "workspace": self._factory.workspace_dir(str(user_id)),
            "downloads": self._factory.downloads_dir(str(user_id)),
            "temp": self._factory.user_root(str(user_id)) / "temp",
        }
        d = mapping.get(name)
        if d is None:
            d = self._factory.user_root(str(user_id)) / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------
    # 用户目录 CRUD（委托给 DirectoryService）
    # ------------------------------------------------------------------
    @property
    def _dir_svc(self):
        """懒加载目录服务，避免循环导入。"""
        if not hasattr(self, "_FileService__dir_svc"):
            from omichub.application.services.directory_service import DirectoryService

            object.__setattr__(self, "_FileService__dir_svc", DirectoryService(self._session))
        return self._FileService__dir_svc

    async def ensure_default_directories(self, user_id: UUID) -> None:
        return await self._dir_svc.ensure_default_directories(user_id)

    async def list_directories(self, user_id: UUID) -> list[DirectoryDTO]:
        return await self._dir_svc.list_directories(user_id)

    async def create_directory(self, user_id: UUID, req: DirectoryCreateRequest) -> DirectoryDTO:
        return await self._dir_svc.create_directory(user_id, req)

    async def delete_directory(self, user_id: UUID, path: str) -> bool:
        return await self._dir_svc.delete_directory(user_id, path)

    async def list_files_for_picker(
        self, user_id: UUID, directory: str | None = None, file_type: str | None = None
    ) -> list[FilePickerItemDTO]:
        """供分析文件选择器：返回文件 + 绝对路径"""
        items = await self._files.list_by_user(user_id, status="active", directory=directory)
        result = [
            FilePickerItemDTO(
                id=f.id,
                original_name=f.original_name,
                size=f.size,
                file_type=f.file_type,
                directory=f.directory,
                abs_path=str(self._resolve_abs(f.path)),
            )
            for f in items
            if file_type is None or f.file_type.value == file_type
        ]
        return result

    # ------------------------------------------------------------------
    # 文件同步（磁盘 ↔ file_records）
    # ------------------------------------------------------------------
    async def sync_user_files(self, user_id: UUID) -> SyncResponse:
        """对账用户目录与 file_records，并重算配额。

        用于：手动放入的文件、旧任务未登记的产物，以及用户从磁盘直接删除文件后的
        页面自愈。幂等：同 storage_path 已存在则跳过；active 记录的物理文件不存在则
        删除记录；历史去重后缀显示名会在同步时修正。
        """
        from sqlalchemy import select

        from omichub.infrastructure.database.models.file import FileRecordModel

        user_root = self.user_root(user_id)

        res = await self._session.execute(
            select(FileRecordModel).where(
                FileRecordModel.user_id == user_id,
                FileRecordModel.status == "active",
            )
        )
        existing_paths: set[str] = set()
        removed = 0
        removed_size = 0
        renamed = 0

        for model in res.scalars().all():
            abs_path = self._resolve_abs(model.storage_path)
            if not abs_path.is_file():
                await self._files.delete(user_id, model.id)
                removed += 1
                removed_size += model.size or 0
                continue

            existing_paths.add(model.storage_path)
            physical_name = abs_path.name
            if model.original_name == physical_name:
                clean_name = canonical_original_name(physical_name)
                if clean_name != model.original_name:
                    model.original_name = clean_name
                    model.file_type = _detect_file_type(clean_name).value
                    renamed += 1

        added = 0
        added_size = 0
        if user_root.exists():
            for directory_path in user_root.rglob("*"):
                if not directory_path.is_dir():
                    continue
                relative_parts = directory_path.relative_to(user_root).parts
                if self._should_skip_sync_path(relative_parts):
                    continue
                relative_directory = "/".join(relative_parts)
                if relative_directory:
                    await ensure_directory_chain(self._session, user_id, relative_directory)
            for f in user_root.rglob("*"):
                if not f.is_file():
                    continue
                rel_user_parts = f.relative_to(user_root).parts
                # 跳过隐藏目录/文件（.tmp 上传分片、.qoder 等 IDE 元数据）
                if any(part.startswith(".") for part in rel_user_parts):
                    continue
                # 跳过系统内部目录下的文件（tasks/projects/... 由各自服务登记）
                if self._should_skip_sync_path(rel_user_parts):
                    continue
                try:
                    rel = self._factory.relative_to_root(f)
                except ValueError:
                    continue
                if rel in existing_paths:
                    continue
                rel_user = Path(*rel_user_parts) if rel_user_parts else None
                directory = self._derive_directory(rel_user)
                if directory:
                    await ensure_directory_chain(self._session, user_id, directory)
                try:
                    size = f.stat().st_size
                except OSError:
                    continue
                original_name = canonical_original_name(f.name)
                record = DataFile(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    path=rel,
                    original_name=original_name,
                    size=size,
                    checksum="",
                    file_type=_detect_file_type(original_name),
                    status="active",
                    directory=directory,
                )
                await self._files.save(record)
                existing_paths.add(rel)
                added += 1
                added_size += size

        # 重算配额，修正历史漂移（下载/手动放入/手工删除未计入的部分）
        await self._users.recompute_used_storage(user_id)
        await self._session.commit()
        return SyncResponse(
            added=added,
            added_size=added_size,
            removed=removed,
            removed_size=removed_size,
            renamed=renamed,
        )

    @staticmethod
    def _derive_directory(rel_user: Path | None) -> str:
        """从「相对用户根的路径」推导 logical directory。

        - ``inbox/myproj/x.fq`` → ``myproj``（上传布局，剥离 inbox/ 前缀）
        - ``inbox/x.fq`` → ``""``（直接落在 inbox 根，归入用户根目录视图）
        - ``raw/myproj/x.fq`` → ``myproj``（兼容 legacy 上传布局，剥离 raw/）
        - ``raw_data/PRJNA1259417/x.fq`` → ``raw_data/PRJNA1259417``（下载布局，保留）
        - ``downloads/x.fq`` → ``downloads``（下载产物）
        - 直接在用户根下的文件 → ``""``
        """
        if rel_user is None:
            return ""
        parts = list(rel_user.parts)[:-1]  # 去掉文件名
        if not parts:
            return ""
        # 剥离上传暂存目录前缀（inbox 是当前，raw 是 legacy）
        if parts and parts[0] in ("inbox", "raw"):
            parts = parts[1:]
        parts = [p for p in parts if p and p not in (".", "..")]
        return "/".join(parts)

    @staticmethod
    def _should_skip_sync_path(parts: tuple[str, ...]) -> bool:
        """判断该路径是否属于系统内部目录，sync 时应跳过（不登记为普通文件记录）。

        - 顶层命中 _SYNC_SKIP_USER_TOP_DIRS（tasks/projects/temp/results/raw）→ 跳过
        - workspace/{chat-uploads,sandbox,...} → 跳过；workspace/ 根下的文件允许登记
        - 隐藏目录（以 . 开头）→ 跳过
        """
        if not parts:
            return False
        top = parts[0]
        if top.startswith("."):
            return True
        if top in _SYNC_SKIP_USER_TOP_DIRS:
            return True
        if top == "workspace" and len(parts) >= 2 and parts[1] in _SYNC_SKIP_WORKSPACE_SUBDIRS:
            return True
        return False

    # ------------------------------------------------------------------
    # 样本（供流程引擎读取文件路径）
    # ------------------------------------------------------------------
    async def list_samples(self, user_id: UUID) -> SampleListResponse:
        items = await self._samples.list_by_user(user_id)
        dtos = [
            SampleDTO(
                id=s.id,
                name=s.name,
                species=s.species,
                tissue=s.tissue,
                description=s.description,
                metadata=s.metadata,
                file_ids=s.file_ids,
                created_at=s.created_at,
            )
            for s in items
        ]
        return SampleListResponse(items=dtos, total=len(dtos))

    async def create_sample(self, user_id: UUID, req: SampleCreateRequest) -> SampleDTO:
        # 校验 file_ids 归属
        for fid in req.file_ids:
            if await self._files.get_by_id(user_id, fid) is None:
                raise NotFoundError(f"文件不存在或无权访问：{fid}")
        sample = Sample(
            id=uuid.uuid4(),
            user_id=user_id,
            name=req.name,
            species=req.species,
            tissue=req.tissue,
            description=req.description,
            metadata=req.metadata,
            file_ids=list(req.file_ids),
        )
        saved = await self._samples.save(sample)
        await self._session.commit()
        return SampleDTO(
            id=saved.id,
            name=saved.name,
            species=saved.species,
            tissue=saved.tissue,
            description=saved.description,
            metadata=saved.metadata,
            file_ids=saved.file_ids,
            created_at=saved.created_at,
        )

    async def get_sample_file_paths(self, user_id: UUID, sample_id: UUID) -> list[str]:
        """供下游 Nextflow/Snakemake 读取样本文件绝对路径"""
        sample = await self._samples.get_by_id(user_id, sample_id)
        if sample is None:
            raise NotFoundError("样本不存在")
        paths: list[str] = []
        for fid in sample.file_ids:
            file = await self._files.get_by_id(user_id, fid)
            if file is not None:
                paths.append(str(self._resolve_abs(file.path)))
        return paths
