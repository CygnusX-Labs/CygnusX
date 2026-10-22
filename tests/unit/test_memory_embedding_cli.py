"""Embedding maintenance CLI has an explicit target and a read-only default."""

import json
from pathlib import Path
from runpy import run_path
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit
_SCRIPT = Path(__file__).resolve().parents[2] / "scripts/backfill_memory_embeddings.py"


def test_missing_explicit_dsn_never_uses_application_database(monkeypatch, capsys):
    script = run_path(str(_SCRIPT))
    run = AsyncMock()
    script["main"].__globals__["run"] = run
    monkeypatch.delenv("MEMORY_MAINTENANCE_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://private:password@production/platform")
    monkeypatch.setattr("sys.argv", [str(_SCRIPT)])
    assert script["main"]() == 2
    run.assert_not_awaited()
    output = capsys.readouterr().out
    assert json.loads(output)["status"] == "blocked"
    assert "password" not in output and "production" not in output


@pytest.mark.parametrize("apply", [False, True])
@pytest.mark.parametrize("statuses", [("active",), ("archived", "superseded")])
def test_explicit_database_and_apply_or_dry_run_are_passed_to_operator_service(
    monkeypatch, capsys, apply, statuses
):
    script = run_path(str(_SCRIPT))
    result = {"status": "completed" if apply else "dry_run", "updated": 0}
    run = AsyncMock(return_value=result)
    script["main"].__globals__["run"] = run
    monkeypatch.setenv("MEMORY_MAINTENANCE_DATABASE_URL", "postgresql://test/maintenance")
    monkeypatch.setattr(
        "sys.argv",
        [
            str(_SCRIPT),
            "--mode",
            "mismatch",
            *(["--statuses", *statuses] if statuses != ("active",) else []),
            *(["--apply", "--confirm-database", "maintenance"] if apply else []),
        ],
    )
    assert script["main"]() == 0
    run.assert_awaited_once_with(
        "postgresql://test/maintenance",
        storage="facts",
        mode="mismatch",
        limit=100,
        apply=apply,
        provider_id=None,
        confirm_database="maintenance" if apply else None,
        statuses=statuses,
    )
    assert json.loads(capsys.readouterr().out) == result


def test_errors_never_echo_dsn_or_source_text_and_failed_rows_are_nonzero(monkeypatch, capsys):
    script = run_path(str(_SCRIPT))
    monkeypatch.setenv(
        "MEMORY_MAINTENANCE_DATABASE_URL", "postgresql://private:password@test/maintenance"
    )
    monkeypatch.setattr("sys.argv", [str(_SCRIPT)])
    script["main"].__globals__["run"] = AsyncMock(
        side_effect=RuntimeError("private source and password")
    )
    assert script["main"]() == 2
    output = capsys.readouterr().out
    assert json.loads(output) == {"status": "error", "error_type": "RuntimeError"}
    assert "password" not in output and "private source" not in output
    script["main"].__globals__["run"] = AsyncMock(return_value={"status": "completed", "failed": 1})
    assert script["main"]() == 2


@pytest.mark.asyncio
async def test_non_postgres_is_rejected_before_opening_engine():
    script = run_path(str(_SCRIPT))
    with pytest.raises(ValueError, match="PostgreSQL required"):
        await script["run"]("sqlite://", storage="facts", mode="missing", limit=1, apply=False)


@pytest.mark.asyncio
async def test_apply_resolves_provider_in_explicit_db_and_publishes_only_after_commit(monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from uuid import uuid4

    from cygnusx.domain.ai_provider.entities import AIProviderConfig

    script = run_path(str(_SCRIPT))
    db = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
    engine = SimpleNamespace(dispose=AsyncMock())
    chosen = AIProviderConfig(id=uuid4(), name="maintenance-provider", model="synthetic-model")
    default = AsyncMock(return_value=chosen)
    monkeypatch.setattr(
        "cygnusx.infrastructure.database.repositories.ai_provider_repository.SqlAlchemyAIProviderConfigRepository",
        lambda session: SimpleNamespace(get_default=default),
    )

    @asynccontextmanager
    async def session_context(target_engine, **kwargs):
        assert target_engine is engine
        yield db

    class Maintenance:
        def __init__(self, session, *, storage, embedding_client):
            assert session is db and storage == "facts"
            assert embedding_client._config is chosen

        async def backfill(self, limit, *, mode, dry_run, statuses):
            assert mode == "mismatch" and not dry_run
            assert statuses == ("archived", "superseded")
            return {"status": "completed", "updated": 1}

        def publish_report(self, report):
            assert db.commit.await_count == 1

    script["run"].__globals__.update(
        {
            "create_async_engine": lambda url, **kwargs: engine,
            "AsyncSession": session_context,
            "MemoryEmbeddingService": Maintenance,
        }
    )
    result = await script["run"](
        "postgresql://test/maintenance",
        storage="facts",
        mode="mismatch",
        limit=1,
        apply=True,
        confirm_database="maintenance",
        statuses=("archived", "superseded"),
    )
    assert result["updated"] == 1
    default.assert_awaited_once()
    engine.dispose.assert_awaited_once()


@pytest.mark.parametrize("confirmation", [None, "another_database"])
@pytest.mark.asyncio
async def test_apply_rejects_unconfirmed_or_wrong_database_before_connecting(confirmation):
    script = run_path(str(_SCRIPT))
    engine = AsyncMock()
    script["run"].__globals__["create_async_engine"] = engine
    with pytest.raises(ValueError, match="confirm-database"):
        await script["run"](
            "postgresql://test/maintenance",
            storage="facts",
            mode="missing",
            limit=10,
            apply=True,
            confirm_database=confirmation,
        )
    engine.assert_not_called()


def test_cli_rejects_wrong_target_without_provider_or_dsn_disclosure(monkeypatch, capsys):
    script = run_path(str(_SCRIPT))
    run = AsyncMock()
    script["main"].__globals__["run"] = run
    monkeypatch.setenv(
        "MEMORY_MAINTENANCE_DATABASE_URL", "postgresql://private:secret@test/unexpected_target"
    )
    monkeypatch.setattr(
        "sys.argv", [str(_SCRIPT), "--apply", "--confirm-database", "authorized_target"]
    )
    assert script["main"]() == 2
    run.assert_not_awaited()
    output = capsys.readouterr().out
    assert json.loads(output) == {"status": "error", "error_type": "ValueError"}
    assert "secret" not in output and "private" not in output and "unexpected_target" not in output
