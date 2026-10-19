"""Capture the current MCP tool contract across runtime and all transports."""

from __future__ import annotations

import asyncio
import csv
import json
import os
import socket
import sys
from pathlib import Path

import httpx
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

ROOT = Path(__file__).resolve().parents[2] / "mcp-server"
EVIDENCE = Path(__file__).resolve().parent
TOKEN = "isolated-capture-token-12345678901234567890"
sys.path.insert(0, str(ROOT))


def isolated_env() -> dict[str, str]:
    return {
        **os.environ,
        "CYGNUSX_BASE_URL": "http://127.0.0.1:1",
        "CYGNUSX_API_KEY": "isolated-not-a-production-key",
        "CYGNUSX_HOST": "127.0.0.1",
        "CYGNUSX_HTTP_TOKEN": TOKEN,
        "CYGNUSX_REQUEST_TIMEOUT": "1",
    }


def contract(tool: object) -> dict[str, object]:
    data = tool.model_dump(by_alias=True, mode="json", exclude_none=True)
    return {
        "name": data["name"],
        "inputSchema": data.get("inputSchema", data.get("input_schema")),
        "description": data.get("description"),
    }


async def snapshot(client: Client) -> list[dict[str, object]]:
    async with client:
        tools = await client.list_tools()
    return sorted((contract(tool) for tool in tools), key=lambda item: item["name"])


async def capture_process(transport: str, path: str) -> list[dict[str, object]]:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "main.py",
        "--transport",
        transport,
        "--port",
        str(port),
        cwd=ROOT,
        env=isolated_env(),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}{path}"
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=1) as http:
            for _ in range(100):
                if process.returncode is not None:
                    raise RuntimeError(f"{transport} server exited before startup")
                try:
                    if transport == "sse":
                        response = await http.get(url)
                    else:
                        response = await http.post(url, json={})
                    if response.status_code in {200, 401}:
                        break
                except httpx.ConnectError:
                    pass
                await asyncio.sleep(0.1)
            else:
                raise TimeoutError(f"{transport} server startup timed out")
        client = Client(url, auth=TOKEN, timeout=10)
        return await snapshot(client)
    finally:
        process.terminate()
        await asyncio.wait_for(process.wait(), 10)


async def main() -> None:
    os.environ.update(isolated_env())
    from main import mcp

    surfaces = {
        "runtime": await snapshot(Client(mcp, timeout=10)),
        "stdio": await snapshot(
            Client(
                StdioTransport(
                    sys.executable,
                    ["main.py"],
                    env=isolated_env(),
                    cwd=str(ROOT),
                    log_file=None,
                ),
                timeout=10,
            )
        ),
        "streamable_http": await capture_process("streamable-http", "/mcp"),
        "sse": await capture_process("sse", "/sse"),
    }
    for name, tools in surfaces.items():
        (EVIDENCE / f"current-{name}-tools.json").write_text(
            json.dumps(tools, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    reference = surfaces["runtime"]
    diffs = []
    for name, tools in surfaces.items():
        left = {tool["name"]: tool for tool in reference}
        right = {tool["name"]: tool for tool in tools}
        changed = [
            {"name": key, "fields": [field for field in ("inputSchema", "description") if left[key][field] != right[key][field]]}
            for key in sorted(left.keys() & right.keys())
            if any(left[key][field] != right[key][field] for field in ("inputSchema", "description"))
        ]
        diffs.append(
            {
                "comparison": f"runtime_vs_{name}",
                "left_count": len(left),
                "right_count": len(right),
                "missing_names": sorted(left.keys() - right.keys()),
                "extra_names": sorted(right.keys() - left.keys()),
                "schema_or_description_changed": changed,
            }
        )
    (EVIDENCE / "current-four-surface-schema-diff.json").write_text(
        json.dumps(diffs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "schema-diff.json").write_text(
        json.dumps(diffs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    old_tools = {
        item["name"]: item
        for item in (
            json.loads(line)
            for line in (EVIDENCE / "stdio-tools-list.ndjson").read_text(encoding="utf-8").splitlines()
        )
    }
    current_tools = {item["name"]: item for item in reference}
    description_changes = [
        {
            "name": name,
            "old_description": old_tools[name].get("description", ""),
            "new_description": current_tools[name].get("description", ""),
            "source": "handler docstring; tools.yaml synchronized",
            "reason": "修复原审计标记的模糊描述，并补充真实参数、返回语义或行为边界",
        }
        for name in sorted(old_tools.keys() & current_tools.keys())
        if old_tools[name].get("description") != current_tools[name].get("description")
    ]
    with (EVIDENCE / "description-changes.tsv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=description_changes[0].keys(), delimiter="\t")
        writer.writeheader()
        writer.writerows(description_changes)

    before_after = {
        "before": "saved STDIO tools/list snapshot captured 2026-10-18 before this description patch",
        "after": "current in-process runtime snapshot captured by this script",
        "before_count": len(old_tools),
        "after_count": len(current_tools),
        "name_set_changed": sorted(old_tools.keys() ^ current_tools.keys()),
        "input_schema_changed": sorted(
            name
            for name in old_tools.keys() & current_tools.keys()
            if old_tools[name].get("inputSchema") != current_tools[name].get("inputSchema")
        ),
        "description_changed": [item["name"] for item in description_changes],
        "handler_binding": "not independently compared; pre-patch handler map was not captured",
    }
    (EVIDENCE / "before-after-contract-diff.json").write_text(
        json.dumps(before_after, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({item["comparison"]: item["right_count"] for item in diffs}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
