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


@pytest.mark.asyncio
async def test_event_consumer_runs_bound_cases_and_releases_lock(monkeypatch) -> None:
    session = type(
        "BoundSession",
        (),
        {
            "session_id": "session-1",
            "sandbox_meta": {
                "agentteams_case_ids": ["case-1", "case-closed"],
                "agentteams_case_status": {"case-1": "executing", "case-closed": "closed"},
            },
        },
    )()

    class DiscoverySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def scalars(self, _query):
            return type("Rows", (), {"all": lambda self: [session]})()

    class ConsumerSession:
        committed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def commit(self):
            self.committed = True

    consumer_session = ConsumerSession()
    sessions = iter([DiscoverySession(), consumer_session])

    class Consumer:
        def __init__(self, db):
            assert db is consumer_session

        async def consume(self, session_id, case_id, *, watch_seconds):
            assert (session_id, case_id, watch_seconds) == ("session-1", "case-1", 2)
            return {"events": 2, "projected": 3, "skipped": 0}

    redis = FakeRedis()
    result = await task_module._consume_case_events_with_factory(
        lambda: lambda: next(sessions),
        Consumer,
        redis_getter=lambda: redis,
        stream_seconds=2,
    )

    assert result == {"bindings": 1, "events": 2, "projected": 3, "failed": 0}
    assert consumer_session.committed is True
    assert len(redis.release_calls) == 1


@pytest.mark.asyncio
async def test_stale_task_watch_runs_service_and_releases_lock(monkeypatch) -> None:
    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    class Service:
        def __init__(self, _session):
            pass

        async def scan(self, *, stale_after_seconds):
            assert stale_after_seconds == 600
            return {"scanned": 1, "requeued": 1, "failed": 0, "skipped": 0}

    monkeypatch.setattr(
        task_module,
        "get_settings",
        lambda: type("Settings", (), {"agentteams_stale_task_seconds": 600})(),
    )
    redis = FakeRedis()
    result = await task_module._requeue_stale_tasks_with_factory(
        lambda: lambda: Session(), Service, redis_getter=lambda: redis
    )

    assert result["requeued"] == 1
    assert len(redis.release_calls) == 1
