from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from omichub.api.v1.agentteams import require_integration_token
from omichub.application.services.agent_consultation_service import (
    AgentConsultationService,
    ConsultationEnvelope,
)
from omichub.application.services.parallel_subagent_service import ParallelSubAgentService
from omichub.core.exceptions import NotFoundError
from omichub.middleware.auth import SELF_AUTHENTICATED_PREFIXES


def test_run_consultation_uses_safe_single_task_and_parses_envelope() -> None:
    asyncio.run(_test_run_consultation_uses_safe_single_task_and_parses_envelope())


async def _test_run_consultation_uses_safe_single_task_and_parses_envelope() -> None:
    agent_service = SimpleNamespace(
        assemble_context=AsyncMock(return_value=SimpleNamespace(model_config=object()))
    )
    parallel_service = SimpleNamespace(
        run=AsyncMock(
            return_value={
                "llm_payload": {
                    "results": [
                        {
                            "answer": """```json
{"conclusion":"可信","recommendations":["复核样本"],"evidence_refs":["report://qc"],"risks":[],"token_usage":42}
```"""
                        }
                    ]
                }
            }
        )
    )
    service = AgentConsultationService(
        SimpleNamespace(), agent_service=agent_service, parallel_service=parallel_service
    )

    result = await service.run_consultation(
        case_id="case-1",
        agent_id="agent-rnaseq",
        question="解释结果",
        capability="result_interpretation",
        evidence_refs=["report://qc"],
        requested_tools=["knowledge_search"],
        requester_ref="user-1",
    )

    assert result == ConsultationEnvelope(
        conclusion="可信",
        recommendations=["复核样本"],
        evidence_refs=["report://qc"],
        risks=[],
        token_usage=42,
    )
    agent_service.assemble_context.assert_awaited_once_with("agent-rnaseq", user_id="user-1")
    call = parallel_service.run.await_args.kwargs
    assert call["safe_only"] is True
    assert call["runtime_authorized"] is True
    assert len(call["tasks"]) == 1
    assert call["tasks"][0]["workspace_access"] is False


def test_parse_envelope_falls_back_to_raw_answer() -> None:
    result = AgentConsultationService.parse_envelope("普通文本结论")
    assert result.conclusion == "普通文本结论"
    assert result.token_usage == 0
    assert result.risks == ["信封解析降级：专家答复未满足结构化 JSON 契约。"]


def test_workspace_consultation_uses_scoped_workdir() -> None:
    asyncio.run(_test_workspace_consultation_uses_scoped_workdir())


async def _test_workspace_consultation_uses_scoped_workdir() -> None:
    agent_service = SimpleNamespace(
        assemble_context=AsyncMock(return_value=SimpleNamespace(model_config=object()))
    )
    parallel_service = SimpleNamespace(
        run=AsyncMock(return_value={"llm_payload": {"results": [{"answer": "workspace complete"}]}})
    )
    service = AgentConsultationService(
        SimpleNamespace(), agent_service=agent_service, parallel_service=parallel_service
    )

    result = await service.run_consultation(
        case_id="case-1",
        work_item_id="code-write-01",
        agent_id="agent-code",
        question="生成报告",
        capability="result_interpretation",
        evidence_refs=[],
        requested_tools=[],
        requester_ref="user-1",
        execution_mode="workspace_execution",
    )

    call = parallel_service.run.await_args.kwargs
    assert call["safe_only"] is False
    assert call["tasks"][0]["workspace_access"] is True
    assert str(call["workdir_root"]) == "/data/omichub/output/agentteams/case-1/code-write-01"
    assert "信封解析降级" in result.risks[0]


def test_workspace_artifacts_are_copied_and_registered(tmp_path, monkeypatch) -> None:
    asyncio.run(_test_workspace_artifacts_are_copied_and_registered(tmp_path, monkeypatch))


