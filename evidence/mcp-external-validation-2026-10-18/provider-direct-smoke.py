#!/usr/bin/env python3
"""Small unauthenticated provider probes; these do not exercise MCP or platform REST."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from cygnusx.application.services.research_data_service import (
    close_research_clients,
    execute_research,
)

CASES: tuple[tuple[str, dict[str, Any], str], ...] = (
    ("cygnusx_te_search", {"query": "CACTA", "limit": 1}, "Dfam"),
    ("cygnusx_expression_studies", {"single_cell": False, "limit": 1}, "Expression Atlas"),
    (
        "cygnusx_expression_studies",
        {"single_cell": True, "limit": 1},
        "Single Cell Expression Atlas",
    ),
    ("cygnusx_domain_get", {"accession": "P04637", "limit": 1}, "InterPro"),
    ("cygnusx_target_search", {"query": "TP53", "limit": 1}, "Open Targets"),
)


async def main() -> None:
    timestamp = datetime.now(UTC).isoformat()
    try:
        for tool_name, arguments, provider in CASES:
            result = await execute_research(tool_name, arguments)
            payload = result.get("data")
            provider_result = payload.get("result") if isinstance(payload, dict) else None
            record = {
                "observed_at_utc": timestamp,
                "provider": provider,
                "tool": tool_name,
                "attempted": True,
                "transport": "direct_https",
                "platform_verified": False,
                "provider_verified": bool(result.get("success")),
                "business_success": bool(result.get("success")),
                "summary": result.get("summary"),
                "result_type": type(provider_result).__name__
                if provider_result is not None
                else None,
                "result_keys": list(provider_result)[:8]
                if isinstance(provider_result, dict)
                else None,
                "partial": bool(provider_result.get("partial"))
                if isinstance(provider_result, dict)
                else False,
            }
            print(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    finally:
        await close_research_clients()


if __name__ == "__main__":
    asyncio.run(main())
