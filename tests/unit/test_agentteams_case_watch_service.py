"""AgentTeams Case 状态回流的去重与失败隔离测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

import omichub.application.services.agentteams_case_watch_service as watch_module
from omichub.application.services.agentteams_case_watch_service import AgentTeamsCaseWatchService
from omichub.application.services.agentteams_case_watch_service import _watchable_sessions_query


class FakeDb:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flushes = 0

    def add(self, value: object) -> None:
        self.added.append(value)

    async def scalar(self, _query):
        return None

    async def flush(self) -> None:
        self.flushes += 1


@pytest.mark.unit
def test_watch_query_filters_sessions_without_case_bindings() -> None:
    statement = _watchable_sessions_query()
    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "sandbox_meta IS NOT NULL" in sql
    assert " ? " in sql


class FakeAgentTeams:
    async def get_case(self, case_id: str, requester_ref: str):
        assert case_id == "case-1"
        assert requester_ref == "user-1"
        return {"case_id": case_id, "intent": "RNA-seq 全流程交付", "status": "approval_pending"}


@pytest.mark.asyncio
async def test_watch_notifies_each_case_status_once(monkeypatch) -> None:
    db = FakeDb()
    service = AgentTeamsCaseWatchService(db)
    published: list[tuple[str, dict[str, str]]] = []

    async def publish(session_id: str, event: dict[str, str]) -> None:
        published.append((session_id, event))

    monkeypatch.setattr(watch_module, "publish_chat_case_event", publish)
    session = SimpleNamespace(
        session_id="session-1",
        user_id="user-1",
        sandbox_meta={
            "agentteams_case_ids": ["case-1"],
            "agentteams_case_status": {"case-1": "received"},
            "agentteams_case_notified": {"case-1": []},
        },
        updated_at=None,
        message_count=0,
        last_message_at=None,
    )

    first = await service._scan_session(session, FakeAgentTeams())
    second = await service._scan_session(session, FakeAgentTeams())

    assert first == {"scanned": 1, "notified": 1, "failed": 0}
    assert second == {"scanned": 1, "notified": 0, "failed": 0}
    assert len(db.added) == 1
    assert len(published) == 1
    assert session.sandbox_meta["agentteams_case_notified"]["case-1"] == ["approval_pending"]


@pytest.mark.asyncio
async def test_watch_continues_when_one_case_read_fails() -> None:
    db = FakeDb()
    service = AgentTeamsCaseWatchService(db)
    session = SimpleNamespace(
        session_id="session-1",
        user_id="user-1",
        sandbox_meta={"agentteams_case_ids": ["case-1"], "agentteams_case_status": {}},
        updated_at=None,
        message_count=0,
        last_message_at=None,
    )

    class BrokenAgentTeams:
        async def get_case(self, *_args, **_kwargs):
            raise RuntimeError("bridge unavailable")

    result = await service._scan_session(session, BrokenAgentTeams())

    assert result == {"scanned": 1, "notified": 0, "failed": 1}
    assert db.added == []
