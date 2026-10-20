"""SQL-backed residual visibility, literal matching, failed scan savepoints and user actions."""

from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import text

from cygnusx.application.services.agent_memory_service import AgentMemoryService
from cygnusx.application.services.memory_residual_service import MemoryResidualService
from cygnusx.core.exceptions import BusinessError, NotFoundError
from cygnusx.infrastructure.database.models.agent_memory import MemoryBlockModel, MemoryFactModel
from cygnusx.infrastructure.memory.fact_store import MemoryFactCreate, PostgresFactStore

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def _fact(
    db, content, *, owner="owner", agent="a", project="p", scope="summary", keywords=None
):
    return await PostgresFactStore(db).insert(
        MemoryFactCreate(
            user_id=owner,
            agent_id=agent,
            project_id=project,
            scope=scope,
            content=content,
            keywords=keywords or [],
        )
    )


async def test_forget_reports_only_owned_visible_active_residuals_without_rewriting(
    fact_database,
    residual_settings,
):
    session, db = fact_database
    service = AgentMemoryService(db)
    source = await _fact(db, "常用 GRCh38", keywords=["GRCh38"])
    expected = [
        await _fact(db, "summary about GRCh38"),
        await _fact(db, "episode about GRCh38", scope="episode"),
        await _fact(db, "global GRCh38", project=None),
        await _fact(db, "GRCh38 preference", scope="preference"),
    ]
    hidden = [
        await _fact(db, "GRCh38 project q", project="q"),
        await _fact(db, "GRCh38 other agent", agent="b"),
        await _fact(db, "GRCh38 other owner", owner="other"),
        await _fact(db, "GRCh38 old archived"),
    ]
    session.get(MemoryFactModel, hidden[-1].id).status = "archived"
    shared = await service.update_memory_block("owner", "a", "profile", "GRCh38 研究", 1)
    focus = await service.update_memory_block(
        "owner", "a", "current_focus", "GRCh38 当前项目", 1, project_id="p"
    )
    await service.update_memory_block(
        "owner", "a", "current_focus", "GRCh38 其他项目", 1, project_id="q"
    )
    await service.update_memory_block("other", "a", "profile", "GRCh38 外部", 1)
    session.commit()
    report = await service.forget_memory(user_id="owner", memory_id=str(source.id))
    session.commit()
    hints = report["residual_hints"]
    assert report["forgotten"] and report["scan_status"] == "complete"
    assert {item["id"] for item in hints if item["kind"] != "block"} == {f.id for f in expected}
    assert {item["id"] for item in hints if item["kind"] == "block"} == {shared["id"], focus["id"]}
    assert all(0 < len(item["excerpt"]) <= 60 for item in hints)
    assert session.get(MemoryFactModel, source.id).status == "archived"
    assert all(session.get(MemoryFactModel, fact.id).status == "active" for fact in expected)
    assert session.get(MemoryBlockModel, shared["id"]).content == "GRCh38 研究"
    # Once manually archived, a candidate must disappear on a repeated residual scan.
    await service.delete_memory("owner", str(expected[0].id))
    repeated = await service.forget_memory(user_id="owner", memory_id=str(source.id))
    assert expected[0].id not in {
        h["id"] for h in repeated["residual_hints"] if h["kind"] != "block"
    }


async def test_scan_disabled_still_archives_without_loading_source(
    fact_database,
    residual_settings,
    monkeypatch,
):
    session, db = fact_database
    source = await _fact(db, "GRCh38 source")
    session.commit()
    residual_settings.memory_forget_residual_scan_enabled = False
    scan = AsyncMock()
    monkeypatch.setattr(MemoryResidualService, "scan", scan)
    result = await AgentMemoryService(db).forget_memory(user_id="owner", memory_id=str(source.id))
    session.commit()
    assert result["scan_status"] == "disabled" and result["residual_hints"] == []
    scan.assert_not_awaited()
    assert session.get(MemoryFactModel, source.id).status == "archived"


