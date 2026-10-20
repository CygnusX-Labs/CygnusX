#!/usr/bin/env python3
"""Review or rollback one memory consolidation run on an explicit PostgreSQL DSN.

Set MEMORY_MAINTENANCE_DATABASE_URL through the deployment secret mechanism. The
script never falls back to the application's default database.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from cygnusx.infrastructure.memory.consolidation import MemoryConsolidator
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


async def run(dsn: str, run_key: str, actor: str, *, apply: bool) -> dict[str, Any]:
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
        async with AsyncSession(engine, expire_on_commit=False) as db:
            result = await MemoryConsolidator(db, None).rollback_run(
                run_key, actor, dry_run=not apply
            )
            if not apply:
                await db.rollback()
            return result
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_key")
    parser.add_argument("--actor", required=True, help="管理员标识，写入回滚审计")
    parser.add_argument("--apply", action="store_true", help="提交回滚；默认只做 dry-run")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    dsn = os.environ.get("MEMORY_MAINTENANCE_DATABASE_URL", "").strip()
    if not dsn:
        result: dict[str, Any] = {
            "status": "blocked",
            "reason": "MEMORY_MAINTENANCE_DATABASE_URL not configured",
        }
    else:
        try:
            result = asyncio.run(run(dsn, args.run_key, args.actor, apply=args.apply))
        except Exception as exc:
            result = {"status": "error", "error_type": type(exc).__name__}
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        sys.stdout.write(rendered)
    return 0 if result.get("status") in {"dry_run", "rolled_back"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
