"""Agent 跨会话长期记忆的无数据库安全契约测试。"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cygnusx.application.services.agent_memory_service import AgentMemoryService
from cygnusx.application.services.agent_memory_tool_service import AgentMemoryToolService
from cygnusx.core.exceptions import BusinessError
from cygnusx.infrastructure.database.models.agent_memory import (
    EMBEDDING_DIMENSIONS,
    AgentMemoryModel,
)


def test_memory_content_rejects_sensitive_credentials() -> None:
    with pytest.raises(BusinessError, match="敏感凭据"):
        AgentMemoryService._validate_content("我的 API_KEY 是 sk-super-secret-token-value")


def test_memory_content_and_scope_limits_are_enforced() -> None:
    assert AgentMemoryService._validate_content("用户常用小鼠脑 10x V3 数据") == "用户常用小鼠脑 10x V3 数据"
    assert AgentMemoryService._validate_scope("project") == "project"

    with pytest.raises(BusinessError, match="不能超过"):
        AgentMemoryService._validate_content("a" * 201)
    with pytest.raises(BusinessError, match="不支持的记忆范围"):
        AgentMemoryService._validate_scope("temporary")


def test_memory_keywords_are_bounded_and_deduplicated() -> None:
    keywords = AgentMemoryService._normalize_keywords(
        ["Mouse", "mouse", "10x", "GRCh38", "RNA", "single-cell", "project", "brain", "extra"],
        "ignored",
    )

    assert keywords == ["mouse", "10x", "grch38", "rna", "single-cell", "project", "brain", "extra"]


def test_profile_memory_is_shared_but_project_memory_is_agent_scoped() -> None:
    context = type("Context", (), {"agent_id": "agent-scrna"})()

    assert AgentMemoryToolService._memory_agent_id("profile", context) is None
    assert AgentMemoryToolService._memory_agent_id("preference", context) is None
    assert AgentMemoryToolService._memory_agent_id("project", context) == "agent-scrna"


def test_conflict_adjudication_parser_accepts_only_supported_actions() -> None:
    assert AgentMemoryService._parse_conflict_action(
        {"choices": [{"message": {"content": '{"action":"coexist"}'}}]}
    ) == "coexist"
    assert AgentMemoryService._parse_conflict_action(
        {"choices": [{"message": {"content": '{"action":"unsafe"}'}}]}
    ) == "update"


@pytest.mark.asyncio
async def test_semantic_rank_prefers_embedding_similarity(monkeypatch) -> None:
    settings = SimpleNamespace(
        agent_memory_semantic_retrieval_enabled=True, memory_embedding_model_filter_enabled=False,
        agent_memory_embedding_model="text-embedding-3-small",
        agent_memory_semantic_candidate_limit=100,
    )
    monkeypatch.setattr(
        "cygnusx.application.services.agent_memory_service.get_settings", lambda: settings
    )

    class EmbeddingClient:
        async def embeddings(self, _text: str, *, model: str) -> list[float]:
            assert model == "text-embedding-3-small"
            return [1.0, *([0.0] * (EMBEDDING_DIMENSIONS - 1))]

    now = datetime.now(UTC)
    lexical_only = AgentMemoryModel(
        content="小鼠脑单细胞项目",
        keywords=["小鼠"],
        embedding=[0.0, 1.0, *([0.0] * (EMBEDDING_DIMENSIONS - 2))],
        updated_at=now,
    )
    semantic_match = AgentMemoryModel(
        content="肿瘤转录组分析偏好",
        keywords=[],
        embedding=[1.0, *([0.0] * (EMBEDDING_DIMENSIONS - 1))],
        updated_at=now,
    )
    service = AgentMemoryService(AsyncMock(), embedding_client=EmbeddingClient())

    ranked = await service._semantic_rank(
        [lexical_only, semantic_match], "请继续这个转录组项目", ["项目"], 2
    )

    assert ranked == [semantic_match, lexical_only]


@pytest.mark.asyncio
async def test_embedding_failure_returns_empty_vector_for_keyword_fallback(monkeypatch) -> None:
    settings = SimpleNamespace(
        agent_memory_semantic_retrieval_enabled=True, memory_embedding_model_filter_enabled=False,
        agent_memory_embedding_model="text-embedding-3-small",
        agent_memory_semantic_candidate_limit=100,
    )
    monkeypatch.setattr(
        "cygnusx.application.services.agent_memory_service.get_settings", lambda: settings
    )

    class BrokenEmbeddingClient:
        async def embeddings(self, _text: str, *, model: str) -> list[float]:
            raise RuntimeError("embedding service unavailable")

    service = AgentMemoryService(AsyncMock(), embedding_client=BrokenEmbeddingClient())

    assert await service._embed("测试") == []


@pytest.mark.asyncio
async def test_wrong_dimension_embedding_returns_empty_vector_for_keyword_fallback(monkeypatch) -> None:
    settings = SimpleNamespace(
        agent_memory_semantic_retrieval_enabled=True, memory_embedding_model_filter_enabled=False,
        agent_memory_embedding_model="text-embedding-3-small",
        agent_memory_semantic_candidate_limit=100,
    )
    monkeypatch.setattr(
        "cygnusx.application.services.agent_memory_service.get_settings", lambda: settings
    )

    class WrongDimensionEmbeddingClient:
        async def embeddings(self, _text: str, *, model: str) -> list[float]:
            assert model == "text-embedding-3-small"
            return [0.1, 0.2]

    service = AgentMemoryService(AsyncMock(), embedding_client=WrongDimensionEmbeddingClient())

    assert await service._embed("测试") == []


# --- M1：v2 共享分区召回两路合并 ---

@pytest.mark.asyncio
async def test_unconfigured_embedding_never_calls_default_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        "cygnusx.application.services.agent_memory_service.get_settings",
        lambda: SimpleNamespace(agent_memory_embedding_model="  "),
    )
    client = AsyncMock()
    assert await AgentMemoryService(AsyncMock(), client)._embed("测试") == []
    client.embeddings.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf")])
async def test_non_finite_embedding_rejected_before_database(monkeypatch, invalid) -> None:
    monkeypatch.setattr(
        "cygnusx.application.services.agent_memory_service.get_settings",
        lambda: SimpleNamespace(agent_memory_embedding_model="verified"),
    )
    client = AsyncMock()
    client.embeddings.return_value = [invalid, *([0.1] * (EMBEDDING_DIMENSIONS - 1))]
    assert await AgentMemoryService(AsyncMock(), client)._embed("测试") == []

def _v2_settings(**overrides) -> SimpleNamespace:
    base = {
        "memory_v2_enabled": True, "memory_focus_per_project_enabled": False,
        "memory_fact_time_decay_lambda": 0.02,
        "agent_memory_embedding_model": "text-embedding-3-small",
        "agent_memory_semantic_retrieval_enabled": True,
        "memory_embedding_model_filter_enabled": False,
        "memory_hybrid_retrieval_enabled": False,
        "agent_memory_semantic_candidate_limit": 100,
        "memory_importance_weight": 0.5,
        "memory_recall_weight": 0.25,
        "memory_recall_boost_scale": 20,
        "memory_recall_tracking_enabled": False,
        "memory_prompt_max_bytes": 6000,
        "memory_prompt_blocks_max_bytes": 2800,
        "memory_prompt_episode_max_bytes": 3200,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class _FixedEmbeddingClient:
    async def embeddings(self, _text: str, *, model: str) -> list[float]:
        return [1.0, *([0.0] * (EMBEDDING_DIMENSIONS - 1))]


def _fact(
    fact_id: int,
    agent_id: str,
    scope: str,
    content: str,
    *,
    similarity: float = 0.9,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=fact_id,
        user_id="user-1",
        agent_id=agent_id,
        scope=scope,
        content=content,
        keywords=[],
        embedding=None,
        embedding_model=None,
        project_id=None,
        source_session_id=None,
        source_message_ids=[],
        confidence=1.0,
        status="active",
        created_at=datetime.now(UTC),
        last_recalled_at=None,
        superseded_by=None,
        similarity=similarity,
        importance=5,
        recall_count=0,
    )


def _patch_fact_store(monkeypatch, partitions: dict[str, list]) -> list[str]:
    """按分区返回预置事实的 FakeStore；返回每次召回命中的分区序列。"""
    calls: list[str] = []

    class FakeStore:
        def __init__(self, _db) -> None:
            pass

        async def search(self, user_id, agent_id, query_vector, limit=10):
            calls.append(agent_id)
            return list(partitions.get(agent_id, []))[:limit]

        async def recent_episodes(self, *args, **kwargs):
            return []

        async def search_keywords(self, user_id, agent_id, terms, limit=10):
            return []

    monkeypatch.setattr(
        "cygnusx.application.services.agent_memory_service.PostgresFactStore", FakeStore
    )
    return calls


class _FakeScalars:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def all(self) -> list:
        return self._rows


def _block(block_id: int, agent_id: str, name: str, content: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=block_id, agent_id=agent_id, block_name=name, project_id=None, content=content, char_limit=2000, version=1
    )


@pytest.mark.asyncio
async def test_v2_search_merges_shared_partition_across_agents(monkeypatch) -> None:
    """agent A 写入共享偏好（agent_id=""），agent B 召回可见，且同分时共享层结果优先。"""
    monkeypatch.setattr(
        "cygnusx.application.services.agent_memory_service.get_settings",
        lambda: _v2_settings(),
    )
    shared_pref = _fact(1, "", "preference", "结果图都用英文标注")
    b_project = _fact(2, "agent-b", "project", "agent-b 的项目事实")
    b_project.created_at = shared_pref.created_at
    calls = _patch_fact_store(monkeypatch, {"": [shared_pref], "agent-b": [b_project]})

    service = AgentMemoryService(AsyncMock(), embedding_client=_FixedEmbeddingClient())
    result = await service.search_memory(user_id="user-1", query="绘图偏好", agent_id="agent-b")

    assert [m["content"] for m in result["memories"]] == [
        "结果图都用英文标注",
        "agent-b 的项目事实",
    ]
    assert calls == ["", "agent-b"]


@pytest.mark.asyncio
async def test_v2_search_keeps_agent_partition_isolated(monkeypatch) -> None:
    """agent 分区事实（project/summary）不被其他 agent 召回。"""
    monkeypatch.setattr(
        "cygnusx.application.services.agent_memory_service.get_settings",
        lambda: _v2_settings(),
    )
    a_project = _fact(3, "agent-a", "project", "agent-a 的项目事实")
    calls = _patch_fact_store(monkeypatch, {"agent-a": [a_project]})

    service = AgentMemoryService(AsyncMock(), embedding_client=_FixedEmbeddingClient())
    result = await service.search_memory(user_id="user-1", query="项目", agent_id="agent-b")

    assert result["memories"] == []
    assert "agent-a" not in calls


@pytest.mark.asyncio
async def test_v2_search_dedupes_when_current_agent_is_shared_partition(monkeypatch) -> None:
    """当前 agent 即共享分区时两路命中同一事实，去重后不重复返回。"""
    monkeypatch.setattr(
        "cygnusx.application.services.agent_memory_service.get_settings",
        lambda: _v2_settings(),
    )
    shared_pref = _fact(1, "", "preference", "结果图都用英文标注")
    calls = _patch_fact_store(monkeypatch, {"": [shared_pref]})

    service = AgentMemoryService(AsyncMock(), embedding_client=_FixedEmbeddingClient())
    result = await service.search_memory(user_id="user-1", query="绘图偏好", agent_id=None)

    assert [m["id"] for m in result["memories"]] == ["1"]
    assert calls == [""]


@pytest.mark.asyncio
async def test_v2_prompt_context_merges_shared_blocks_and_facts(monkeypatch) -> None:
    """build_prompt_context_v2：共享层块 + 当前 agent 块、共享事实 + 分区事实均注入。"""
    monkeypatch.setattr(
        "cygnusx.application.services.agent_memory_service.get_settings",
        lambda: _v2_settings(),
    )
    blocks = [
        _block(1, "", "profile", "用户画像：肿瘤方向 PI"),
        _block(2, "agentteams-manager", "current_focus", "当前关注：协作室交付"),
    ]
    shared_pref = _fact(1, "", "preference", "结果图都用英文标注")
    mgr_fact = _fact(2, "agentteams-manager", "summary", "manager 分区摘要")
    _patch_fact_store(monkeypatch, {"": [shared_pref], "agentteams-manager": [mgr_fact]})

    db = AsyncMock()
    db.scalars = AsyncMock(return_value=_FakeScalars(blocks))
    service = AgentMemoryService(db, embedding_client=_FixedEmbeddingClient())

    content = await service.build_prompt_context_v2("user-1", "agentteams-manager", "画图")

    assert content.startswith("<user_memory>")
    assert content.rstrip().endswith("</user_memory>")
    assert "用户画像：肿瘤方向 PI" in content
    assert "当前关注：协作室交付" in content
    assert "结果图都用英文标注" in content
    assert "manager 分区摘要" in content
    # 共享层块排前
    assert content.index("用户画像") < content.index("当前关注")


@pytest.mark.asyncio
async def test_v2_prompt_context_omits_oversized_block_without_partial_text(monkeypatch) -> None:
    """超长块整块省略，保留可以容纳的完整偏好与边界。"""
    monkeypatch.setattr(
        "cygnusx.application.services.agent_memory_service.get_settings",
        lambda: _v2_settings(),
    )
    blocks = [_block(1, "", "profile", "长" * 5000), _block(2, "", "preferences", "保留完整偏好")]
    _patch_fact_store(monkeypatch, {})

    db = AsyncMock()
    db.scalars = AsyncMock(return_value=_FakeScalars(blocks))
    service = AgentMemoryService(db, embedding_client=_FixedEmbeddingClient())

    content = await service.build_prompt_context_v2("user-1", "agent-b", "任意问题")

    assert len(content.encode("utf-8")) <= 3200
    assert content.startswith("<user_memory>")
    assert content.endswith("</user_memory>")
    assert "长" * 10 not in content
    assert "保留完整偏好" in content


@pytest.mark.asyncio
async def test_v2_off_search_does_not_touch_fact_store(monkeypatch) -> None:
    """v2 off 回归：旧 agent_memories 链路不变，完全不经过 v2 FactStore。"""
    monkeypatch.setattr(
        "cygnusx.application.services.agent_memory_service.get_settings",
        lambda: _v2_settings(
            memory_v2_enabled=False,
            agent_memory_semantic_retrieval_enabled=False,
            agent_memory_embedding_model="",
        ),
    )

    class _ForbiddenStore:
        def __init__(self, _db) -> None:
            raise AssertionError("v2 off 不应触达 FactStore")

    monkeypatch.setattr(
        "cygnusx.application.services.agent_memory_service.PostgresFactStore", _ForbiddenStore
    )
    db = AsyncMock()
    db.scalars = AsyncMock(return_value=_FakeScalars([]))
    service = AgentMemoryService(db, embedding_client=_FixedEmbeddingClient())

    result = await service.search_memory(user_id="user-1", query="偏好", agent_id="agent-b")

    assert result == {"memories": [], "count": 0}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_v2_keyword_fallback_reaches_tool_and_prompt(monkeypatch) -> None:
    monkeypatch.setattr(
        "cygnusx.application.services.agent_memory_service.get_settings",
        lambda: _v2_settings(),
    )
    calls = []
    fact = _fact(41, "", "preference", "用户常用 GRCh38")

    class KeywordStore:
        def __init__(self, _db):
            pass

        async def recent_episodes(self, *args, **kwargs):
            return []

        async def search_keywords(self, user_id, agent_id, terms, limit=10):
            calls.append((user_id, agent_id, terms))
            return [fact] if agent_id == "" else []

        async def search(self, *args, **kwargs):
            raise AssertionError("No vector query is allowed without an embedding")

    monkeypatch.setattr(
        "cygnusx.application.services.agent_memory_service.PostgresFactStore", KeywordStore
    )
    db = SimpleNamespace(scalars=AsyncMock(return_value=_FakeScalars([])))
    service = AgentMemoryService(db)
    service._embed = AsyncMock(return_value=[])
    result = await service.search_memory(user_id="user-1", query="GRCh38", agent_id="agent-b")
    assert result["memories"][0]["content"] == fact.content
    prompt = await service.build_prompt_context_v2("user-1", "agent-b", "GRCh38")
    assert fact.content in prompt
    assert calls == [("user-1", partition, ["grch38"]) for partition in ("", "agent-b", "", "agent-b")]


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("matched", [True, False])
async def test_v2_forget_archives_only_owned_fact(monkeypatch, matched: bool) -> None:
    from sqlalchemy.dialects import postgresql

    from cygnusx.core.exceptions import NotFoundError

    monkeypatch.setattr(
        "cygnusx.application.services.agent_memory_service.get_settings",
        lambda: SimpleNamespace(memory_v2_enabled=True, memory_focus_per_project_enabled=False, memory_forget_residual_scan_enabled=False),
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(rowcount=int(matched))),
        flush=AsyncMock(),
    )
    service = AgentMemoryService(db)
    if matched:
        result = await service.forget_memory(user_id="owner", memory_id="42")
        assert result == {"memory_id": "42", "forgotten": True, "scan_status": "disabled", "residual_hints": []}
        db.flush.assert_awaited_once()
    else:
        with pytest.raises(NotFoundError):
            await service.forget_memory(user_id="owner", memory_id="42")
        db.flush.assert_not_awaited()
    statement = db.execute.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "memory_facts.user_id =" in str(compiled)
    assert "memory_facts.id =" in str(compiled)
    assert set(compiled.params.values()) == {"owner", 42, "archived"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_blocks_uses_conflict_safe_shared_and_agent_partitions() -> None:
    from sqlalchemy.dialects import postgresql

    db = SimpleNamespace(execute=AsyncMock(), flush=AsyncMock())
    await AgentMemoryService(db).ensure_memory_blocks("user-1", "agent-b")
    compiled = db.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    assert "ON CONFLICT (user_id, agent_id, block_name) WHERE project_id IS NULL DO NOTHING" in str(compiled)
    params = compiled.params
    assert [(params[f"agent_id_m{i}"], params[f"block_name_m{i}"]) for i in range(3)] == [
        ("", "profile"), ("", "preferences"), ("agent-b", "current_focus")
    ]


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("name,partition", [("profile", ""), ("preferences", ""), ("current_focus", "agent-b")])
@pytest.mark.parametrize("updated", [True, False])
async def test_block_update_normalizes_partition_and_preserves_version_lock(
    monkeypatch, name: str, partition: str, updated: bool
) -> None:
    from sqlalchemy.dialects import postgresql

    block = SimpleNamespace(
        id=12, user_id="owner", agent_id=partition, block_name=name, project_id=None,
        content="new", char_limit=2000, version=2, created_at=None, updated_at=None,
        status="active", superseded_by=None,
    )
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=block),
        execute=AsyncMock(return_value=SimpleNamespace(rowcount=int(updated))),
        flush=AsyncMock(),
    )
    service = AgentMemoryService(db)
    service.ensure_memory_blocks = AsyncMock()
    if updated:
        result = await service.update_memory_block("owner", "agent-b", name, "new", 1)
        assert result["version"] == 2
    else:
        with pytest.raises(BusinessError, match="并发修改"):
            await service.update_memory_block("owner", "agent-b", name, "new", 1)
    read = db.scalar.await_args_list[0].args[0].compile(dialect=postgresql.dialect())
    assert partition in read.params.values()
    assert "owner" in read.params.values()
    write = db.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    assert "memory_blocks.version =" in str(write)
    assert 1 in write.params.values()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_save_tool_confirms_actual_persisted_content(monkeypatch) -> None:
    service = SimpleNamespace(save_memory=AsyncMock(return_value={
        "memory": {"id": "42", "content": "用户常用 GRCh38"}, "action": "created"
    }))
    tools = AgentMemoryToolService()
    monkeypatch.setattr(tools, "_service", lambda _context: service)
    monkeypatch.setattr(tools, "_project_id", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "cygnusx.application.services.memory_runtime_policy.is_memory_runtime_enabled",
        AsyncMock(return_value=True),
    )
    context = SimpleNamespace(user_id="owner", db=object(), agent_id="a", session_id="s")
    result = await tools.save_memory(user_id="owner", content="用户常用 GRCh38", scope="preference", context=context)
    assert result["content"] == "用户常用 GRCh38"
    assert result["summary"] == "已记住：用户常用 GRCh38"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_recent_episode_injection_does_not_require_query_similarity(monkeypatch) -> None:
    from cygnusx.infrastructure.memory.fact_store import PostgresFactStore

    monkeypatch.setattr(
        "cygnusx.application.services.agent_memory_service.get_settings", lambda: _v2_settings()
    )
    episode = _fact(44, "agent-b", "episode", "上次完成 RNA 质控，遗留批次效应检查")
    recent = AsyncMock(return_value=[episode])
    monkeypatch.setattr(PostgresFactStore, "recent_episodes", recent)
    monkeypatch.setattr(PostgresFactStore, "search_keywords", AsyncMock(return_value=[]))
    service = AgentMemoryService(SimpleNamespace(scalars=AsyncMock(return_value=_FakeScalars([]))))
    service._embed = AsyncMock(return_value=[])
    content = await service.build_prompt_context_v2("owner", "agent-b", "我们上次说到哪了", project_id="project-a")
    assert episode.content in content
    assert content.startswith("<user_memory>") and content.endswith("</user_memory>")
    recent.assert_awaited_once_with("owner", "agent-b", project_id="project-a")


@pytest.mark.unit
def test_injection_reserves_episode_and_preserves_complete_utf8_units() -> None:
    render = AgentMemoryService._render_memory_context
    episode = "### 上次进展\n" + "批次效应待检查。" * 80
    block = "### profile\n" + "研究者。" * 300
    fact = "- 参考基因组是 GRCh38"
    context = render([block], [episode], [fact], max_bytes=4000,
                     block_budget=2800, episode_budget=3200)
    assert len(context.encode()) <= 4000
    assert episode in context
    assert fact in context
    assert block not in context
    assert "研究者。" not in context
    assert context.endswith("</user_memory>")


@pytest.mark.unit
def test_injection_prioritizes_blocks_then_episode_over_optional_fact_text() -> None:
    block, episode = "### profile\n研究者", "### 上次进展\n完成质控"
    oversized_fact = "- " + "不能截断的事实" * 1000
    context = AgentMemoryService._render_memory_context(
        [block], [episode], [oversized_fact], max_bytes=6000,
        block_budget=2800, episode_budget=3200,
    )
    assert block in context and episode in context
    assert context.index(block) < context.index(episode)
    assert "不能截断的事实" not in context
    assert AgentMemoryService._render_memory_context(
        ["too large" * 1000], [], [], max_bytes=512, block_budget=200, episode_budget=0
    ) == ""


@pytest.mark.unit
def test_compound_ranking_rewards_importance_and_recall_without_reviving_irrelevance(monkeypatch) -> None:
    monkeypatch.setattr(
        "cygnusx.application.services.agent_memory_service.get_settings", lambda: _v2_settings()
    )
    plain = _fact(1, "agent-b", "project", "plain")
    important = _fact(2, "agent-b", "project", "important")
    recalled = _fact(3, "agent-b", "project", "recalled")
    irrelevant = _fact(4, "agent-b", "project", "irrelevant", similarity=0)
    for item in (important, recalled, irrelevant):
        item.created_at = plain.created_at
    important.importance = 10
    recalled.recall_count = 20
    irrelevant.importance = 10
    irrelevant.recall_count = 1000000
    ranked = AgentMemoryService._rank_facts([plain, important, recalled, irrelevant])
    assert ranked.index(plain) > ranked.index(important)
    assert ranked.index(plain) > ranked.index(recalled)
    assert ranked[-1] is irrelevant


@pytest.mark.unit
def test_render_reports_only_facts_and_episodes_actually_included() -> None:
    fact_indices, episode_indices = [], []
    AgentMemoryService._render_memory_context(
        [], ["recent episode"], ["x" * 2000, "fits"], max_bytes=512,
        block_budget=0, episode_budget=100,
        included_fact_indices=fact_indices, included_episode_indices=episode_indices,
    )
    assert fact_indices == [1] and episode_indices == [0]