async def test_failed_scan_rolls_back_only_savepoint_and_does_not_log_private_data(
    fact_database,
    residual_settings,
    monkeypatch,
):
    session, db = fact_database
    service = AgentMemoryService(db)
    source = await _fact(db, "GRCh38 source")
    block = await service.update_memory_block("owner", "a", "profile", "original", 1)
    session.commit()

    async def fail(_self, *args, **kwargs):
        await db.execute(text("UPDATE memory_blocks SET content='should roll back'"))
        raise RuntimeError("private conversation and API_KEY=sk-private-token")

    warning = Mock()
    monkeypatch.setattr(MemoryResidualService, "scan", fail)
    monkeypatch.setattr("cygnusx.application.services.agent_memory_service.logger.warning", warning)
    result = await service.forget_memory(user_id="owner", memory_id=str(source.id))
    session.commit()
    session.expire_all()
    assert result["scan_status"] == "failed" and result["residual_hints"] == []
    assert session.get(MemoryFactModel, source.id).status == "archived"
    assert session.get(MemoryBlockModel, block["id"]).content == "original"
    assert "private" not in str(warning.call_args) and "conversation" not in str(warning.call_args)


async def test_bounded_hints_literal_wildcards_and_sensitive_excerpt(
    fact_database,
    residual_settings,
):
    session, db = fact_database
    source = await _fact(db, "literal_%_")
    good = await _fact(db, "literal_%_ target")
    await _fact(db, "literalAB")  # '_' and '%' must never act as SQL wildcards.
    sensitive = await _fact(db, "literal_%_ API_KEY=sk-private-example")
    await _fact(db, "literal_%_ third")
    session.commit()
    residual_settings.memory_forget_residual_limit = 2
    result = await AgentMemoryService(db).forget_memory(user_id="owner", memory_id=str(source.id))
    assert result["scan_status"] == "partial"
    assert {hint["id"] for hint in result["residual_hints"]} == {good.id, sensitive.id}
    assert (
        next(h["excerpt"] for h in result["residual_hints"] if h["id"] == sensitive.id)
        == "[可能包含敏感凭据，摘录已隐藏]"
    )


async def test_controlled_scope_does_not_fall_back_to_source_project(
    fact_database, residual_settings
):
    session, db = fact_database
    source = await _fact(db, "GRCh38 source")
    await _fact(db, "GRCh38 hidden p")
    visible = await _fact(db, "GRCh38 visible global", project=None)
    session.commit()
    result = await AgentMemoryService(db).forget_memory(
        user_id="owner", memory_id=str(source.id), agent_id="a", project_id=None
    )
    assert {item["id"] for item in result["residual_hints"]} == {visible.id}
    with pytest.raises(NotFoundError):
        await AgentMemoryService(db).forget_memory(user_id="other", memory_id=str(source.id))


@pytest.mark.parametrize(
    "kind,action", [("block", "open_editor"), ("fact", "archive"), ("episode", "archive")]
)
async def test_residual_click_is_owner_checked_telemetry_without_mutation(
    fact_database,
    residual_settings,
    monkeypatch,
    kind,
    action,
):
    session, db = fact_database
    source = await _fact(db, "source")
    session.get(MemoryFactModel, source.id).status = "archived"
    if kind == "block":
        target = await AgentMemoryService(db).update_memory_block(
            "owner", "a", "profile", "profile", 1
        )
        target_id = target["id"]
    else:
        target_id = (
            await _fact(db, "target", scope="episode" if kind == "episode" else "summary")
        ).id
    session.commit()
    counter = Mock()
    monkeypatch.setattr("cygnusx.application.services.memory_residual_service._actions", counter)
    service = MemoryResidualService(db)
    await service.record_action(
        "owner", source_id=source.id, target_id=target_id, kind=kind, action=action
    )
    counter.add.assert_called_once_with(1, {"kind": kind, "action": action})
    with pytest.raises(NotFoundError):
        await service.record_action(
            "other", source_id=source.id, target_id=target_id, kind=kind, action=action
        )
    if kind != "block":
        assert session.get(MemoryFactModel, target_id).status == "active"
    residual_settings.memory_forget_residual_scan_enabled = False
    with pytest.raises(BusinessError):
        await service.record_action(
            "owner", source_id=source.id, target_id=target_id, kind=kind, action=action
        )


