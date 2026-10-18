"""Shared compact MCP result envelope for research-provider adapters."""

from __future__ import annotations

import asyncio
import json
import weakref
from typing import Any

import httpx

MAX_TOOL_RESULT_BYTES = 3000
_CLIENTS: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient] = (
    weakref.WeakKeyDictionary()
)


def provider_client(timeout: httpx.Timeout) -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    client = _CLIENTS.get(loop)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(timeout=timeout, follow_redirects=False)
        _CLIENTS[loop] = client
    return client


async def close_provider_clients() -> None:
    clients = list(_CLIENTS.values())
    _CLIENTS.clear()
    for client in clients:
        await client.aclose()


def _compact(value: Any, *, text_limit: int, item_limit: int, depth: int) -> Any:
    if isinstance(value, str):
        return value if len(value) <= text_limit else value[:text_limit] + " [truncated]"
    if isinstance(value, list):
        items = [
            _compact(item, text_limit=text_limit, item_limit=item_limit, depth=depth - 1)
            for item in value[:item_limit]
        ]
        if len(value) > item_limit:
            items.append({"truncated_items": len(value) - item_limit})
        return items
    if isinstance(value, dict):
        if depth <= 0:
            return {"truncated": True}
        result = {
            str(key): _compact(item, text_limit=text_limit, item_limit=item_limit, depth=depth - 1)
            for key, item in list(value.items())[:item_limit]
        }
        if len(value) > item_limit:
            result["truncated_fields"] = len(value) - item_limit
        return result
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:text_limit]


def _json_size(value: dict[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def envelope(success: bool, summary: str, data: Any = None) -> dict[str, Any]:
    original = {"success": success, "summary": summary, "data": data}
    if _json_size(original) <= MAX_TOOL_RESULT_BYTES:
        return original

    for text_limit, item_limit, depth in ((512, 10, 6), (192, 5, 4), (64, 2, 2)):
        result = {
            "success": success,
            "summary": summary[:256],
            "data": _compact(data, text_limit=text_limit, item_limit=item_limit, depth=depth),
            "truncated": True,
        }
        if _json_size(result) <= MAX_TOOL_RESULT_BYTES:
            return result

    fallback = {
        "success": success,
        "summary": summary[:128],
        "data": {"truncated": True, "preview": "Result exceeded the 3000-byte MCP output budget."},
        "truncated": True,
    }
    return fallback
