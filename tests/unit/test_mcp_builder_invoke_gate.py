"""实验 MCP 调用门禁（P0 执行权限闭环）测试。

架构审查 §6.2 缺口：invoke 须拒绝未审核 / 已驳回 / 已下线的实验 MCP，
且输出须限额。与 Agent 装配口径（experimental 池须 review_status=APPROVED）一致。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from cygnusx.application.services.mcp_builder_service import (
    MCPBuilderService,
    _clamp_experimental_result,
)
from cygnusx.core.exceptions import ValidationError
from cygnusx.domain.mcp.entities import MCPServer, MCPToolRegistry
from cygnusx.domain.mcp.value_objects import (
    ReviewStatus,
    ServerPool,
    ServerStatus,
    Transport,
)


def _server(**overrides) -> MCPServer:
    server_id = uuid4()
    server = MCPServer(
        id=server_id,
        name="exp-demo",
        description="desc",
        transport=Transport.STDIO,
        command="python",
        args=["/workspace/mcp-builds/demo/server.py"],
        status=ServerStatus.ONLINE,
        pool=ServerPool.EXPERIMENTAL,
        created_by=uuid4(),
        current_version="1.0.0",
        version="1.0.0",
        generation_meta={"build_id": str(uuid4()), "code_path": "mcp-builds/demo/server.py"},
        tools=[
            MCPToolRegistry(tool_name="tool_a", description="a", input_schema={}, server_id=server_id),
        ],
    )
    for key, value in overrides.items():
        setattr(server, key, value)
    return server


def _service(server: MCPServer) -> MCPBuilderService:
    service = MCPBuilderService(MagicMock())
    service._repo = AsyncMock()
    service._repo.get_by_id.return_value = server
    return service


def _fake_sandbox(monkeypatch: pytest.MonkeyPatch, result: dict) -> SimpleNamespace:
    fake = SimpleNamespace(
        write_file=AsyncMock(),
        start_mcp_server=AsyncMock(return_value={"server_id": "s1", "tools": []}),
        mcp_call_tool=AsyncMock(return_value=result),
        stop_mcp_server=AsyncMock(),
    )
    monkeypatch.setattr(
        "cygnusx.infrastructure.studio.manager.studio_sandbox_manager", fake
    )
    return fake


@pytest.mark.unit
async def test_invoke_rejects_pending_review(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = uuid4()
    server = _server(created_by=owner, review_status=ReviewStatus.PENDING)
    service = _service(server)
    fake = _fake_sandbox(monkeypatch, {"content": [], "is_error": False})

    with pytest.raises(ValidationError, match="尚未通过审核"):
        await service.call_experimental_tool(str(server.id), "tool_a", {}, "sess", str(owner))
    fake.start_mcp_server.assert_not_awaited()


@pytest.mark.unit
async def test_invoke_rejects_rejected_review(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = uuid4()
    server = _server(created_by=owner, review_status=ReviewStatus.REJECTED)
    service = _service(server)
    fake = _fake_sandbox(monkeypatch, {"content": [], "is_error": False})

    with pytest.raises(ValidationError, match="尚未通过审核"):
        await service.call_experimental_tool(str(server.id), "tool_a", {}, "sess", str(owner))
    fake.start_mcp_server.assert_not_awaited()


@pytest.mark.unit
async def test_invoke_rejects_rejected_even_if_still_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """审核驳回即拒绝，与 is_enabled 状态解耦（双保险，不依赖驳回时是否同步禁用）。"""
    owner = uuid4()
    server = _server(created_by=owner, review_status=ReviewStatus.REJECTED, is_enabled=True)
    service = _service(server)
    fake = _fake_sandbox(monkeypatch, {"content": [], "is_error": False})

    with pytest.raises(ValidationError, match="尚未通过审核"):
        await service.call_experimental_tool(str(server.id), "tool_a", {}, "sess", str(owner))
    fake.start_mcp_server.assert_not_awaited()


@pytest.mark.unit
async def test_invoke_rejects_disabled_server(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = uuid4()
    server = _server(created_by=owner, is_enabled=False)
    service = _service(server)
    fake = _fake_sandbox(monkeypatch, {"content": [], "is_error": False})

    with pytest.raises(ValidationError, match="下线"):
        await service.call_experimental_tool(str(server.id), "tool_a", {}, "sess", str(owner))
    fake.start_mcp_server.assert_not_awaited()


@pytest.mark.unit
async def test_invoke_approved_server_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = uuid4()
    server = _server(created_by=owner, review_status=ReviewStatus.APPROVED)
    service = _service(server)
    service._version_code = AsyncMock(return_value="")  # 绕过 DB 取代码快照
    service._log = AsyncMock()  # 绕过审计落库
    result_payload = {"content": [{"text": "ok"}], "is_error": False}
    _fake_sandbox(monkeypatch, result_payload)

    result = await service.call_experimental_tool(
        str(server.id), "tool_a", {}, "sess", str(owner)
    )
    assert result == result_payload


@pytest.mark.unit
async def test_oversized_result_is_truncated() -> None:
    big = {"content": [{"text": "x" * 100_000}], "is_error": False, "success": True}
    clamped = _clamp_experimental_result(big)
    assert clamped["truncated"] is True
    assert clamped["success"] is True
    assert "超出实验工具单次调用" in clamped["summary"]


@pytest.mark.unit
async def test_small_result_passes_through() -> None:
    small = {"content": [{"text": "ok"}], "is_error": False}
    assert _clamp_experimental_result(small) == small
