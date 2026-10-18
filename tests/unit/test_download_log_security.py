"""Synthetic secret canaries through real execution/log boundaries; no subprocess/network."""

from __future__ import annotations

import pytest

from cygnusx.infrastructure.execution.base import ExecutionContext
from cygnusx.infrastructure.execution.binary import BinaryExecutor

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_binary_log_filter_runs_before_callback():
    messages = []

    async def capture(level, message, source=""):
        messages.append(message)

    context = ExecutionContext(engine="binary", on_log=capture)
    context.log_filter = lambda text: "[redacted]"
    await BinaryExecutor()._emit(context, "https://example.org/a?token=S3_CANARY", is_stderr=True)
    assert messages == ["[redacted]"]


@pytest.mark.parametrize(
    "message",
    [
        "https://example.org/private/S3_CANARY?token=S3_CANARY",
        "https:\\/\\/example.org/S3_CANARY",
        "Authorization: Bearer S3_CANARY",
        "Cookie: session=S3_CANARY; other=value",
        '"password":"S3_CANARY"',
        "access_key_secret=S3_CANARY",
    ],
)
def test_log_redaction_removes_secret_canaries(message: str) -> None:
    from cygnusx.domain.download_security import redact_download_text

    assert "S3_CANARY" not in redact_download_text(message)


@pytest.mark.parametrize("query", ["token=S3_CANARY", "X-Amz-Signature=S3_CANARY", "sig=S3_CANARY"])
def test_signed_urls_rejected_before_storage(query: str) -> None:
    from cygnusx.domain.download_security import validate_download_url

    with pytest.raises(ValueError, match="安全凭据通道"):
        validate_download_url(f"https://example.org/file?{query}")


def test_response_copy_preserves_original_parameters() -> None:
    from cygnusx.domain.download_security import redact_download_parameters

    original = {"links": ["https://example.org/file?token=S3_CANARY"], "token": "S3_CANARY"}
    safe = redact_download_parameters(original)
    assert "S3_CANARY" not in str(safe)
    assert original["token"] == "S3_CANARY"
    assert "S3_CANARY" in original["links"][0]


def test_validation_errors_drop_untrusted_values() -> None:
    from cygnusx.domain.download_security import download_validation_errors

    errors = [
        {
            "type": "value_error",
            "loc": ("body", "links", "S3_CANARY"),
            "msg": "S3_CANARY",
            "input": "S3_CANARY",
            "ctx": {"error": "S3_CANARY"},
        }
    ]
    safe = download_validation_errors(errors, {"links"})
    assert "S3_CANARY" not in str(safe)
    assert safe[0]["loc"] == ["body", "links", "[field]"]


def test_public_query_and_default_execution_are_unchanged() -> None:
    from cygnusx.domain.download_security import validate_download_url

    url = "https://example.org/file?download=1"
    assert validate_download_url(url) == url
    assert ExecutionContext(engine="binary").log_filter is None


@pytest.mark.asyncio
async def test_executor_filters_result_and_preserves_progress(monkeypatch) -> None:
    import asyncio
    from types import SimpleNamespace

    from cygnusx.domain.download_security import redact_download_text

    stdout, stderr = asyncio.StreamReader(), asyncio.StreamReader()
    stdout.feed_data(b'{"message":"https://example.org/S3_CANARY","progress":0.5}\n')
    stdout.feed_eof()
    stderr.feed_data(b"password=S3_CANARY\n")
    stderr.feed_eof()

    async def wait():
        return 1

    async def spawn(*args, **kwargs):
        return SimpleNamespace(stdout=stdout, stderr=stderr, wait=wait)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    messages, progress = [], []

    async def log(level, message, source):
        messages.append(message)

    async def update(value):
        progress.append(value)

    result = await BinaryExecutor().execute(
        ExecutionContext(
            engine="binary",
            binary="fixture-only",
            on_log=log,
            on_progress=update,
            log_filter=redact_download_text,
        )
    )
    assert result.status == "failed"
    assert "S3_CANARY" not in str((result, messages))
    assert progress == [0.5]


