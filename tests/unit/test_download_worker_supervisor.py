"""Worker-to-Supervisor orchestration contract; no network or OS backend."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from cygnusx.core.exceptions import ValidationError
from cygnusx.infrastructure.celery_app.tasks import download as worker
from cygnusx.infrastructure.download import execution_request, supervisor_client
from cygnusx.infrastructure.download.trusted_execution import ExecutionBoundaryRequest

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_http_worker_uses_supervisor_lifecycle(monkeypatch):
    task_id, owner_id, scope = uuid4(), uuid4(), uuid4()
    request = ExecutionBoundaryRequest(
        task_id=task_id,
        owner_id=owner_id,
        attempt_id=uuid4(),
        execution_id=uuid4(),
        execution_epoch=1,
        admission_ref=uuid4(),
        budget_ref=uuid4(),
    )
    task = SimpleNamespace(user_id=owner_id, parameters={})

    async def build_request(session, requested_task_id, requested_owner_id):
        assert session is sentinel_session
        assert (requested_task_id, requested_owner_id) == (task_id, owner_id)
        return request

    class FakeAdapter:
        instances = []

        def __init__(self, *, settings):
            self.events = []
            self.observations = 0
            FakeAdapter.instances.append(self)

        async def start(self, actual_request):
            assert actual_request == request
            self.events.append("start")
            return scope

        async def observe(self, actual_task_id, actual_scope):
            assert (actual_task_id, actual_scope) == (task_id, scope)
            self.observations += 1
            self.events.append("observe")
            if self.observations == 1:
                return SimpleNamespace(state="running")
            return SimpleNamespace(state="stopped", reason="completed", returncode=0)

        async def renew(self, actual_task_id, actual_scope):
            assert (actual_task_id, actual_scope) == (task_id, scope)
            self.events.append("renew")

        async def evidence(self, actual_request, actual_scope):
            assert (actual_request, actual_scope) == (request, scope)
            self.events.append("evidence")
            return SimpleNamespace(model_dump=lambda mode: {"scope_ref": str(scope)})

        async def stop(self, *_args):
            self.events.append("stop")

        async def aclose(self):
            self.events.append("close")

    class Session:
        async def flush(self):
            self.flushed = True

    sentinel_session = Session()
    monkeypatch.setattr(execution_request, "build_execution_boundary_request", build_request)
    monkeypatch.setattr(supervisor_client, "MutualTLSExecutionAdapter", FakeAdapter)

    logs = []

    async def log(*args, **kwargs):
        logs.append((args, kwargs))

    await worker._execute_supervised_http_download(
        session=sentinel_session,
        task=task,
        task_uuid=task_id,
        add_and_publish_log=log,
    )

    assert task.parameters["_download_execution"]["scope_ref"] == str(scope)
    assert sentinel_session.flushed
    assert FakeAdapter.instances[0].events == [
        "start",
        "observe",
        "renew",
        "observe",
        "evidence",
        "close",
    ]
    assert logs


@pytest.mark.asyncio
async def test_http_worker_does_not_renew_unknown_or_unrecognized_state(monkeypatch):
    task_id, owner_id, scope = uuid4(), uuid4(), uuid4()
    request = ExecutionBoundaryRequest(
        task_id=task_id,
        owner_id=owner_id,
        attempt_id=uuid4(),
        execution_id=uuid4(),
        execution_epoch=1,
        admission_ref=uuid4(),
        budget_ref=uuid4(),
    )
    task = SimpleNamespace(user_id=owner_id, parameters={})

    async def build_request(session, requested_task_id, requested_owner_id):
        return request

    class FakeAdapter:
        instances = []

        def __init__(self, *, settings):
            self.stopped = False
            self.renewed = False
            FakeAdapter.instances.append(self)

        async def start(self, actual_request):
            return scope

        async def observe(self, actual_task_id, actual_scope):
            return SimpleNamespace(state="unknown")

        async def renew(self, actual_task_id, actual_scope):
            self.renewed = True

        async def stop(self, *_args):
            self.stopped = True

        async def aclose(self):
            return None

    sentinel_session = SimpleNamespace(flush=lambda: None)
    monkeypatch.setattr(execution_request, "build_execution_boundary_request", build_request)
    monkeypatch.setattr(supervisor_client, "MutualTLSExecutionAdapter", FakeAdapter)

    async def log(*args, **kwargs):
        return None

    with pytest.raises(ValidationError) as error:
        await worker._execute_supervised_http_download(
            session=sentinel_session,
            task=task,
            task_uuid=task_id,
            add_and_publish_log=log,
        )
    assert error.value.code == "DOWNLOAD_SCOPE_RECONCILIATION_REQUIRED"
    assert FakeAdapter.instances[0].renewed is False
    assert FakeAdapter.instances[0].stopped is True
