"""Secret-free Agent tool snapshots for runtime acceptance evidence."""

from __future__ import annotations

from typing import Any

from cygnusx.application.services.tool_manifest import build_tool_manifest


def build_agent_tool_snapshot(context: Any) -> dict[str, Any]:
    """Serialize one assembled Agent context without prompts, messages, or secrets."""
    tools = [item for item in (getattr(context, "tools", None) or []) if isinstance(item, dict)]
    manifest = build_tool_manifest(tools, getattr(context, "mcp_servers", None))
    decisions = [
        dict(item)
        for item in (getattr(context, "tool_filter_decisions", None) or [])
        if isinstance(item, dict)
    ]
    decisions.sort(
        key=lambda item: (
            str(item.get("tool_name") or ""),
            str(item.get("server_id") or ""),
            str(item.get("reason") or ""),
        )
    )
    manifest_tools = list(manifest["tools"])
    return {
        "agent_id": str(getattr(getattr(context, "agent", None), "agent_id", "unknown")),
        "agent_name": str(getattr(getattr(context, "agent", None), "name", "unknown")),
        "user_capabilities_customized": bool(
            getattr(context, "user_capabilities_customized", False)
        ),
        "bound_servers": [
            {
                "server": str(getattr(server, "name", "unknown")),
                "server_id": str(getattr(server, "id", "unknown")),
                "enabled": bool(getattr(server, "is_enabled", False)),
            }
            for server in (getattr(context, "mcp_servers", None) or [])
        ],
        "final_tool_manifest": manifest,
        "biothings_count": sum(
            str(item.get("server") or "") == "cygnusx-biothings" for item in manifest_tools
        ),
        "research_data_count": sum(
            str(item.get("server") or "") == "cygnusx-research-data" for item in manifest_tools
        ),
        "tool_filter_decisions": decisions,
    }
