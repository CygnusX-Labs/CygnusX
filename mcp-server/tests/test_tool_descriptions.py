"""Regression tests for descriptions exposed by the external MCP server."""

import unittest
from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core.logger import logger
from fastmcp import Client, FastMCP
from tools import (
    _DescriptionAwareMCP,
    _load_tool_descriptions,
    _verify_tools_yaml_consistency,
    register_all_tools,
)
from tools.tasks import register as register_tasks


def input_schema(tool):
    """Support FastMCP 2.x and 3.x Tool field names in contract tests."""
    return getattr(tool, "input_schema", getattr(tool, "inputSchema", {}))


class ToolDescriptionTests(unittest.IsolatedAsyncioTestCase):
    async def test_registry_fallback_and_explicit_description(self):
        descriptions = {
            "fallback_tool": ("Registry description", "tests"),
            "blank_tool": ("Blank fallback", "tests"),
            "explicit_tool": ("Must not replace explicit", "tests"),
        }
        mcp = FastMCP("description-test")
        registered = _DescriptionAwareMCP(mcp, descriptions)

        @registered.tool()
        async def fallback_tool(value: str) -> dict:
            return {"value": value}

        @registered.tool(description="Explicit description")
        async def explicit_tool() -> str:
            return "ok"

        @registered.tool(description="   ")
        async def blank_tool() -> str:
            return "ok"

        async with Client(mcp) as client:
            tools = {tool.name: tool for tool in await client.list_tools()}
            self.assertEqual(tools["fallback_tool"].description, "Registry description")
            self.assertEqual(tools["explicit_tool"].description, "Explicit description")
            self.assertEqual(tools["blank_tool"].description, "Blank fallback")
            self.assertEqual(
                input_schema(tools["fallback_tool"])["properties"]["value"]["type"], "string"
            )
            result = await client.call_tool("fallback_tool", {"value": "read-only"})
            self.assertEqual(result.data, {"value": "read-only"})

    async def test_unknown_tool_name_does_not_receive_another_description(self):
        mcp = FastMCP("exact-name-test")
        registered = _DescriptionAwareMCP(
            mcp, {"different_tool": ("Unrelated description", "tests")}
        )

        @registered.tool()
        async def missing_description_tool() -> str:
            return "ok"

        async with Client(mcp) as client:
            tool = (await client.list_tools())[0]
            self.assertEqual(tool.name, "missing_description_tool")
            self.assertIsNone(tool.description)

    async def test_yaml_descriptions_and_read_only_task_call(self):
        descriptions = _load_tool_descriptions()
        self.assertTrue(descriptions["cygnusx_list_tasks"][0].strip())
        self.assertNotIn("not_a_registered_tool", descriptions)

        api = type("API", (), {})()
        api.list_tasks = AsyncMock(return_value=[{"id": "task-1", "status": "running"}])
        mcp = FastMCP("task-description-test")
        register_tasks(_DescriptionAwareMCP(mcp, descriptions), api)

        async with Client(mcp) as client:
            tools = {tool.name: tool for tool in await client.list_tools()}
            self.assertEqual(
                tools["cygnusx_list_tasks"].description,
                descriptions["cygnusx_list_tasks"][0],
            )
            result = await client.call_tool("cygnusx_list_tasks", {})
            self.assertTrue(result.data["success"])
            self.assertEqual(result.data["data"][0]["id"], "task-1")
        api.list_tasks.assert_awaited_once_with(status=None)

    async def test_disabled_group_registers_no_tools(self):
        api = type("API", (), {})()
        mcp = FastMCP("disabled-group-test")
        disabled_settings = SimpleNamespace(is_tool_group_enabled=lambda group: False)
        with patch("tools.settings", disabled_settings):
            register_all_tools(mcp, api)
        async with Client(mcp) as client:
            self.assertEqual(await client.list_tools(), [])

    async def test_enabled_registry_preserves_all_tool_schemas(self):
        api = type("API", (), {})()
        enabled_settings = SimpleNamespace(is_tool_group_enabled=lambda group: True)
        described_mcp = FastMCP("described-registry-test")
        baseline_mcp = FastMCP("baseline-registry-test")

        with patch("tools.settings", enabled_settings):
            register_all_tools(described_mcp, api)
            with patch("tools._DescriptionAwareMCP", side_effect=lambda server, _: server):
                register_all_tools(baseline_mcp, api)

        async with Client(described_mcp) as described_client:
            described = await described_client.list_tools()
        async with Client(baseline_mcp) as baseline_client:
            baseline = await baseline_client.list_tools()

        self.assertEqual(len(described), 111)
        self.assertEqual(
            {tool.name: input_schema(tool) for tool in described},
            {tool.name: input_schema(tool) for tool in baseline},
        )
        self.assertTrue(all(tool.description and tool.description.strip() for tool in described))

        descriptions = {tool.name: tool.description for tool in described}
        required_detail = {
            "cygnusx_list_runs": ("project_slug", "status"),
            "cygnusx_get_run_status": ("run_id", "task_id"),
            "cygnusx_get_run_logs": ("run_id", "limit", "500"),
            "cygnusx_verify_artifact": ("run_id", "checksum", "不自行重算"),
            "cygnusx_confirm_run_plan": ("confirmation_id", "人类批准", "user_confirmed"),
            "cygnusx_preview_analysis": ("flow_id", "sample_sheet", "不验证完整"),
            "atac_seq_status": ("task_id", "DEPRECATED", "cygnusx_get_task_progress"),
            "cygnusx_gene_search": ("query", "species", "候选"),
            "cygnusx_chem_search": ("query", "盐型", "结构相似"),
            "cygnusx_genome_sequence": ("stable ID", "3000", "截断"),
            "cygnusx_plant_get": ("Gramene v69", "taxon_id", "NCBI taxid"),
            "cygnusx_expression_studies": ("query", "single_cell", "表达定量值"),
        }
        for name, fragments in required_detail.items():
            with self.subTest(tool=name):
                self.assertTrue(all(fragment in descriptions[name] for fragment in fragments))


class RegistryWarningTests(unittest.TestCase):
    def test_missing_mapping_warning_names_tool_and_source(self):
        mcp = FastMCP("missing-description-test")
        registered = _DescriptionAwareMCP(mcp, {})

        @registered.tool()
        async def unmapped_description_probe() -> str:
            return "ok"

        output = StringIO()
        sink_id = logger.add(output, level="WARNING", format="{message}")
        try:
            _verify_tools_yaml_consistency(mcp, set())
        finally:
            logger.remove(sink_id)

        message = output.getvalue()
        self.assertIn("tool=unmapped_description_probe", message)
        self.assertIn("test_tool_descriptions.py:", message)
        self.assertIn("registry_source=tools.yaml entry missing", message)
        self.assertIn("registry_description=missing", message)


if __name__ == "__main__":
    unittest.main()
