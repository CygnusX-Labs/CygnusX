"""MyGene, MyVariant, and MyChem builtin MCP tool contracts."""

from __future__ import annotations

import uuid
from typing import Any

from cygnusx.application.schemas.tool_invocation import ToolInvocationContext
from cygnusx.application.services.biothings_service import (
    describe_biothings,
    execute_biothings,
)

CYGNUSX_BIOTHINGS_SERVER_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "cygnusx-biothings.builtin")
CYGNUSX_BIOTHINGS_SERVER_NAME = "cygnusx-biothings"


def _schema(action: str, kind: str) -> dict[str, Any]:
    common = {"fields": {"type": "string", "maxLength": 3840}}
    if action == "search":
        properties: dict[str, Any] = {
            "query": {"type": "string", "minLength": 1, "maxLength": 2048},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            "offset": {"type": "integer", "minimum": 0, "maximum": 10000, "default": 0},
            **common,
        }
        required = ["query"]
    elif action == "get":
        properties = {
            "identifier": {"type": "string", "minLength": 1, "maxLength": 256},
            **common,
        }
        required = ["identifier"]
    else:
        properties = {
            "identifiers": {
                "type": "array",
                "minItems": 1,
                "maxItems": 100,
                "items": {"type": "string", "minLength": 1, "maxLength": 256},
            },
            "scopes": {"type": "string", "minLength": 1, "maxLength": 256},
            **common,
        }
        required = ["identifiers", "scopes"]
    if kind == "gene":
        properties["species"] = {"type": "string", "minLength": 1, "maxLength": 128}
        required.append("species")
    if kind == "variant":
        properties["assembly"] = {"type": "string", "enum": ["hg19", "hg38"]}
        required.append("assembly")
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


BIOTHINGS_TOOLS: list[dict[str, Any]] = [
    {
        "name": f"cygnusx_{kind}_{action}",
        "description": f"Read-only MyGene/MyVariant/MyChem {action} query with bounded parameters.",
        "inputSchema": _schema(action, kind),
    }
    for kind in ("gene", "variant", "chem")
    for action in ("search", "get", "resolve")
] + [
    {
        "name": "biothings_describe",
        "description": "Describe the supported BioThings provider and default field profile.",
        "inputSchema": {
            "type": "object",
            "properties": {"database": {"type": "string", "enum": ["gene", "variant", "chem"]}},
            "required": ["database"],
            "additionalProperties": False,
        },
    }
]


async def biothings_handler(
    arguments: dict[str, Any],
    *,
    tool_name: str,
    context: ToolInvocationContext | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    del context
    for prefix, database in (
        ("cygnusx_gene_", "gene"),
        ("cygnusx_variant_", "variant"),
        ("cygnusx_chem_", "chem"),
    ):
        if tool_name.startswith(prefix):
            return await execute_biothings(database, tool_name[len(prefix) :], arguments)
    return {"success": False, "summary": "Unknown BioThings tool", "data": None}


async def biothings_describe_handler(
    arguments: dict[str, Any], **_kwargs: Any
) -> dict[str, Any]:
    database = arguments.get("database")
    if not isinstance(database, str):
        return {"success": False, "summary": "database must be gene, variant, or chem", "data": None}
    return await describe_biothings(database)


BIOTHINGS_HANDLERS = {
    **{tool["name"]: biothings_handler for tool in BIOTHINGS_TOOLS[:-1]},
    "biothings_describe": biothings_describe_handler,
}
