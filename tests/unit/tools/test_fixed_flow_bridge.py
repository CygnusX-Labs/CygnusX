"""固定分析工具（prepare_fixed / submit_fixed 角色）的桥接分发测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.tool_invocation import ToolInvocationContext
from cygnusx.application.services.tool_bridge_service import ToolBridgeService
from cygnusx.tools.schema_loader import ToolSchema, ToolsSchemaLoader


class _FakeAsyncSession(AsyncSession):
    def __init__(self):
        pass


class _FakeLoader(ToolsSchemaLoader):
    """不读盘的伪造加载器。"""

    def __init__(self, tools: list[ToolSchema]) -> None:
        self._tools = tools
        self._config = None
        self._mtime = 0.0
        self._tools_by_name = {t.name: t for t in tools}

    def get_config(self):
        from cygnusx.tools.schema_loader import ToolsSchemaRegistry

        return ToolsSchemaRegistry(tools=self._tools)

    def list_tools(self):
        return list(self._tools)

    def get_tool(self, name: str):
        return self._tools_by_name.get(name)


def _fixed_schema(name: str, role: str, properties: dict, required: list[str]) -> ToolSchema:
    return ToolSchema(
        key=name,
        name=name,
        description=f"fixed tool {name}",
        category="workflow",
        invocation_mode="analysis_flow",
        extra={"tool_role": role},
        input_schema={"type": "object", "properties": properties, "required": required},
    )


PREPARE_SCHEMA = _fixed_schema(
    "cygnusx_prepare",
    "prepare_fixed",
    {
        "flow_id": {"type": "string"},
        "arguments": {"type": "object"},
    },
    ["flow_id", "arguments"],
)
SUBMIT_SCHEMA = _fixed_schema(
    "cygnusx_submit",
    "submit_fixed",
    {"confirmation_id": {"type": "string"}},
    ["confirmation_id"],
)


def _context() -> ToolInvocationContext:
    return ToolInvocationContext(
        user_id="u1", session_id="s-test", db=_FakeAsyncSession()
    )


@pytest.mark.asyncio
async def test_prepare_fixed_dispatches_to_service_prepare() -> None:
    bridge = ToolBridgeService(_FakeLoader([PREPARE_SCHEMA]))
    with patch(
        "cygnusx.application.services.analysis_flow_tool_service.AnalysisFlowToolService"
    ) as service_type:
        instance = service_type.return_value
        instance.prepare = AsyncMock(
            return_value={"valid": True, "flow_id": "rna_seq", "confirmation_id": "c-1"}
        )
        result = await bridge.execute(
            "u1",
            "cygnusx_prepare",
            {"flow_id": "rna_seq", "arguments": {"task_name": "demo"}},
            context=_context(),
        )
    instance.prepare.assert_awaited_once_with("rna_seq", {"task_name": "demo"})
    assert result["llm_payload"]["confirmation_id"] == "c-1"


@pytest.mark.asyncio
async def test_prepare_fixed_without_flow_id_calls_prepare_with_empty_id() -> None:
    """flow_id 缺失也要落到服务端校验，由服务层给出明确错误，不静默放行。"""
    bridge = ToolBridgeService(_FakeLoader([PREPARE_SCHEMA]))
    with patch(
        "cygnusx.application.services.analysis_flow_tool_service.AnalysisFlowToolService"
    ) as service_type:
        instance = service_type.return_value
        instance.prepare = AsyncMock(
            side_effect=Exception("流程 '' 不存在"),
        )
        result = await bridge.execute(
            "u1",
            "cygnusx_prepare",
            {"arguments": {}},
            context=_context(),
        )
    instance.prepare.assert_awaited_once_with("", {})
    assert result["success"] is False


@pytest.mark.asyncio
async def test_submit_fixed_dispatches_to_confirm_and_submit() -> None:
    bridge = ToolBridgeService(_FakeLoader([SUBMIT_SCHEMA]))
    with patch(
        "cygnusx.application.services.analysis_flow_tool_service.AnalysisFlowToolService"
    ) as service_type:
        instance = service_type.return_value
        instance.confirm_and_submit = AsyncMock(
            return_value={"task_id": "t-1", "status": "QUEUED", "task_url": "/tasks/t-1"}
        )
        result = await bridge.execute(
            "u1",
            "cygnusx_submit",
            {"confirmation_id": "c-1"},
            context=_context(),
        )
    instance.confirm_and_submit.assert_awaited_once_with("c-1")
    assert result["llm_payload"]["task_id"] == "t-1"


@pytest.mark.asyncio
async def test_per_flow_prepare_role_still_requires_schema_flow_id() -> None:
    """存量 per-flow 角色行为不变：schema.extra 无 flow_id 仍报错。"""
    schema = _fixed_schema("cygnusx_prepare_legacy", "prepare", {}, [])
    bridge = ToolBridgeService(_FakeLoader([schema]))
    result = await bridge.execute("u1", "cygnusx_prepare_legacy", {}, context=_context())
    assert result["success"] is False
    assert "flow_id" in result["error"]
