"""Real Worker preflight with offline SQL; no executable, socket or broker is started."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock

import pytest

from cygnusx.infrastructure.celery_app.tasks import download as worker
from cygnusx.infrastructure.database import session as session_module
from cygnusx.infrastructure.database.models.task import TaskModel
from tests.unit.test_download_registration_contract import (
    download_env as download_env,
)
from tests.unit.test_download_registration_contract import (
    imports as imports,
)
from tests.unit.test_download_registration_contract import (
    registry as registry,
)
from tests.unit.test_download_registration_contract import (
    sandbox_thread_wakeup as sandbox_thread_wakeup,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_queued_unsupported_method_is_failed_before_any_transfer(download_env, monkeypatch):
    env = download_env
    task = TaskModel(
        user_id=env.owner,
        flow_id="ebi_download",
        name="old-queue",
        status="queued",
        parameters={"source": "sra", "accession": "SRR1", "download_method": "aspera"},
    )
    env.db.add(task)
    await env.db.commit()

    @asynccontextmanager
    async def factory():
        yield env.db

    monkeypatch.setattr(session_module, "get_session_factory", lambda: factory)
    publish = AsyncMock()
    prepare = AsyncMock()
    executor = Mock()
    monkeypatch.setattr(worker, "publish_task_log", publish)
    monkeypatch.setattr(worker, "_prepare_download_registration", prepare)
    monkeypatch.setattr(worker, "get_executor", executor)
    result = await worker._execute_download(str(task.id))
    assert result["status"] == "failed"
    assert task.status == "failed"
    assert "DOWNLOAD_METHOD_UNSUPPORTED" in task.error_message
    assert task.parameters["_download_registration"]["reason_code"] == "DOWNLOAD_METHOD_UNSUPPORTED"
    prepare.assert_not_called()
    executor.assert_not_called()