async def _test_workspace_artifacts_are_copied_and_registered(tmp_path, monkeypatch) -> None:
    source_root = tmp_path / "output" / "agentteams" / "case-1" / "exec-01"
    source_root.mkdir(parents=True)
    source = source_root / "treeplot.svg"
    source.write_text("<svg/>", encoding="utf-8")
    storage_root = tmp_path / "storage"

    class Factory:
        def user_root(self, user_id: str):
            return storage_root / "users" / user_id

        def relative_to_root(self, path):
            return path.relative_to(storage_root).as_posix()

    saved = []

    class Repository:
        def __init__(self, _db) -> None:
            pass

        async def save(self, file):
            saved.append(file)
            return file

    monkeypatch.setattr(
        "omichub.application.services.agent_consultation_service.get_path_factory", lambda: Factory()
    )
    monkeypatch.setattr(
        "omichub.application.services.agent_consultation_service.FileRepositoryImpl", Repository
    )
    service = AgentConsultationService(SimpleNamespace())

    artifacts, errors = await service._register_workspace_artifacts(
        str(uuid4()), "case-1", "exec-01", source_root
    )

    assert errors == []
    assert len(artifacts) == len(saved) == 1
    assert artifacts[0]["path"].endswith("workspace/agentteams/case-1/exec-01/treeplot.svg")
    assert (storage_root / artifacts[0]["path"]).read_text(encoding="utf-8") == "<svg/>"


def test_run_consultation_rejects_missing_agent() -> None:
    asyncio.run(_test_run_consultation_rejects_missing_agent())


async def _test_run_consultation_rejects_missing_agent() -> None:
    agent_service = SimpleNamespace(assemble_context=AsyncMock(return_value=None))
    service = AgentConsultationService(
        SimpleNamespace(),
        agent_service=agent_service,
        parallel_service=SimpleNamespace(run=AsyncMock()),
    )
    with pytest.raises(NotFoundError):
        await service.run_consultation(
            case_id="case-1",
            agent_id="agent-rnaseq",
            question="解释结果",
            capability="result_interpretation",
            evidence_refs=[],
            requested_tools=[],
            requester_ref="user-1",
        )


def test_integration_token_missing_or_wrong_is_unauthorized(monkeypatch) -> None:
    monkeypatch.setattr(
        "omichub.api.v1.agentteams.get_settings",
        lambda: SimpleNamespace(agentteams_integration_token="expected-token"),
    )
    with pytest.raises(HTTPException) as missing:
        require_integration_token(None)
    with pytest.raises(HTTPException) as wrong:
        require_integration_token("wrong-token")
    assert missing.value.status_code == 401
    assert wrong.value.status_code == 401
    assert require_integration_token("expected-token") is None


def test_consultation_prefix_uses_its_integration_token_guard() -> None:
    assert "/api/v1/agent-teams/consultations/" in SELF_AUTHENTICATED_PREFIXES


def test_safe_only_filters_writable_and_confirmation_tools(monkeypatch) -> None:
    schemas = {
        "safe_lookup": SimpleNamespace(
            invocation_mode="backend_sync",
            annotations=SimpleNamespace(read_only_hint=True),
            requires_confirm=False,
        ),
        "write_file": SimpleNamespace(
            invocation_mode="backend_sync",
            annotations=SimpleNamespace(read_only_hint=False),
            requires_confirm=False,
        ),
        "dangerous_read": SimpleNamespace(
            invocation_mode="backend_sync",
            annotations=SimpleNamespace(read_only_hint=True),
            requires_confirm=True,
        ),
    }
    monkeypatch.setattr(
        "omichub.application.services.parallel_subagent_service.schema_loader.get_tool",
        schemas.get,
    )
    context = SimpleNamespace(
        tools=[
            {"type": "function", "function": {"name": name}}
            for name in ("safe_lookup", "write_file", "dangerous_read")
        ],
        features={"web_search": False},
        mcp_servers=[],
    )

    filtered = ParallelSubAgentService._prepare_child_tools(context, safe_only=True)
    names = {tool["function"]["name"] for tool in filtered}

    assert "safe_lookup" in names
    assert "write_file" not in names
    assert "dangerous_read" not in names
