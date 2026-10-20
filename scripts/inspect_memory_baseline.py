#!/usr/bin/env python3
"""Collect content-free, read-only memory migration baseline on an explicit PostgreSQL DSN.

Set MEMORY_ACCEPTANCE_DATABASE_URL via the deployment's secret mechanism. This tool
never falls back to DATABASE_URL, creates schemas, or runs migrations.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

_TABLES = (
    "agent_memories",
    "memory_blocks",
    "memory_facts",
    "memory_settlements",
    "memory_recall_batches",
    "memory_consolidation_runs",
    "memory_consolidation_budgets",
)


async def collect(dsn: str) -> dict[str, Any]:
    url = make_url(dsn)
    if url.get_backend_name() != "postgresql":
        raise ValueError("PostgreSQL required")
    engine = create_async_engine(
        url.set(drivername="postgresql+asyncpg"),
        connect_args={"timeout": 10},
        pool_size=1,
        max_overflow=0,
    )
    try:
        async with engine.connect() as connection, connection.begin():
            # First statement after BEGIN: even accidental mutations are rejected by PostgreSQL.
            await connection.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            await connection.execute(text("SET LOCAL statement_timeout = '10s'"))
            await connection.execute(text("SET LOCAL lock_timeout = '2s'"))
            report: dict[str, Any] = {
                "status": "collected",
                "read_only": True,
                "server_version_num": await connection.scalar(text("SHOW server_version_num")),
                "pgvector_version": await connection.scalar(
                    text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                ),
                "tables": {},
                "limitations": [
                    "Counts only; does not prove migration correctness or snapshot restoration",
                    "Does not run Worker, Beat, Provider or quality cases",
                ],
            }

            def schema(sync: Any) -> dict[str, set[str]]:
                inspector = inspect(sync)
                names = set(inspector.get_table_names())
                return {
                    name: {column["name"] for column in inspector.get_columns(name)}
                    for name in (*_TABLES, "alembic_version")
                    if name in names
                }

            columns = await connection.run_sync(schema)
            if "alembic_version" in columns:
                report["revisions"] = list(
                    (
                        await connection.scalars(
                            text("SELECT version_num FROM alembic_version ORDER BY version_num")
                        )
                    ).all()
                )
            for table in _TABLES:
                if table not in columns:
                    report["tables"][table] = {"present": False}
                    continue
                # Identifiers are fixed source constants, never data/CLI input.
                metrics: dict[str, Any] = {
                    "present": True,
                    "rows": await connection.scalar(text(f'SELECT count(*) FROM "{table}"')),
                }
                dimensions: list[str] = [
                    field for field in ("status", "scope") if field in columns[table]
                ]
                if "agent_id" in columns[table]:
                    dimensions.append(
                        "CASE WHEN agent_id IS NULL OR agent_id = '' THEN true ELSE false END"
                    )
                if dimensions:
                    expression = ", ".join(dimensions)
                    grouped = (
                        await connection.execute(
                            text(
                                f'SELECT {expression}, count(*) FROM "{table}" GROUP BY {expression}'
                            )
                        )
                    ).all()
                    metrics["group_dimensions"] = [
                        "agent_empty" if field.startswith("CASE") else field for field in dimensions
                    ]
                    metrics["group_counts"] = sorted([list(row) for row in grouped], key=str)
                if table == "memory_blocks":
                    metrics["shared_personal_blocks"] = await connection.scalar(
                        text(
                            "SELECT count(*) FROM memory_blocks WHERE agent_id = '' "
                            "AND block_name IN ('profile', 'preferences')"
                        )
                    )
                if table == "memory_facts" and "embedding" in columns[table]:
                    metrics["without_embedding"] = await connection.scalar(
                        text("SELECT count(*) FROM memory_facts WHERE embedding IS NULL")
                    )
                metrics["bytes"] = await connection.scalar(
                    text(f"SELECT pg_total_relation_size('{table}'::regclass)")
                )
                report["tables"][table] = metrics
            return report
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, help="Write aggregate JSON; never includes memory text"
    )
    args = parser.parse_args()
    dsn = os.environ.get("MEMORY_ACCEPTANCE_DATABASE_URL", "").strip()
    if not dsn:
        report = {"status": "blocked", "reason": "MEMORY_ACCEPTANCE_DATABASE_URL not configured"}
        result = 2
    else:
        try:
            report = asyncio.run(collect(dsn))
            result = 0
        except Exception as exc:
            # Driver exceptions can include passwords/DSNs/SQL parameters: emit type only.
            report = {"status": "blocked", "error_type": type(exc).__name__}
            result = 2
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        sys.stdout.write(rendered)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
