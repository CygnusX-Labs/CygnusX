"""长期记忆异步摘要任务的无外部依赖契约测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cygnusx.application.services.chat_service import ChatService
from cygnusx.infrastructure.celery_app.tasks.memory import (
    _conversation_text,
    _settle_idle_sessions,
    _settle_session_memory_v2,
    _summary_content,
    is_agentteams_synthetic_session,
)


@pytest.fixture(autouse=True)
def isolate_settlement_candidate_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "cygnusx.infrastructure.memory.fact_store.PostgresFactStore.settlement_candidates",
        AsyncMock(return_value=[]),
    )


def test_conversation_text_excludes_empty_and_non_chat_messages() -> None:
    messages = [
        SimpleNamespace(role="user", content="我使用 GRCh38"),
        SimpleNamespace(role="tool", content="不应进入摘要"),
        SimpleNamespace(role="assistant", content="收到"),
        SimpleNamespace(role="assistant", content="  "),
    ]

    assert _conversation_text(messages) == "user: 我使用 GRCh38\nassistant: 收到"


def test_summary_content_is_single_line_and_bounded() -> None:
    response = {
        "choices": [
            {"message": {"content": "  用户使用\nGRCh38 作为参考基因组。  "}}
        ]
    }

    assert _summary_content(response) == "用户使用 GRCh38 作为参考基因组。"
    assert _summary_content({"choices": []}) == ""


# --- M0：settle 泄漏面封堵（AgentTeams 合成会话排除） ---


def _settings(**overrides) -> SimpleNamespace:
    base = {"memory_v2_enabled": True, "memory_focus_per_project_enabled": False, "memory_settle_min_new_messages": 4,
            "memory_recall_tracking_enabled": True, "memory_settle_candidate_limit": 30}
    base.update(overrides)
    return SimpleNamespace(**base)


def _capture_enqueue(monkeypatch, settings) -> list:
    calls: list = []
    monkeypatch.setattr(ChatService, "_memory_runtime_enabled", AsyncMock(return_value=settings.memory_v2_enabled))
    monkeypatch.setattr("cygnusx.core.config.get_settings", lambda: settings)
    monkeypatch.setattr(
        "cygnusx.infrastructure.task_queue.dispatcher.enqueue_task",
        lambda task, *args, **kwargs: calls.append(task),
    )
    return calls


def _session(**overrides) -> SimpleNamespace:
    base = {
        "session_id": "chat-normal-1",
        "mode": "chat",
        "status": "active",
        "message_count": 8,
        "agent_id": "agent-scrna",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "marker",
    [
        {"mode": "agentteams"},
        {"status": "system"},
        {"session_id": "agentteams:case-1"},
    ],
    ids=["mode_agentteams", "status_system", "session_id_prefix"],
)
async def test_settle_entries_skip_agentteams_synthetic_sessions(monkeypatch, marker) -> None:
    """三种排除标记各一条：两个投递点（删除/消息阈值）均不投递 settle。"""
    calls = _capture_enqueue(monkeypatch, _settings())
    service = ChatService(None)
    session = _session(**marker)

    await service._enqueue_memory_summary(session)
    await service._maybe_enqueue_memory_settle(session)

    assert calls == []


@pytest.mark.asyncio
async def test_settle_task_body_skips_agentteams_synthetic(monkeypatch) -> None:
    """任务体双保险：直接调用任务（绕过入口排除）命中标记即幂等返回。"""
    chat_session = _session(mode="agentteams", status="system", session_id="agentteams:case-9")
    fake_db = SimpleNamespace(scalar=AsyncMock(return_value=chat_session))

    class _Ctx:
        async def __aenter__(self) -> SimpleNamespace:
            return fake_db

        async def __aexit__(self, *exc: object) -> bool:
            return False

    monkeypatch.setattr(
        "cygnusx.infrastructure.database.session.get_session_factory",
        lambda: (lambda: _Ctx()),
    )

    result = await _settle_session_memory_v2("agentteams:case-9")

    assert result == {"status": "skipped_agentteams"}
    # 只读了会话行即返回，未继续取消息、未写 settlement、未动游标
    assert fake_db.scalar.await_count == 1


@pytest.mark.asyncio
async def test_normal_session_settle_behavior_unchanged(monkeypatch) -> None:
    """回归：普通会话两个投递点行为不变（v2 开启时正常入队）。"""
    calls = _capture_enqueue(monkeypatch, _settings())
    service = ChatService(None)

    await service._enqueue_memory_summary(_session())
    await service._maybe_enqueue_memory_settle(_session())

    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("extraction", ["[]", "invalid", "{}", "[null]", "provider_error"])
async def test_settle_ignores_compaction_events_and_advances_message_cursor(
    monkeypatch, extraction: str
) -> None:
    """压缩事件属于审计流，settle 仍只消费 chat_messages 的新消息区间。"""
    from cygnusx.infrastructure.ai_provider.litellm_provider import LiteLLMProvider

    extraction_failures = SimpleNamespace(add=MagicMock())
    monkeypatch.setattr(
        "cygnusx.infrastructure.celery_app.tasks.memory._settle_extract_failed", extraction_failures
    )
    chat_session = _session(
        session_id="chat-compaction-memory-1",
        message_count=2,
        last_settled_message_id=None,
        user_id="user-1",
        agent_id="agent-1",
    )
    messages = [
        SimpleNamespace(message_id="memory-user-1", role="user", content="保留 GRCh38"),
        SimpleNamespace(message_id="memory-assistant-1", role="assistant", content="已记录"),
    ]
    compaction_event = SimpleNamespace(
        message_id="memory-assistant-1",
        event_type="context_compacted",
        payload={"tokens_before": 1200, "tokens_after": 400},
    )

    class _Scalars:
        def all(self):
            return messages

    class _Db:
        def __init__(self, *, final: bool) -> None:
            self.final = final
            self.scalar_calls = 0
            self.committed = False
            self.added = []

        async def scalar(self, statement):
            sql = str(statement)
            assert "chat_message_events" not in sql
            if self.final:
                assert self.scalar_calls == 0
                self.scalar_calls += 1
                return chat_session
            self.scalar_calls += 1
            if self.scalar_calls == 1:
                return chat_session
            # No existing settlement for this message range.
            return None

        async def scalars(self, statement):
            sql = str(statement)
            assert "chat_messages" in sql
            assert "chat_message_events" not in sql
            assert compaction_event.event_type == "context_compacted"
            return _Scalars()

        def add(self, value):
            self.added.append(value)

        async def flush(self):
            return None

        async def commit(self):
            self.committed = True

    databases: list[_Db] = []

    def session_factory():
        db = _Db(final=bool(databases))
        databases.append(db)

        class _Context:
            async def __aenter__(self):
                return db

            async def __aexit__(self, *exc):
                return False

        return _Context()

    monkeypatch.setattr(
        "cygnusx.infrastructure.database.session.get_session_factory",
        lambda: session_factory,
    )
    monkeypatch.setattr(
        LiteLLMProvider,
        "chat",
        AsyncMock(
            side_effect=RuntimeError("provider unavailable")
            if extraction == "provider_error" else None,
            return_value={"choices": [{"message": {"content": extraction}}]},
        ),
    )
    monkeypatch.setattr(
        "cygnusx.core.config.get_settings",
        lambda: SimpleNamespace(
            memory_v2_enabled=True, memory_focus_per_project_enabled=False,
            memory_settle_candidate_limit=30,
            memory_settle_max_messages=30,
            memory_settle_max_chars=8000,
            memory_extraction_model="memory-test-model",
            memory_settle_min_new_messages=2,
        ),
    )

    monkeypatch.setattr(
        "cygnusx.application.services.site_settings_service.SiteSettingsService.is_agent_memory_enabled",
        AsyncMock(return_value=True),
    )
    result = await _settle_session_memory_v2(chat_session.session_id)

    if extraction != "[]":
        assert result == {"status": "error", "detail": "事实抽取失败，区间未结算"}
        assert len(databases) == 1
        assert databases[0].added == []
        assert databases[0].committed is False
        assert chat_session.last_settled_message_id is None
        extraction_failures.add.assert_called_once_with(1)
        return

    assert result == {
        "status": "settled",
        "facts": 0,
        "processed_messages": 2,
    }
    assert len(databases) == 2
    assert databases[1].committed is True
    extraction_failures.add.assert_not_called()
    assert chat_session.last_settled_message_id == "memory-assistant-1"


@pytest.mark.asyncio
async def test_v2_off_never_enqueues_settle(monkeypatch) -> None:
    """回归：v2 off 路径零变化——普通与合成会话都不投递。"""
    calls = _capture_enqueue(monkeypatch, _settings(memory_v2_enabled=False))
    service = ChatService(None)

    await service._enqueue_memory_summary(_session())
    await service._maybe_enqueue_memory_settle(_session())
    await service._enqueue_memory_summary(_session(mode="agentteams"))

    assert calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_idle_tail_scan_enqueues_force_tail_and_excludes_synthetic(monkeypatch) -> None:
    from contextlib import asynccontextmanager

    normal = _session(
        session_id="idle-normal",
        last_message_at=SimpleNamespace(),
    )
    synthetic = _session(
        session_id="agentteams:idle-case",
        mode="agentteams",
        last_message_at=SimpleNamespace(),
    )
    db = SimpleNamespace(
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [normal, synthetic])),
    )
    settings = _settings(
        memory_settle_tail_enabled=True,
        memory_settle_idle_seconds=1800,
        memory_settle_tail_min_messages=2,
        memory_settle_tail_scan_limit=200,
    )
    calls = []

    @asynccontextmanager
    async def session_context():
        yield db

    monkeypatch.setattr("cygnusx.core.config.get_settings", lambda: settings)
    monkeypatch.setattr("cygnusx.infrastructure.database.session.get_session_factory", lambda: session_context)
    monkeypatch.setattr(
        "cygnusx.application.services.site_settings_service.SiteSettingsService.is_agent_memory_enabled",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "cygnusx.infrastructure.task_queue.dispatcher.enqueue_task",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    assert await _settle_idle_sessions() == {"status": "queued", "queued": 1}
    assert calls[0][0][1] == "idle-normal"
    assert calls[0][1] == {"force_tail": True, "queue": "analysis"}


def test_is_agentteams_synthetic_session_predicate() -> None:
    assert is_agentteams_synthetic_session(_session(mode="agentteams"))
    assert is_agentteams_synthetic_session(_session(status="system"))
    assert is_agentteams_synthetic_session(_session(session_id="agentteams:case-1"))
    assert not is_agentteams_synthetic_session(_session())


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("v2,site", [(False, True), (True, False)])
async def test_queued_settlement_rechecks_runtime_gates(monkeypatch, v2, site) -> None:
    from contextlib import asynccontextmanager

    db = SimpleNamespace(scalar=AsyncMock(return_value=_session()), scalars=AsyncMock())

    @asynccontextmanager
    async def session_context():
        yield db

    monkeypatch.setattr("cygnusx.core.config.get_settings", lambda: _settings(memory_v2_enabled=v2))
    monkeypatch.setattr(
        "cygnusx.infrastructure.database.session.get_session_factory", lambda: session_context
    )
    monkeypatch.setattr(
        "cygnusx.application.services.site_settings_service.SiteSettingsService.is_agent_memory_enabled",
        AsyncMock(return_value=site),
    )
    assert await _settle_session_memory_v2("chat-normal-1") == {"status": "disabled"}
    db.scalars.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("v2", [True, False])
async def test_backfill_selects_current_storage_and_counts_only_successes(monkeypatch, v2) -> None:
    from contextlib import asynccontextmanager

    from cygnusx.infrastructure.celery_app.tasks.memory import _backfill_embeddings

    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    result = {"status": "completed", "updated": 1, "failed": 1, "skipped": 0}
    run = AsyncMock(return_value=result)
    published = []
    selected = []

    class Maintenance:
        def __init__(self, session, *, storage):
            assert session is db
            selected.append(storage)
            self.backfill = run

        def publish_report(self, value):
            assert db.commit.await_count == 1
            published.append(value)

    @asynccontextmanager
    async def session_context():
        yield db

    monkeypatch.setattr(
        "cygnusx.core.config.get_settings",
        lambda: _settings(memory_v2_enabled=v2, agent_memory_embedding_model="memory-embedding",
                          agent_memory_semantic_retrieval_enabled=not v2),
    )
    monkeypatch.setattr("cygnusx.infrastructure.database.session.get_session_factory", lambda: session_context)
    monkeypatch.setattr("cygnusx.application.services.memory_embedding_service.MemoryEmbeddingService", Maintenance)
    assert await _backfill_embeddings(20) == result
    assert selected == ["facts" if v2 else "legacy"]
    run.assert_awaited_once_with(20, mode="missing", dry_run=False)
    assert published == [result]
    db.rollback.assert_not_awaited()


@pytest.mark.unit
def test_settlement_batches_cover_backlog_without_tail_skips() -> None:
    from cygnusx.infrastructure.celery_app.tasks.memory import _settlement_batch

    messages = [SimpleNamespace(message_id=str(i), role="user", content=f"fact {i}")
                for i in range(75)]
    covered = []
    pending = list(messages)
    while pending:
        batch = _settlement_batch(pending, max_messages=30, max_chars=8000)
        assert batch == pending[:len(batch)]
        assert len(batch) <= 30
        covered.extend(batch)
        pending = pending[len(batch):]
    assert covered == messages
    assert "fact 0" in _conversation_text(messages[:30])
    assert "fact 74" not in _conversation_text(messages[:30])


@pytest.mark.unit
def test_settlement_budget_keeps_whole_messages_and_rejects_oversized_input() -> None:
    from cygnusx.infrastructure.celery_app.tasks.memory import _settlement_batch

    messages = [SimpleNamespace(role="user", content="abc"),
                SimpleNamespace(role="assistant", content="xyz")]
    assert _settlement_batch(messages, max_messages=30, max_chars=12) == messages[:1]
    with pytest.raises(ValueError):
        _settlement_batch(messages, max_messages=30, max_chars=3)
    with pytest.raises(ValueError):
        _conversation_text(messages, limit=12)


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("per_project", [False, True])
async def test_one_extraction_persists_episode_focus_and_cursor_together(monkeypatch, per_project) -> None:
    import json
    from contextlib import asynccontextmanager

    from cygnusx.application.services.agent_memory_service import AgentMemoryService
    from cygnusx.infrastructure.ai_provider.litellm_provider import LiteLLMProvider
    from cygnusx.infrastructure.memory.fact_store import PostgresFactStore

    chat = _session(user_id="owner", project_id="project-a", last_settled_message_id=None)
    messages = [SimpleNamespace(message_id=f"m{i}", role="user", content="继续分析")
                for i in range(4)]
    read = SimpleNamespace(
        scalar=AsyncMock(side_effect=[chat, None, "上次完成比对"]),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: messages)),
    )
    write = SimpleNamespace(
        scalar=AsyncMock(side_effect=[SimpleNamespace(version=3), chat]),
        add=lambda value: None, flush=AsyncMock(), execute=AsyncMock(), commit=AsyncMock(),
    )
    databases = iter([read, write])

    @asynccontextmanager
    async def session_context():
        yield next(databases)

    monkeypatch.setattr("cygnusx.core.config.get_settings", lambda: _settings(
        memory_settle_max_messages=30, memory_settle_max_chars=8000,
        memory_extraction_model="test-model", memory_focus_per_project_enabled=per_project,
    ))
    monkeypatch.setattr(
        "cygnusx.infrastructure.database.session.get_session_factory", lambda: session_context
    )
    monkeypatch.setattr(
        "cygnusx.application.services.site_settings_service.SiteSettingsService.is_agent_memory_enabled",
        AsyncMock(return_value=True),
    )
    provider = AsyncMock(return_value={"choices": [{"message": {"content": json.dumps({
        "facts": [], "episode": "完成比对和质控；待分析批次效应", "current_focus": "完成 RNA 分析"
    })}}]})
    monkeypatch.setattr(LiteLLMProvider, "chat", provider)
    insert = AsyncMock(return_value=SimpleNamespace(id=42))
    monkeypatch.setattr(PostgresFactStore, "insert", insert)
    monkeypatch.setattr(AgentMemoryService, "ensure_focus_block", AsyncMock())
    update_block = AsyncMock()
    monkeypatch.setattr(AgentMemoryService, "update_memory_block", update_block)

    result = await _settle_session_memory_v2(chat.session_id)
    assert result["status"] == "settled"
    provider.assert_awaited_once()
    assert "上次完成比对" in provider.await_args.args[0][0]["content"]
    episode = insert.await_args.args[0]
    assert episode.scope == "episode" and episode.project_id == "project-a"
    assert episode.source_session_id == chat.session_id
    assert episode.source_message_ids == [f"m{i}" for i in range(4)]
    update_block.assert_awaited_once_with("owner", "agent-scrna", "current_focus", "完成 RNA 分析", 3, project_id="project-a")
    assert chat.last_settled_message_id == "m3"
    write.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_recall_batch_replay_does_not_double_count(monkeypatch) -> None:
    from contextlib import asynccontextmanager

    from cygnusx.infrastructure.celery_app.tasks.memory import _record_recall_batch
    from cygnusx.infrastructure.memory.fact_store import PostgresFactStore

    db = SimpleNamespace(scalar=AsyncMock(side_effect=["batch-id", None]), commit=AsyncMock())

    @asynccontextmanager
    async def context():
        yield db

    monkeypatch.setattr("cygnusx.core.config.get_settings", lambda: _settings())
    monkeypatch.setattr("cygnusx.infrastructure.database.session.get_session_factory", lambda: context)
    monkeypatch.setattr(
        "cygnusx.application.services.memory_runtime_policy.is_memory_runtime_enabled",
        AsyncMock(return_value=True),
    )
    touch = AsyncMock()
    monkeypatch.setattr(PostgresFactStore, "touch_recalled", touch)
    assert await _record_recall_batch("owner", [1, 2], "batch-id") == {"status": "recorded"}
    assert await _record_recall_batch("owner", [1, 2], "batch-id") == {"status": "already_recorded"}
    touch.assert_awaited_once_with([1, 2], user_id="owner")
    db.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["add", "update", "duplicate", "unknown_target", "wrong_scope", "stale"])
async def test_settlement_uses_model_arbitration_and_rejects_untrusted_targets(monkeypatch, decision) -> None:
    import json
    from contextlib import asynccontextmanager

    from cygnusx.application.services.agent_memory_service import AgentMemoryService
    from cygnusx.infrastructure.ai_provider.litellm_provider import LiteLLMProvider
    from cygnusx.infrastructure.memory.fact_store import PostgresFactStore

    chat = _session(user_id="owner", project_id="p", last_settled_message_id=None)
    messages = [SimpleNamespace(message_id=f"m{i}", role="user", content="改为 GRCh38")
                for i in range(4)]
    read = SimpleNamespace(
        scalar=AsyncMock(side_effect=[chat, None, None]),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: messages)),
    )
    write = SimpleNamespace(scalar=AsyncMock(return_value=chat), flush=AsyncMock(),
                            add=lambda value: None, commit=AsyncMock(), rollback=AsyncMock())
    databases = iter([read, write])

    @asynccontextmanager
    async def context():
        yield next(databases)

    monkeypatch.setattr("cygnusx.core.config.get_settings", lambda: _settings(
        memory_settle_max_messages=30, memory_settle_max_chars=8000,
        memory_extraction_model="test-model",
    ))
    monkeypatch.setattr("cygnusx.infrastructure.database.session.get_session_factory", lambda: context)
    monkeypatch.setattr(
        "cygnusx.application.services.site_settings_service.SiteSettingsService.is_agent_memory_enabled",
        AsyncMock(return_value=True),
    )
    candidate = SimpleNamespace(id=7, scope="profile" if decision == "wrong_scope" else "preference",
                                content="常用 GRCh37")
    candidates = AsyncMock(return_value=[candidate])
    monkeypatch.setattr(PostgresFactStore, "settlement_candidates", candidates)
    action = decision if decision in {"add", "update", "duplicate"} else "update"
    target = None if action == "add" else (88 if decision == "unknown_target" else 7)
    fact = {"content": "改为 GRCh38", "scope": "preference", "action": action, "target_id": target}
    provider = AsyncMock(return_value={"choices": [{"message": {"content": json.dumps({
        "facts": [fact], "episode": None, "current_focus": None,
    })}}]})
    monkeypatch.setattr(LiteLLMProvider, "chat", provider)
    monkeypatch.setattr(AgentMemoryService, "_embed", AsyncMock(return_value=[]))
    insert = AsyncMock()
    supersede = AsyncMock(side_effect=ValueError("stale") if decision == "stale" else None)
    monkeypatch.setattr(PostgresFactStore, "insert", insert)
    monkeypatch.setattr(PostgresFactStore, "supersede", supersede)

    result = await _settle_session_memory_v2(chat.session_id)
    provider.assert_awaited_once()
    assert "常用 GRCh37" in provider.await_args.args[0][0]["content"]
    candidates.assert_awaited_once_with("owner", "agent-scrna", project_id="p", limit=30)
    if decision in {"unknown_target", "wrong_scope", "stale"}:
        assert result["status"] == "error"
        assert chat.last_settled_message_id is None
        write.commit.assert_not_awaited()
        if decision == "stale":
            write.rollback.assert_awaited_once()
    else:
        assert result["status"] == "settled"
        assert chat.last_settled_message_id == "m3"
        assert insert.await_count == int(decision == "add")
        assert supersede.await_count == int(decision == "update")
        write.commit.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_missing_cursor_does_not_silently_replay_old_history(monkeypatch) -> None:
    from contextlib import asynccontextmanager

    chat = _session(last_settled_message_id="removed-message")
    db = SimpleNamespace(scalar=AsyncMock(side_effect=[chat, None]), scalars=AsyncMock(
        return_value=SimpleNamespace(all=lambda: [SimpleNamespace(message_id="old-message")])
    ))

    @asynccontextmanager
    async def context():
        yield db

    monkeypatch.setattr("cygnusx.core.config.get_settings", lambda: _settings())
    monkeypatch.setattr("cygnusx.infrastructure.database.session.get_session_factory", lambda: context)
    monkeypatch.setattr(
        "cygnusx.application.services.site_settings_service.SiteSettingsService.is_agent_memory_enabled",
        AsyncMock(return_value=True),
    )
    assert await _settle_session_memory_v2(chat.session_id) == {
        "status": "error", "detail": "沉淀游标消息缺失，未重放历史"
    }
    assert chat.last_settled_message_id == "removed-message"
    assert db.scalar.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("observe,site", [(False, True), (True, False), (True, True)])
async def test_embedding_coverage_obeys_observation_and_runtime_gates(monkeypatch, observe, site):
    from contextlib import asynccontextmanager
    from unittest.mock import Mock

    from cygnusx.infrastructure.celery_app.tasks.memory import _collect_embedding_coverage

    db = object()

    @asynccontextmanager
    async def session_context():
        yield db

    monkeypatch.setattr("cygnusx.core.config.get_settings", lambda: SimpleNamespace(memory_embedding_coverage_enabled=observe))
    monkeypatch.setattr("cygnusx.infrastructure.database.session.get_session_factory", lambda: session_context)
    gate = AsyncMock(return_value=site)
    monkeypatch.setattr("cygnusx.application.services.memory_runtime_policy.is_memory_runtime_enabled", gate)
    coverage = AsyncMock(return_value={"status": "collected"})
    constructor = Mock(return_value=SimpleNamespace(coverage=coverage))
    monkeypatch.setattr("cygnusx.application.services.memory_embedding_service.MemoryEmbeddingService", constructor)
    assert (await _collect_embedding_coverage())["status"] == ("collected" if observe and site else "disabled")
    if not observe:
        gate.assert_not_awaited()
    if not (observe and site):
        constructor.assert_not_called()
    else:
        constructor.assert_called_once_with(db)
        coverage.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_failed_backfill_commit_rolls_back_and_does_not_publish_success(monkeypatch):
    from contextlib import asynccontextmanager
    from unittest.mock import Mock

    from cygnusx.infrastructure.celery_app.tasks.memory import _backfill_embeddings

    db = SimpleNamespace(commit=AsyncMock(side_effect=RuntimeError("private database parameters")), rollback=AsyncMock())
    maintenance = SimpleNamespace(backfill=AsyncMock(return_value={"status": "completed", "updated": 1}), publish_report=Mock())

    @asynccontextmanager
    async def session_context():
        yield db

    monkeypatch.setattr("cygnusx.core.config.get_settings", lambda: _settings(agent_memory_embedding_model="new"))
    monkeypatch.setattr("cygnusx.infrastructure.database.session.get_session_factory", lambda: session_context)
    monkeypatch.setattr("cygnusx.application.services.memory_embedding_service.MemoryEmbeddingService", lambda *args, **kwargs: maintenance)
    warning = Mock()
    monkeypatch.setattr("cygnusx.infrastructure.celery_app.tasks.memory.logger.warning", warning)
    result = await _backfill_embeddings(1, mode="mismatch")
    assert result == {"status": "error", "error_type": "RuntimeError"}
    db.rollback.assert_awaited_once()
    maintenance.publish_report.assert_not_called()
    assert "private database parameters" not in str(warning.call_args)