async def test_forget_tool_retains_controlled_scope_and_reports_possible_residuals(monkeypatch):
    from types import SimpleNamespace

    from cygnusx.application.services.agent_memory_tool_service import AgentMemoryToolService

    report = {
        "memory_id": "1",
        "forgotten": True,
        "scan_status": "complete",
        "residual_hints": [{"kind": "block", "id": 4, "excerpt": "possible"}],
    }
    forget = AsyncMock(return_value=report)
    monkeypatch.setattr(AgentMemoryToolService, "_assert_runtime", AsyncMock())
    monkeypatch.setattr(
        AgentMemoryToolService,
        "_service",
        staticmethod(lambda context: SimpleNamespace(forget_memory=forget)),
    )
    monkeypatch.setattr(AgentMemoryToolService, "_project_id", AsyncMock(return_value="p"))
    context = SimpleNamespace(agent_id="a")
    result = await AgentMemoryToolService().forget_memory(
        user_id="owner", memory_id="1", context=context
    )
    forget.assert_awaited_once_with(user_id="owner", memory_id="1", agent_id="a", project_id="p")
    assert result["residual_hints"] == report["residual_hints"]
    assert "可能" in result["summary"] and "确认" in result["summary"]


async def test_http_forget_returns_hints_and_denies_other_owner(fact_database, residual_settings):
    import asyncio

    import httpx
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    from cygnusx.api import deps
    from cygnusx.api.v1 import users
    from cygnusx.core.exceptions import CygnusXError

    session, db = fact_database
    source = await _fact(db, "GRCh38 source")
    target = await _fact(db, "GRCh38 related")
    foreign = await _fact(db, "GRCh38 private foreign", owner="foreign")
    session.commit()
    subject = "other"
    app = FastAPI()
    app.include_router(users.router, prefix="/users")

    async def identity():
        return subject

    async def database():
        return db

    async def errors(request, exc):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    app.dependency_overrides[deps.get_current_user_id] = identity
    app.dependency_overrides[deps.get_db] = database
    app.add_exception_handler(CygnusXError, errors)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://memory-test"
    ) as client:
        response = await asyncio.wait_for(client.post(f"/users/me/memories/{source.id}/forget"), 5)
        assert response.status_code == 404
        assert session.get(MemoryFactModel, source.id).status == "active"
        subject = "owner"
        response = await asyncio.wait_for(client.post(f"/users/me/memories/{source.id}/forget"), 5)
        assert response.status_code == 200
        result = response.json()
        assert result["forgotten"] and result["scan_status"] == "complete"
        assert [hint["id"] for hint in result["residual_hints"]] == [target.id]
        assert "content" not in result["residual_hints"][0]
        response = await asyncio.wait_for(
            client.post(
                "/users/me/memory-residual-actions",
                json={
                    "source_id": source.id,
                    "target_id": target.id,
                    "kind": "fact",
                    "action": "archive",
                },
            ),
            5,
        )
        assert response.status_code == 204
        rejected = await asyncio.wait_for(
            client.post(
                "/users/me/memory-residual-actions",
                json={
                    "source_id": source.id,
                    "target_id": foreign.id,
                    "kind": "fact",
                    "action": "archive",
                },
            ),
            5,
        )
        assert rejected.status_code == 404 and "private foreign" not in rejected.text
        assert (
            session.get(MemoryFactModel, target.id).status == "active"
        )  # Click report never deletes.
        response = await asyncio.wait_for(
            client.post(
                "/users/me/memory-residual-actions",
                json={
                    "source_id": source.id,
                    "target_id": target.id,
                    "kind": "fact",
                    "action": "delete-all",
                },
            ),
            5,
        )
        assert response.status_code == 422