@pytest.mark.asyncio
async def test_confirmation_rejects_signed_url_before_save() -> None:
    from unittest.mock import AsyncMock

    from cygnusx.application.services.tool_confirmation_service import (
        ConfirmationError,
        ToolConfirmationService,
        _MemoryStore,
    )

    store = _MemoryStore()
    store.save = AsyncMock()
    service = ToolConfirmationService(store)
    with pytest.raises(ConfirmationError, match="安全或协议"):
        await service.create_for_tool(
            "user",
            "cygnusx_submit_download",
            {
                "source": "http",
                "links": ["https://example.org/f?token=S3_CANARY"],
            },
        )
    store.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_download_validation_handler_hides_input_from_response_and_log(monkeypatch) -> None:
    import json
    from unittest.mock import Mock

    from fastapi.exceptions import RequestValidationError
    from starlette.requests import Request

    from cygnusx import main

    warning = Mock()
    monkeypatch.setattr(main.logger, "warning", warning)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/downloads",
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("test", 80),
        }
    )
    error = RequestValidationError(
        [
            {
                "type": "value_error",
                "loc": ("body", "links", 0),
                "input": "https://example.org/f?token=S3_CANARY",
                "msg": "S3_CANARY",
                "ctx": {"error": ValueError("S3_CANARY")},
            }
        ]
    )
    handler = main.app.exception_handlers[RequestValidationError]
    response = await handler(request, error)
    assert response.status_code == 422
    assert "S3_CANARY" not in response.body.decode()
    assert "S3_CANARY" not in str(warning.call_args)
    assert json.loads(response.body)["errors"][0]["loc"] == ["body", "links", 0]


def test_real_task_response_redacts_download_without_mutating_execution() -> None:
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from uuid import uuid4

    from cygnusx.application.schemas.task import task_to_response

    now = datetime.now(UTC)
    parameters = {"links": ["https://example.org/f?token=S3_CANARY"]}
    task = SimpleNamespace(
        id=uuid4(),
        flow_id="ebi_download",
        user_id=uuid4(),
        name="download https://example.org/S3_CANARY",
        status="failed",
        execution_mode="local",
        parameters=parameters,
        work_dir="/fixture",
        result_path="",
        error_message="password=S3_CANARY",
        progress=0.0,
        logs=[
            SimpleNamespace(
                timestamp=now,
                level="error",
                source="binary",
                message="Authorization: Bearer S3_CANARY",
            )
        ],
        created_at=now,
        started_at=None,
        finished_at=None,
    )
    result = task_to_response(task)
    assert "S3_CANARY" not in result.model_dump_json()
    assert task.parameters is parameters
    assert "S3_CANARY" in str(task.parameters)
    assert "S3_CANARY" in task.logs[0].message
    task.flow_id = "other_flow"
    assert task_to_response(task).parameters == parameters


def test_ftp_expansion_obeys_request_link_limit(monkeypatch) -> None:
    from cygnusx.core.exceptions import ValidationError
    from cygnusx.infrastructure.celery_app.tasks import download as worker
    from cygnusx.infrastructure.download import policy

    config = worker.get_download_config().model_copy(deep=True)
    config.validation.max_links_per_task = 1
    config.validation.max_ftp_files = 100
    monkeypatch.setattr(worker, "get_download_config", lambda: config)
    monkeypatch.setattr(policy, "require_download_runtime", lambda source: None)

    class FakeFTP:
        def __init__(self, *args, **kwargs):
            pass

        def login(self):
            pass

        def cwd(self, path):
            if path != "/":
                raise OSError("fixture file")

        def pwd(self):
            return "/"

        def nlst(self):
            return ["first", "second"]

        def quit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(worker, "FTP", FakeFTP)
    with pytest.raises(ValidationError, match="数量超限"):
        worker._expand_ftp_directories(["ftp://example.org/"], True)


@pytest.mark.asyncio
async def test_builtin_download_error_does_not_echo_rejected_credentials(monkeypatch) -> None:
    from cygnusx.application.services import agent_tool_gateway
    from cygnusx.infrastructure.mcp.presets import _platform_submit_download

    # Exercise the latent validation branch without changing either production source gate.
    monkeypatch.setattr(agent_tool_gateway, "require_agent_write_gate", lambda operation: None)
    result = await _platform_submit_download(
        {
            "source": "direct_link",
            "links": ["https://example.org/f?token=S3_CANARY"],
        },
        user_id="fixture-user",
    )
    assert "S3_CANARY" not in str(result)
    assert result["code"] == "DOWNLOAD_ARGUMENTS_INVALID"
