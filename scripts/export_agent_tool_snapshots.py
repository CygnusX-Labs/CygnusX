#!/usr/bin/env python3
"""Export final Agent tool snapshots for an isolated acceptance identity.

This command is read-only with respect to Agent/MCP configuration.  It requires
an explicit test user UUID and writes only schema metadata, filter decisions and
hashed identity references; prompts, messages, credentials and patient data are
never included in the output.

Example::

    uv run python scripts/export_agent_tool_snapshots.py \
      --user-id 00000000-0000-0000-0000-000000000001 \
      --output evidence/mcp-external-validation-2026-10-18/agents-runtime
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from cygnusx.application.services.agent_context_builder import AgentContextBuilder
from cygnusx.application.services.agent_service import AgentService
from cygnusx.application.services.agent_tool_snapshot import build_agent_tool_snapshot
from cygnusx.infrastructure.config.agent_loader import load_agent_configs
from cygnusx.infrastructure.database.session import get_session_factory


def _identity_ref(user_id: UUID) -> str:
    return hashlib.sha256(str(user_id).encode("ascii")).hexdigest()


def _agent_ids(requested: list[str]) -> list[str]:
    configured = [str(item["agent_id"]) for item in load_agent_configs()]
    if not requested:
        return configured
    allowed = set(configured)
    unknown = sorted(set(requested) - allowed)
    if unknown:
        raise ValueError(f"Agent 不在 data/CygnusX.yaml 启用清单中: {', '.join(unknown)}")
    return list(dict.fromkeys(requested))


async def _export(user_id: UUID, agent_ids: list[str], output: Path, context_ref: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    identity_ref = _identity_ref(user_id)
    async with get_session_factory()() as db:
        builder = AgentContextBuilder(
            db,
            agent_service=AgentService(db, reconcile_model_bindings_on_read=False),
        )
        index: list[dict[str, object]] = []
        for agent_id in agent_ids:
            context = await builder.assemble(agent_id, user_id=str(user_id), mode="chat")
            if context is None:
                index.append({"agent_id": agent_id, "status": "unavailable"})
                continue
            snapshot = build_agent_tool_snapshot(context)
            snapshot.update(
                {
                    "status": "assembled",
                    "context_ref": context_ref,
                    "identity_ref": identity_ref,
                    "captured_at_utc": datetime.now(UTC).isoformat(),
                }
            )
            destination = output / f"{agent_id}.json"
            destination.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            index.append(
                {
                    "agent_id": agent_id,
                    "status": "assembled",
                    "final_tool_count": snapshot["final_tool_manifest"]["tool_count"],
                    "schema_bytes": snapshot["final_tool_manifest"]["schema_bytes"],
                    "evidence": destination.name,
                }
            )
        (output / "index.json").write_text(
            json.dumps(
                {
                    "captured_at_utc": datetime.now(UTC).isoformat(),
                    "identity_ref": identity_ref,
                    "context_ref": context_ref,
                    "agent_count": len(agent_ids),
                    "agents": index,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True, help="隔离测试用户 UUID")
    parser.add_argument("--output", required=True, type=Path, help="输出目录")
    parser.add_argument("--context-ref", default="isolated-agent-acceptance")
    parser.add_argument("--agent-id", action="append", default=[])
    args = parser.parse_args()
    try:
        user_id = UUID(args.user_id)
        agent_ids = _agent_ids(args.agent_id)
    except ValueError as exc:
        parser.error(str(exc))
    asyncio.run(_export(user_id, agent_ids, args.output, args.context_ref))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
