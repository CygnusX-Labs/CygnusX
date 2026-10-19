"""Deterministic, secret-free manifests for tools sent to an LLM provider."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def build_tool_manifest(
    tools: list[dict[str, Any]], servers: list[Any] | None = None
) -> dict[str, Any]:
    """Serialize the exact provider tool schemas without request or credential data."""
    source_by_name: dict[str, dict[str, str]] = {}
    for server in servers or []:
        server_name = str(getattr(server, "name", "") or "unknown")
        server_id = str(getattr(server, "id", "") or "unknown")
        for registered in getattr(server, "tools", []) or []:
            name = str(getattr(registered, "tool_name", "") or "")
            if name and name not in source_by_name:
                source_by_name[name] = {"server": server_name, "server_id": server_id}

    entries: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for item in tools:
        if not isinstance(item, dict):
            continue
        function = item.get("function")
        if not isinstance(function, dict):
            continue
        name = str(function.get("name") or "").strip()
        if not name:
            continue
        if name in seen_names:
            continue
        seen_names.add(name)
        description = str(function.get("description") or "")
        schema = function.get("parameters")
        if not isinstance(schema, dict):
            schema = {"type": "object", "properties": {}}
        contract = {"name": name, "description": description, "inputSchema": schema}
        source = source_by_name.get(name, {"server": "runtime", "server_id": "unknown"})
        entries.append(
            {
                "name": name,
                "description": description,
                "inputSchema": schema,
                "server": source["server"],
                "server_id": source["server_id"],
                "contract_digest": _digest(contract),
                "schema_bytes": len(_canonical(schema).encode("utf-8")),
            }
        )

    return {
        "tool_count": len(entries),
        "schema_bytes": sum(int(item["schema_bytes"]) for item in entries),
        "manifest_sha256": _digest(entries),
        "tools": entries,
    }
