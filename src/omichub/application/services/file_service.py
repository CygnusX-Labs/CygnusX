"""文件应用服务 — DB 文件记录 + 分块上传 + 配额控制

落盘规范：
  原始上传：{storage_path}/users/{user_id}/raw/{filename}
  分析输出：{storage_path}/users/{user_id}/results/{task_id}/...
  分片临时：{storage_path}/.tmp/{upload_id}/{index}
"""

from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.schemas.file import (
    DataFileDTO,
    DirectoryCreateRequest,
    DirectoryDTO,
    FileListResponse,
    FilePickerItemDTO,
    MoveFileRequest,
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
from omichub.core.config import get_settings
from omichub.core.exceptions import AuthorizationError, ConflictError, NotFoundError, QuotaExceededError, ValidationError
from omichub.domain.file.entities import DataFile, Directory, Sample, UploadSession
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

# 默认分片大小（客户端未传时兜底）
DEFAULT_CHUNK_SIZE = 5 * 1024 * 1024  # 5 MiB

# 系统默认目录：用户首次访问时懒初始化，锁定不可删除/重命名
SYSTEM_DIRECTORIES: tuple[str, ...] = ("raw_data", "workspace", "temp")


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


async def ensure_directory_chain(session: AsyncSession, user_id: UUID, path: str) -> None:
    """确保 path 及其各级父目录在 user_directories 中存在（幂等）。

    path 形如 ``raw_data/PRJNA1259417``。逐段创建缺失的 Directory 记录；系统默认目录段
    （raw_data/workspace/temp）标记 is_system=True，其余为用户数据目录。
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
        self._sessions = UploadSessionRepositoryImpl(session)
        self._samples = SampleRepositoryImpl(session)
        self._dirs = DirectoryRepositoryImpl(session)
        self._users = SqlAlchemyUserRepository(session)
        settings = get_settings()
        self._storage_root = Path(settings.storage_path)

    # ------------------------------------------------------------------
    # 路径工厂
    # ------------------------------------------------------------------
    def user_raw_dir(self, user_id: UUID) -> Path:
        d = self._storage_root / "users" / str(user_id) / "raw"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def user_results_dir(self, user_id: UUID) -> Path:
        d = self._storage_root / "users" / str(user_id) / "results"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def user_downloads_dir(self, user_id: UUID) -> Path:
        d = self._storage_root / "users" / str(user_id) / "downloads"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _tmp_dir(self, upload_id: UUID) -> Path:
        d = self._storage_root / ".tmp" / str(upload_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _resolve_abs(self, storage_path: str) -> Path:
        """storage_path 为相对根目录的路径；拼成绝对路径"""
        return self._storage_root / storage_path

    def _normalize_directory(self, directory: str | None) -> str:
        """规整目录路径：去首尾斜杠、禁绝对路径越权"""
        if not directory:
            return ""
        d = directory.strip().strip("/")
        # 防止 .. 越权逃逸用户目录
        parts = [p for p in d.split("/") if p not in ("", ".", "..")]
        return "/".join(parts)

    def _raw_subdir(self, user_id: UUID, directory: str) -> Path:
        """用户 raw/ 下的指定子目录（自动创建）"""
        d = self.user_raw_dir(user_id)
        if directory:
            d = d / directory
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------
    # 列表 / 配额
    # ------------------------------------------------------------------
    async def list_files(self, user_id: UUID, directory: str | None = None) -> FileListResponse:
        items = await self._files.list_by_user(user_id, status="active", directory=directory)
        dtos = [
            DataFileDTO(
                id=f.id,
                original_name=f.original_name,
                size=f.size,
                file_type=f.file_type,
                status=f.status,
                checksum=f.checksum,
                directory=f.directory,
                created_at=f.created_at,
            )
            for f in items
        ]
        return FileListResponse(items=dtos, total=len(dtos))

    async def get_quota(self, user_id: UUID) -> QuotaResponse:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("用户不存在")
        total = user.storage_quota
        used = user.used_storage
        percent = round(used / total * 100, 2) if total > 0 else 100.0
        return QuotaResponse(used=used, total=total, percent=percent)

    # ------------------------------------------------------------------
    # 分块上传：init / chunk / merge
    # ------------------------------------------------------------------
    async def init_upload(self, user_id: UUID, req: UploadInitRequest) -> UploadInitResponse:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("用户不存在")

        directory = self._normalize_directory(req.directory)

        # 配额前置校验
        if user.used_storage + req.total_size > user.storage_quota:
            raise QuotaExceededError(
                f"存储空间不足：已用 {user.used_storage}，配额 {user.storage_quota}，"
                f"本次需 {req.total_size}"
            )

        # 秒传：同名同大小且已 completed 的会话 → 视为已传完
        completed = await self._sessions.find_completed(user_id, req.file_name, req.total_size)
        if completed is not None:
            return UploadInitResponse(
                upload_id=completed.id,
                completed=True,
                file_id=None,
                uploaded_chunks=list(range(completed.total_chunks)),
                chunk_size=completed.chunk_size,
            )

        # 预创建目标物理目录（raw/{directory}/）
        self._raw_subdir(user_id, directory)

        # 新建上传会话（断点续传由客户端在 chunk 阶段重传来补齐；
        # 同一文件若中途中断重传，会创建新会话，旧 pending 会话由 Celery 清理）
        session = UploadSession(
            id=uuid.uuid4(),
            user_id=user_id,
            file_name=req.file_name,
            total_size=req.total_size,
            chunk_size=req.chunk_size,
            total_chunks=req.total_chunks,
            uploaded_chunks=[],
            file_md5=req.file_md5,
            status="pending",
            directory=directory,
        )
        await self._sessions.save(session)
        await self._session.commit()
        return UploadInitResponse(
            upload_id=session.id,
            completed=False,
            uploaded_chunks=[],
            chunk_size=req.chunk_size,
        )

    async def save_chunk(
        self,
        user_id: UUID,
        upload_id: UUID,
        index: int,
        chunk_bytes: bytes,
        md5: str,
    ) -> UploadChunkResponse:
        session = await self._sessions.get_by_id(user_id, upload_id)
        if session is None:
            raise NotFoundError("上传会话不存在")
        if session.status in ("completed", "merging"):
            raise ValidationError("上传会话已结束")
        if index < 0 or index >= session.total_chunks:
            raise ValidationError(f"分片序号越界：{index}")

        # 校验分片 MD5
        actual_md5 = hashlib.md5(chunk_bytes).hexdigest()
        if actual_md5 != md5:
            raise ValidationError(f"分片 {index} 校验失败：MD5 不匹配")

        # 落盘到临时目录
        chunk_path = self._tmp_dir(upload_id) / str(index)
        chunk_path.write_bytes(chunk_bytes)

        # 更新会话（幂等：同 index 替换）
        session = await self._sessions.add_chunk(
            user_id, upload_id, {"index": index, "md5": md5}
        )
        if session is None:
            raise NotFoundError("上传会话不存在")
        await self._session.commit()
        return UploadChunkResponse(
            upload_id=upload_id,
            index=index,
            accepted=True,
            uploaded=len(session.uploaded_chunks),
        )

    async def merge_upload(self, user_id: UUID, upload_id: UUID) -> UploadMergeResponse:
        session = await self._sessions.get_by_id(user_id, upload_id)
        if session is None:
            raise NotFoundError("上传会话不存在")
        if session.status == "completed":
            raise ValidationError("上传会话已合并完成")

        if len(session.uploaded_chunks) != session.total_chunks:
            raise ValidationError(
                f"分片不齐全：已传 {len(session.uploaded_chunks)}/{session.total_chunks}"
            )

        # 标记 merging，防并发重复合并
        await self._sessions.update_status(user_id, upload_id, "merging")
        await self._session.commit()

        tmp_dir = self._tmp_dir(upload_id)
        directory = self._normalize_directory(session.directory)
        raw_subdir = self._raw_subdir(user_id, directory)  # raw/{directory}/，自动创建
        final_path = raw_subdir / session.file_name
        # 同名冲突：追加短 uuid
        if final_path.exists():
            stem = final_path.stem
            final_path = raw_subdir / f"{stem}_{uuid.uuid4().hex[:8]}{final_path.suffix}"

        hasher = hashlib.md5()
        with final_path.open("wb") as out:
            for chunk_meta in sorted(session.uploaded_chunks, key=lambda c: c["index"]):
                cp = tmp_dir / str(chunk_meta["index"])
                if not cp.exists():
                    raise ValidationError(f"分片文件丢失：{chunk_meta['index']}")
                data = cp.read_bytes()
                out.write(data)
                hasher.update(data)

        checksum = hasher.hexdigest()
        size = final_path.stat().st_size
        rel_path = str(final_path.relative_to(self._storage_root))

        # 创建文件记录
        file_record = DataFile(
            id=uuid.uuid4(),
            user_id=user_id,
            path=rel_path,
            original_name=session.file_name,
            size=size,
            checksum=checksum,
            file_type=_detect_file_type(session.file_name),
            status="active",
            directory=directory,
        )
        await self._files.save(file_record)

        # 原子累加配额
        new_used = await self._users.add_used_storage(user_id, size)

        # 标记会话完成，清理临时分片
        await self._sessions.update_status(user_id, upload_id, "completed")
        await self._session.commit()
        shutil.rmtree(tmp_dir, ignore_errors=True)

        return UploadMergeResponse(
            file_id=file_record.id,
            original_name=file_record.original_name,
            size=size,
            checksum=checksum,
            used_storage=new_used,
        )

    async def cancel_upload(self, user_id: UUID, upload_id: UUID) -> bool:
        """取消上传：删会话 + 清理临时分片"""
        session = await self._sessions.get_by_id(user_id, upload_id)
        if session is None:
            raise NotFoundError("上传会话不存在")
        await self._sessions.delete(user_id, upload_id)
        await self._session.commit()
        shutil.rmtree(self._tmp_dir(upload_id), ignore_errors=True)
        return True

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
        new_subdir = self._raw_subdir(user_id, directory)
        new_abs = new_subdir / old_abs.name
        if new_abs.exists() and new_abs != old_abs:
            # 目标已存在同名：追加短 uuid
            stem = new_abs.stem
            new_abs = new_subdir / f"{stem}_{uuid.uuid4().hex[:8]}{new_abs.suffix}"
        if old_abs.exists() and new_abs != old_abs:
            shutil.move(str(old_abs), str(new_abs))
        file.directory = directory
        file.path = str(new_abs.relative_to(self._storage_root))
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
            created_at=saved.created_at,
        )

    # ------------------------------------------------------------------
    # 用户目录 CRUD
    # ------------------------------------------------------------------
    async def ensure_default_directories(self, user_id: UUID) -> None:
        """懒初始化系统默认目录 raw_data / workspace / temp。

        任何用户首次访问目录列表时补齐，避免改动注册/激活流程。
        已存在则跳过；新建的标记 is_system=True 并预创建物理目录。
        """
        existing = await self._dirs.list_by_user(user_id)
        existing_paths = {d.path for d in existing}
        created_any = False
        for name in SYSTEM_DIRECTORIES:
            if name in existing_paths:
                continue
            directory = Directory(
                id=uuid.uuid4(),
                user_id=user_id,
                path=name,
                name=name,
                parent_path=None,
                is_system=True,
            )
            await self._dirs.save(directory)
            self._raw_subdir(user_id, name)  # 预创建物理目录
            created_any = True
        if created_any:
            await self._session.commit()

    async def list_directories(self, user_id: UUID) -> list[DirectoryDTO]:
        await self.ensure_default_directories(user_id)
        dirs = await self._dirs.list_by_user(user_id)
        return [
            DirectoryDTO(
                id=d.id,
                path=d.path,
                name=d.name,
                parent_path=d.parent_path,
                is_system=d.is_system,
                created_at=d.created_at,
            )
            for d in dirs
        ]

    async def create_directory(self, user_id: UUID, req: DirectoryCreateRequest) -> DirectoryDTO:
        path = self._normalize_directory(req.path)
        if not path:
            raise ValidationError("目录名不能为空")
        if len(path) > 500:
            raise ValidationError("目录路径过长")
        # 顶层目录不得与系统默认目录同名，避免冲突
        top = path.split("/")[0]
        if top in SYSTEM_DIRECTORIES and not await self._dirs.get_by_path(user_id, top):
            # 允许在系统目录下建子目录，但不允许新建同名顶层系统目录
            if path == top:
                raise ConflictError(f"系统目录已存在：{path}")
        if await self._dirs.get_by_path(user_id, path) is not None:
            raise ConflictError(f"目录已存在：{path}")
        # 父目录必须存在（若有多级）
        parts = path.split("/")
        name = parts[-1]
        parent_path = "/".join(parts[:-1]) if len(parts) > 1 else None
        if parent_path and await self._dirs.get_by_path(user_id, parent_path) is None:
            raise NotFoundError(f"父目录不存在：{parent_path}")
        directory = Directory(
            id=uuid.uuid4(),
            user_id=user_id,
            path=path,
            name=name,
            parent_path=parent_path,
        )
        saved = await self._dirs.save(directory)
        # 预创建物理目录
        self._raw_subdir(user_id, path)
        await self._session.commit()
        return DirectoryDTO(
            id=saved.id, path=saved.path, name=saved.name, parent_path=saved.parent_path, created_at=saved.created_at
        )

    async def delete_directory(self, user_id: UUID, path: str) -> bool:
        path = self._normalize_directory(path)
        if not path:
            raise ValidationError("不能删除根目录")
        # 校验归属
        target = await self._dirs.get_by_path(user_id, path)
        if target is None:
            raise NotFoundError("目录不存在")
        # 系统默认目录锁定，禁止删除
        if target.is_system:
            raise AuthorizationError(f"系统目录不可删除：{path}")
        # 检查是否有子目录
        all_dirs = await self._dirs.list_by_user(user_id)
        if any(d.path.startswith(path + "/") for d in all_dirs):
            raise ValidationError("目录下还有子目录，请先删除子目录")
        # 删除目录记录（文件记录的 directory 字段不动，文件仍在原物理路径，
        # 但会从该目录视图消失——实际上文件 directory 仍指向该路径，会显示为孤儿。
        # 简化策略：连带把该目录下的文件 directory 置空回根，避免孤儿）
        files = await self._files.list_by_user(user_id, status="active", directory=path)
        for f in files:
            f.directory = ""
            await self._files.save(f)
        ok = await self._dirs.delete(user_id, path)
        await self._session.commit()
        return ok

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
    # 文件同步（磁盘 → file_records，只增不删）
    # ------------------------------------------------------------------
    async def sync_user_files(self, user_id: UUID) -> SyncResponse:
        """扫描用户目录，把磁盘有但 file_records 没有的文件登记进来（只增不删），并重算配额。

        用于：手动放入的文件、旧任务未登记的产物等。幂等：同 storage_path 已存在则跳过。
        directory 推导见 ``_derive_directory``（raw/ 前缀剥离匹配上传，raw_data/ 等保留匹配下载）。
        """
        from sqlalchemy import select

        from omichub.infrastructure.database.models.file import FileRecordModel

        user_root = self._storage_root / "users" / str(user_id)
        if not user_root.exists():
            await self._users.recompute_used_storage(user_id)
            return SyncResponse(added=0, added_size=0)

        # 一次性取已有 storage_path 集合，避免逐文件查询
        res = await self._session.execute(
            select(FileRecordModel.storage_path).where(FileRecordModel.user_id == user_id)
        )
        existing: set[str] = {row[0] for row in res.all()}

        added = 0
        added_size = 0
        for f in user_root.rglob("*"):
            if not f.is_file():
                continue
            # 跳过隐藏目录/文件（.tmp 上传分片、.qoder 等 IDE 元数据）
            if any(part.startswith(".") for part in f.relative_to(user_root).parts):
                continue
            try:
                rel = str(f.relative_to(self._storage_root))
            except ValueError:
                continue
            if rel in existing:
                continue
            try:
                rel_user = f.relative_to(user_root)
            except ValueError:
                rel_user = None
            directory = self._derive_directory(rel_user)
            if directory:
                await ensure_directory_chain(self._session, user_id, directory)
            try:
                size = f.stat().st_size
            except OSError:
                continue
            record = DataFile(
                id=uuid.uuid4(),
                user_id=user_id,
                path=rel,
                original_name=f.name,
                size=size,
                checksum="",
                file_type=_detect_file_type(f.name),
                status="active",
                directory=directory,
            )
            await self._files.save(record)
            existing.add(rel)
            added += 1
            added_size += size

        # 重算配额，修正历史漂移（下载/手动放入未计入的部分）
        await self._users.recompute_used_storage(user_id)
        await self._session.commit()
        return SyncResponse(added=added, added_size=added_size)

    @staticmethod
    def _derive_directory(rel_user: Path | None) -> str:
        """从「相对用户根的路径」推导 logical directory。

        - ``raw_data/PRJNA1259417/x.fq`` → ``raw_data/PRJNA1259417``（下载布局，保留）
        - ``raw/myproj/x.fq`` → ``myproj``（上传布局，剥离 raw/ 前缀）
        - ``raw/raw_data/x.fq`` → ``raw_data``（上传到系统目录 raw_data）
        - 直接在用户根下的文件 → ``""``
        """
        if rel_user is None:
            return ""
        parts = list(rel_user.parts)[:-1]  # 去掉文件名
        if not parts:
            return ""
        if parts[0] == "raw":
            parts = parts[1:]
        parts = [p for p in parts if p and p not in (".", "..")]
        return "/".join(parts)

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
