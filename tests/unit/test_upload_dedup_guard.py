"""UploadService 秒传命中回归测试（A1 数据正确性缺陷修复）。

缺陷背景：原秒传命中条件仅 user_id + file_name + total_size，与内容无关；
命中后返回 completed=True 且 file_id=None，前端会伪造"成功"而文件并不存在。

修复后契约：
1. 传 file_md5 时，内容指纹不匹配不命中秒传；
2. 即使三元组命中，也必须回查到 active 的 FileRecord 才返回 completed=True；
   查不到则视为未命中，走正常上传流程（新会话 pending）。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cygnusx.application.schemas.file import UploadInitRequest
from cygnusx.application.services.upload_service import UploadService
from cygnusx.domain.file.entities import DataFile, UploadSession

pytestmark = pytest.mark.unit


def _make_service(
    completed_sessions: list[UploadSession],
    active_files: list[DataFile],
    tmp_path: Path,
) -> UploadService:
    """构造 stub 注入的 UploadService（绕过 __init__ 的 DB/存储依赖）。

    未命中秒传的路径会走 _inbox_subdir 真实建目录，因此工厂/后端
    用 LocalStorageBackend + tmp_path（与 test_file_service.py 同款手法）。
    """
    from cygnusx.infrastructure.config.storage_config import StorageConfig
    from cygnusx.infrastructure.storage.backend import LocalStorageBackend
    from cygnusx.infrastructure.storage.path_factory import StoragePathFactory

    service = object.__new__(UploadService)
    service._session = SimpleNamespace()

    async def _commit():
        return None

    service._session.commit = _commit

    async def _get_by_id(user_id):
        return SimpleNamespace(
            id=user_id,
            used_storage=0,
            storage_quota=10 * 1024 * 1024 * 1024,  # 10 GiB，远大于用例体量
        )

    async def _find_completed(*args, **kwargs):
        return _match_sessions(completed_sessions, args, kwargs)

    async def _list_by_user(user_id, status=None):
        return active_files

    async def _save_session(session):
        return session

    service._users = SimpleNamespace(get_by_id=_get_by_id)
    service._sessions = SimpleNamespace(
        find_completed=_find_completed, save=_save_session
    )
    service._files = SimpleNamespace(list_by_user=_list_by_user)
    service._factory = StoragePathFactory(
        StorageConfig(data_root=str(tmp_path), users_subdir="users")
    )
    service._backend = LocalStorageBackend(service._factory)
    return service


def _match_sessions(
    sessions: list[UploadSession], args: tuple, kwargs: dict
) -> UploadSession | None:
    """复刻仓库层 find_completed 的过滤语义（含 file_md5 增量）。"""
    _user_id, file_name, total_size = args[0], args[1], args[2]
    file_md5 = kwargs.get("file_md5")
    for s in sessions:
        if s.file_name != file_name or s.total_size != total_size:
            continue
        if file_md5 and s.file_md5 != file_md5:
            continue
        return s
    return None


def _completed_session(file_name: str, total_size: int, md5: str | None) -> UploadSession:
    return UploadSession(
        id=uuid4(),
        user_id=uuid4(),
        file_name=file_name,
        total_size=total_size,
        chunk_size=5 * 1024 * 1024,
        total_chunks=1,
        uploaded_chunks=[{"index": 0}],
        file_md5=md5,
        status="completed",
        directory="",
    )


def _active_file(file_name: str, directory: str = "") -> DataFile:
    return DataFile(
        id=uuid4(),
        user_id=uuid4(),
        path=f"users/x/inbox/{file_name}",
        original_name=file_name,
        size=100,
        checksum="",
        status="active",
        directory=directory,
    )


def _request(file_name: str, total_size: int, md5: str | None) -> UploadInitRequest:
    return UploadInitRequest(
        file_name=file_name,
        total_size=total_size,
        chunk_size=5 * 1024 * 1024,
        total_chunks=1,
        file_md5=md5,
        directory="",
    )


async def test_dedup_hit_with_matching_md5_and_existing_file(tmp_path) -> None:
    """同名同大小同 MD5 且文件记录存在 → 秒传命中且返回真实 file_id。"""
    file = _active_file("a.fastq")
    service = _make_service(
        [_completed_session("a.fastq", 100, "abc123")], [file], tmp_path
    )

    resp = await service.init_upload(file.user_id, _request("a.fastq", 100, "abc123"))

    assert resp.completed is True
    assert resp.file_id == file.id


async def test_dedup_miss_when_md5_differs(tmp_path) -> None:
    """同名同大小但内容指纹不同 → 不命中秒传（A1 核心场景）。"""
    user_id = uuid4()
    service = _make_service(
        [_completed_session("a.fastq", 100, "abc123")], [_active_file("a.fastq")], tmp_path
    )

    resp = await service.init_upload(user_id, _request("a.fastq", 100, "other456"))

    assert resp.completed is False


async def test_dedup_miss_when_file_record_missing(tmp_path) -> None:
    """三元组命中但文件记录已删/不存在 → 不返回假秒传（A1 假成功场景）。"""
    user_id = uuid4()
    service = _make_service(
        [_completed_session("a.fastq", 100, "abc123")], [], tmp_path  # file_records 为空
    )

    resp = await service.init_upload(user_id, _request("a.fastq", 100, "abc123"))

    assert resp.completed is False


async def test_dedup_hit_tolerates_directory_inbox_normalization(tmp_path) -> None:
    """历史会话 directory='inbox' 与文件记录 directory='' 视为同一目录。"""
    file = _active_file("a.fastq", directory="")
    session = _completed_session("a.fastq", 100, "abc123")
    session.directory = "inbox"
    service = _make_service([session], [file], tmp_path)

    resp = await service.init_upload(file.user_id, _request("a.fastq", 100, "abc123"))

    assert resp.completed is True
    assert resp.file_id == file.id


async def test_dedup_requires_directory_match(tmp_path) -> None:
    """同名文件但目录不同 → 不命中秒传。"""
    file = _active_file("a.fastq", directory="proj1")
    session = _completed_session("a.fastq", 100, "abc123")
    session.directory = "proj2"
    service = _make_service([session], [file], tmp_path)

    resp = await service.init_upload(file.user_id, _request("a.fastq", 100, "abc123"))

    assert resp.completed is False


@pytest.mark.parametrize("md5", [None, ""])
async def test_dedup_without_md5_still_guards_file_record(md5: str | None, tmp_path) -> None:
    """旧客户端未传 MD5：退化为三元组匹配，但 file_id 非空守卫仍生效。"""
    user_id = uuid4()
    # 会话存在但文件已删 → 不得假成功
    service = _make_service(
        [_completed_session("a.fastq", 100, "abc123")], [], tmp_path
    )
    resp = await service.init_upload(user_id, _request("a.fastq", 100, md5))
    assert resp.completed is False

    # 会话与文件都在 → 命中并返回真实 file_id
    file = _active_file("a.fastq")
    service_ok = _make_service(
        [_completed_session("a.fastq", 100, "abc123")], [file], tmp_path
    )
    resp_ok = await service_ok.init_upload(file.user_id, _request("a.fastq", 100, md5))
    assert resp_ok.completed is True
    assert resp_ok.file_id == file.id
