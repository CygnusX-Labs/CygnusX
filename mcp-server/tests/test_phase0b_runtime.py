"""Isolated real MCP clients. Never connect to a configured platform or Redis."""

import asyncio
import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
from fastmcp import Client, FastMCP
from fastmcp.client.transports import StdioTransport
from fastmcp.exceptions import ToolError
from pydantic import SecretStr

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "isolated-phase0b-incoming-token-123456789"


def input_schema(tool):
    """Support FastMCP 2.x and 3.x Tool field names in protocol tests."""
    return getattr(tool, "input_schema", getattr(tool, "inputSchema", {}))


def isolated_env():
    return {
        **os.environ,
        "CYGNUSX_BASE_URL": "http://127.0.0.1:1",
        "CYGNUSX_API_KEY": "isolated-not-a-production-key",
        "CYGNUSX_HOST": "127.0.0.1",
        "CYGNUSX_HTTP_TOKEN": TOKEN,
        "CYGNUSX_REQUEST_TIMEOUT": "1",
    }


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    def require_unrestricted_io(self):
        try:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
        except PermissionError:
            self.skipTest(
                "BLOCKED: restricted I/O sandbox; real STDIO initialization also timed out"
            )

    async def test_stdio_main_schema_and_boolean_rejection(self):
        self.require_unrestricted_io()
        with tempfile.TemporaryFile(mode="w+") as log:
            transport = StdioTransport(
                sys.executable, ["main.py"], env=isolated_env(), cwd=str(ROOT), log_file=log
            )
            async with Client(transport, timeout=10) as client:
                tools = await client.list_tools()
                self.assertEqual(len(tools), 111)
                tool = next(t for t in tools if t.name == "cygnusx_submit_analysis")
                self.assertIn("confirmation_id", input_schema(tool)["properties"])
                result = await client.call_tool(
                    tool.name, {"flow_id": "rna_seq", "user_confirmed": True}
                )
                self.assertFalse(result.data["success"])
                self.assertIn("user_confirmed", result.data["summary"])
                with self.assertRaises(ToolError):
                    await client.call_tool(tool.name, {})
                result = await client.call_tool(
                    "cygnusx_get_task_progress", {"task_id": "isolated"}
                )
                self.assertFalse(result.data["success"])

    async def test_stdio_pipeline_entry(self):
        self.require_unrestricted_io()
        with tempfile.TemporaryFile(mode="w+") as log:
            transport = StdioTransport(
                sys.executable,
                ["pipelines_main.py"],
                env=isolated_env(),
                cwd=str(ROOT),
                log_file=log,
            )
            async with Client(transport, timeout=10) as client:
                tools = await client.list_tools()
                self.assertGreater(len(tools), 0)
                self.assertTrue(all(input_schema(t)["type"] == "object" for t in tools))

    async def check_http(self, transport, path):
        try:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
        except PermissionError as error:
            self.skipTest(f"BLOCKED: loopback binding forbidden: {error}")
        with tempfile.TemporaryFile(mode="w+") as log:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "main.py",
                "--transport",
                transport,
                "--port",
                str(port),
                cwd=ROOT,
                env=isolated_env(),
                stdout=log,
                stderr=log,
            )
            try:
                url = f"http://127.0.0.1:{port}{path}"
                async with httpx.AsyncClient(trust_env=False, timeout=1) as http:
                    request = http.get if transport == "sse" else http.post
                    request_kwargs = {} if transport == "sse" else {"json": {}}
                    for _ in range(100):
                        if process.returncode is not None:
                            log.seek(0)
                            self.fail(log.read())
                        try:
                            denied = await request(url, **request_kwargs)
                            break
                        except httpx.ConnectError:
                            await asyncio.sleep(0.1)
                    else:
                        self.fail("MCP startup timed out")
                    self.assertEqual(denied.status_code, 401)
                    forged = await request(
                        url,
                        **request_kwargs,
                        headers={"Authorization": "Bearer forged", "X-User-Id": "owner"},
                    )
                    self.assertEqual(forged.status_code, 401)
                async with Client(url, auth=TOKEN, timeout=10) as client:
                    self.assertEqual(len(await client.list_tools()), 111)
                    result = await client.call_tool(
                        "cygnusx_submit_analysis", {"flow_id": "rna_seq", "user_confirmed": True}
                    )
                    self.assertFalse(result.data["success"])
            finally:
                if process.returncode is None:
                    process.terminate()
                await asyncio.wait_for(process.wait(), 10)

    async def test_loopback_http(self):
        await self.check_http("streamable-http", "/mcp")

    async def test_loopback_sse(self):
        await self.check_http("sse", "/sse")


