"""Case watch Celery task failure isolation."""

from __future__ import annotations

import pytest

import omichub.infrastructure.celery_app.tasks.agentteams as task_module


@pytest.mark.asyncio
async def test_watch_task_returns_failed_status_when_scan_raises(monkeypatch) -> None:
    class FailingSession:
        async def __aenter__(self):
            raise RuntimeError("database unavailable")

        async def __aexit__(self, *_args):
            return False

    result = await task_module._watch_cases_with_factory(
        lambda: lambda: FailingSession(), object
    )

    assert result == {"status": "failed"}
