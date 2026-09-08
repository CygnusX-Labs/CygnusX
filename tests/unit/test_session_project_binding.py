"""会话强制绑定项目的校验测试 + 项目 customer 字段回归。

覆盖：
- ChatSessionManagement.create_session 的项目边界校验
  （缺失 422 / 不存在 404 / 越权 403 / 内部豁免 require_project=False）
- ProjectService.create_project 持久化 customer 并随响应返回
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from cygnusx.application.services.chat.session_management import ChatSessionManagement
from cygnusx.application.services.project_service import ProjectService
from cygnusx.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from cygnusx.infrastructure.config.storage_config import StorageConfig
from cygnusx.infrastructure.storage.path_factory import StoragePathFactory


class _FakeResult:
    def __init__(self, model):  # noqa: ANN001
        self._model = model

    def scalar_one_or_none(self):  # noqa: ANN202
        return self._model


class _SessionSvc(ChatSessionManagement):
    """最小可实例化的会话服务：DTO 转换原样返回。"""

    @staticmethod
    def _to_session_dto(session):  # noqa: ANN001, ANN202
        return session


def _make_session_service(project) -> _SessionSvc:  # noqa: ANN001, ANN202
    svc = _SessionSvc()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_FakeResult(project))
    svc._db = db
    now = datetime.now(UTC)
    svc._sessions = SimpleNamespace(
        create=AsyncMock(
            return_value=SimpleNamespace(
                session_id="sess-1",
                title="新对话",
                project_id=None,
                created_at=now,
                updated_at=now,
            )
        )
    )
    return svc


@pytest.mark.asyncio
async def test_create_session_requires_project_id() -> None:
    svc = _make_session_service(project=None)
    with pytest.raises(ValidationError):
        await svc.create_session(str(uuid4()), uuid4())
    svc._sessions.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_session_invalid_project_id_is_404() -> None:
    svc = _make_session_service(project=None)
    with pytest.raises(NotFoundError):
        await svc.create_session(str(uuid4()), uuid4(), project_id="not-a-uuid")


@pytest.mark.asyncio
async def test_create_session_missing_project_is_404() -> None:
    svc = _make_session_service(project=None)
    with pytest.raises(NotFoundError):
        await svc.create_session(str(uuid4()), uuid4(), project_id=str(uuid4()))


@pytest.mark.asyncio
async def test_create_session_foreign_project_is_403() -> None:
    project = SimpleNamespace(id=uuid4(), user_id=uuid4())
    svc = _make_session_service(project=project)
    with pytest.raises(AuthorizationError):
        await svc.create_session(str(uuid4()), uuid4(), project_id=str(project.id))


@pytest.mark.asyncio
async def test_create_session_with_owned_project_passes() -> None:
    user_id = uuid4()
    project = SimpleNamespace(id=uuid4(), user_id=user_id)
    svc = _make_session_service(project=project)

    await svc.create_session(str(user_id), uuid4(), project_id=str(project.id))

    svc._sessions.create.assert_awaited_once()
    assert svc._sessions.create.await_args.kwargs["project_id"] == str(project.id)


@pytest.mark.asyncio
async def test_create_session_internal_bypass_skips_validation() -> None:
    svc = _make_session_service(project=None)

    await svc.create_session(str(uuid4()), uuid4(), require_project=False)

    svc._db.execute.assert_not_awaited()
    svc._sessions.create.assert_awaited_once()
    assert svc._sessions.create.await_args.kwargs["project_id"] is None


class _FakeDirectoryRepo:
    def __init__(self, _session) -> None:  # noqa: ANN001
        pass

    async def get_by_path(self, *_args):  # noqa: ANN002, ANN202
        return None

    async def save(self, *_args):  # noqa: ANN002, ANN202
        return None


@pytest.mark.asyncio
async def test_create_project_persists_customer(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    factory = StoragePathFactory(
        StorageConfig(data_root=str(tmp_path), users_subdir="users")
    )
    monkeypatch.setattr(
        "cygnusx.application.services.project_service.get_path_factory", lambda: factory
    )
    monkeypatch.setattr(
        "cygnusx.application.services.project_service.DirectoryRepositoryImpl",
        _FakeDirectoryRepo,
    )
    session = MagicMock()
    session.execute = AsyncMock(return_value=_FakeResult(None))
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    service = ProjectService(session)

    user_id = uuid4()
    project = await service.create_project(user_id, "肿瘤队列分析", customer=" 某医院 ")

    model = session.add.call_args.args[0]
    assert model.customer == "某医院"
    assert project["customer"] == "某医院"
    assert (factory.project_dir(str(user_id), project["slug"]) / "runs").is_dir()


@pytest.mark.asyncio
async def test_create_project_rejects_overlong_customer(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    factory = StoragePathFactory(
        StorageConfig(data_root=str(tmp_path), users_subdir="users")
    )
    monkeypatch.setattr(
        "cygnusx.application.services.project_service.get_path_factory", lambda: factory
    )
    session = MagicMock()
    service = ProjectService(session)

    with pytest.raises(ValidationError):
        await service.create_project(uuid4(), "肿瘤队列分析", customer="x" * 201)
    session.add.assert_not_called()


def test_project_response_dict_includes_customer() -> None:
    now = datetime.now(UTC)
    model = SimpleNamespace(
        id=uuid4(),
        name="p",
        slug="p",
        description="",
        customer="客户A",
        created_at=now,
        updated_at=now,
    )
    assert ProjectService._to_dict(model)["customer"] == "客户A"