class InProcessTests(unittest.IsolatedAsyncioTestCase):
    async def test_download_confirmation_uses_platform_normalized_links(self):
        from tools.downloads import register

        api = type("API", (), {})()
        api.create_tool_confirmation = AsyncMock(return_value={"confirmation_id": "cid-1"})
        api.submit_download = AsyncMock(return_value={"id": "task-1", "status": "queued"})
        mcp = FastMCP("isolated-downloads")
        register(mcp, api)

        links = ["  https://example.org/a.fastq  ", "", "https://example.org/b.fastq"]
        async with Client(mcp, timeout=5) as client:
            first = await client.call_tool(
                "cygnusx_submit_download",
                {"source": "direct_link", "links": links},
            )
            self.assertTrue(first.data["needs_confirmation"])
            confirmation_args = api.create_tool_confirmation.await_args.args[1]
            self.assertEqual(
                confirmation_args["links"],
                ["https://example.org/a.fastq", "https://example.org/b.fastq"],
            )

            await client.call_tool(
                "cygnusx_submit_download",
                {"source": "direct_link", "links": links, "confirmation_id": "cid-1"},
            )

        submitted = api.submit_download.await_args.args[0]
        self.assertEqual(submitted["links"], confirmation_args["links"])
        self.assertEqual(submitted["confirmation_id"], "cid-1")

    async def test_cloud_confirmation_uses_platform_normalized_object_uri(self):
        from tools.downloads import register

        api = type("API", (), {})()
        api.create_tool_confirmation = AsyncMock(return_value={"confirmation_id": "cid-2"})
        api.submit_download = AsyncMock(return_value={"id": "task-2", "status": "queued"})
        mcp = FastMCP("isolated-cloud-downloads")
        register(mcp, api)

        async with Client(mcp, timeout=5) as client:
            await client.call_tool(
                "cygnusx_submit_download",
                {
                    "source": "cloud_storage",
                    "cloud_provider": "aliyun",
                    "object_uri": "  oss://bucket/path  ",
                },
            )
            confirmation_args = api.create_tool_confirmation.await_args.args[1]
            self.assertEqual(confirmation_args["object_uri"], "oss://bucket/path")
            await client.call_tool(
                "cygnusx_submit_download",
                {
                    "source": "cloud_storage",
                    "cloud_provider": "aliyun",
                    "object_uri": "  oss://bucket/path  ",
                    "confirmation_id": "cid-2",
                },
            )

        submitted = api.submit_download.await_args.args[0]
        self.assertEqual(submitted["object_uri"], confirmation_args["object_uri"])

    async def test_incoming_token_and_transport_boundary(self):
        from core.config import settings, validate_transport_security
        from core.runtime import LocalTokenVerifier

        previous_token = settings.http_token
        previous_allow = settings.allow_non_loopback_http
        settings.http_token = SecretStr(TOKEN)
        try:
            verifier = LocalTokenVerifier()
            self.assertIsNone(await verifier.verify_token("forged"))
            accepted = await verifier.verify_token(TOKEN)
            self.assertEqual(accepted.client_id, "local-mcp-client")
            validate_transport_security("streamable-http", "127.0.0.1")
            settings.allow_non_loopback_http = True
            with self.assertRaises(RuntimeError):
                validate_transport_security("http", "0.0.0.0")
        finally:
            settings.http_token = previous_token
            settings.allow_non_loopback_http = previous_allow

    async def test_real_client_schema_call_errors_and_cleanup(self):
        import main
        from client.api_client import CygnusXAPIError

        main.api.get_task = AsyncMock(side_effect=CygnusXAPIError(503, "isolated failure"))
        async with Client(main.mcp, timeout=5) as client:
            tools = await client.list_tools()
            self.assertEqual(len(tools), 111)
            self.assertTrue(all(tool.description and tool.description.strip() for tool in tools))
            self.assertTrue(
                all(
                    input_schema(tool).get("type") == "object"
                    and isinstance(input_schema(tool).get("properties"), dict)
                    for tool in tools
                )
            )
            tool = next(t for t in tools if t.name == "cygnusx_submit_analysis")
            self.assertIn("confirmation_id", input_schema(tool)["properties"])
            result = await client.call_tool(
                tool.name, {"flow_id": "rna_seq", "user_confirmed": True}
            )
            self.assertFalse(result.data["success"])
            with self.assertRaises(ToolError):
                await client.call_tool(tool.name, {})
            result = await client.call_tool("cygnusx_get_task_progress", {"task_id": "isolated"})
            self.assertFalse(result.data["success"])
        self.assertTrue(main.api._client.is_closed)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    os.environ.update(isolated_env())
    import main  # noqa: F401 - Register outside the event loop, like the real entry point.

    unittest.main()
