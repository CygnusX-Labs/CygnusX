"""Acceptance baseline tool never silently falls back to a production DSN."""

import json
from pathlib import Path
from runpy import run_path

import pytest

pytestmark = pytest.mark.unit
_SCRIPT = Path(__file__).resolve().parents[2] / "scripts/inspect_memory_baseline.py"


def test_missing_acceptance_dsn_reports_blocked_without_using_database_url(monkeypatch, capsys):
    monkeypatch.delenv("MEMORY_ACCEPTANCE_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://private:password@production/app")
    monkeypatch.setattr("sys.argv", [str(_SCRIPT)])
    script = run_path(str(_SCRIPT))
    assert script["main"]() == 2
    output = capsys.readouterr().out
    assert json.loads(output)["status"] == "blocked"
    assert "production" not in output and "password" not in output


def test_connection_errors_do_not_echo_dsn_or_driver_message(monkeypatch, capsys):
    script = run_path(str(_SCRIPT))

    async def fail(_dsn):
        raise RuntimeError("password=private; content=personal")

    script["main"].__globals__["collect"] = fail
    monkeypatch.setenv("MEMORY_ACCEPTANCE_DATABASE_URL", "postgresql://private")
    monkeypatch.setattr("sys.argv", [str(_SCRIPT)])
    assert script["main"]() == 2
    output = capsys.readouterr().out
    assert json.loads(output) == {"status": "blocked", "error_type": "RuntimeError"}
    assert "private" not in output and "personal" not in output


@pytest.mark.asyncio
async def test_non_postgres_dsn_rejected_before_connecting():
    script = run_path(str(_SCRIPT))
    with pytest.raises(ValueError, match="PostgreSQL required"):
        await script["collect"]("sqlite://")
