"""Case watch Celery task failure isolation."""

from __future__ import annotations

import pytest

import omichub.infrastructure.celery_app.tasks.agentteams as task_module


class FakeRedis:
    def __init__(self, acquired: bool = True) -> None:
        self.acquired = acquired
        self.set_calls: list[tuple[object, ...]] = []
        self.release_calls: list[tuple[object, ...]] = []

    async def set(self, *args, **kwargs):
        self.set_calls.append((*args, kwargs))
        return self.acquired

    async def eval(self, *args):
        self.release_calls.append(args)
        return 1


@pytest.mark.asyncio
async def test_watch_task_returns_failed_status_when_scan_raises(monkeypatch) -> None:
    class FailingSession:
        async def __aenter__(self):
            raise RuntimeError("database unavailable")

        async def __aexit__(self, *_args):
            return False

    redis = FakeRedis()
    result = await task_module._watch_cases_with_factory(
        lambda: lambda: FailingSession(), object, redis_getter=lambda: redis
    )

    assert result == {"status": "failed"}
    assert len(redis.release_calls) == 1


@pytest.mark.asyncio
async def test_watch_task_skips_when_another_worker_holds_lock() -> None:
    redis = FakeRedis(acquired=False)
    session_factory_called = False

    def session_factory():
        nonlocal session_factory_called
        session_factory_called = True
        raise AssertionError("locked watch must not open a database session")

    result = await task_module._watch_cases_with_factory(
        session_factory, object, redis_getter=lambda: redis
    )

    assert result == {"status": "skipped_locked"}
    assert session_factory_called is False
    assert redis.release_calls == []
