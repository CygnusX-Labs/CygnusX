#!/usr/bin/env python3
"""Explicit-DSN memory embedding dry-run/apply tool; defaults to no writes/model calls.

Use MEMORY_MAINTENANCE_DATABASE_URL from your Secret mechanism. Apply resolves an
active Provider from that same database, never from the application's default DB.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

from cygnusx.application.services.memory_embedding_service import (
    BackfillMode,
    MemoryEmbeddingService,
    Storage,
)
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


async def run(
    dsn: str,
    *,
    storage: Storage,
    mode: BackfillMode,
    limit: int,
    apply: bool,
    provider_id: UUID | None = None,
) -> dict[str, Any]:
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
            if not apply:
                await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            await db.execute(text("SET LOCAL statement_timeout = '30s'"))
            client = None
            if apply:
                from cygnusx.infrastructure.ai_provider.litellm_provider import LiteLLMProvider
                from cygnusx.infrastructure.database.repositories.ai_provider_repository import (
                    SqlAlchemyAIProviderConfigRepository,
                )

                repository = SqlAlchemyAIProviderConfigRepository(db)
                config = (
                    await repository.get_by_id(provider_id)
                    if provider_id
                    else await repository.get_default()
                )
                if config is None or not config.is_active:
                    raise ValueError("An active Provider in the maintenance DB is required")
                client = LiteLLMProvider(config)
            service = MemoryEmbeddingService(db, storage=storage, embedding_client=client)
            result = await service.backfill(limit, mode=mode, dry_run=not apply)
            if apply:
                await db.commit()
            service.publish_report(result)
            return result
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage", choices=("facts", "legacy"), default="facts")
    parser.add_argument("--mode", choices=("missing", "mismatch"), default="missing")
    parser.add_argument("--limit", type=int, default=100)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--apply", action="store_true", help="Write at most 500 rows and call the Provider"
    )
    selection.add_argument(
        "--dry-run", action="store_true", help="Default: counts only, no Provider or writes"
    )
    parser.add_argument(
        "--provider-id", type=UUID, help="Optional Provider ID in the explicit maintenance DB"
    )
    parser.add_argument("--output", type=Path, help="Aggregate JSON report, no memory content")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    dsn = os.environ.get("MEMORY_MAINTENANCE_DATABASE_URL", "").strip()
    if not dsn:
        result: dict[str, Any] = {
            "status": "blocked",
            "reason": "MEMORY_MAINTENANCE_DATABASE_URL not configured",
        }
    else:
        try:
            result = asyncio.run(
                run(
                    dsn,
                    storage=args.storage,
                    mode=args.mode,
                    limit=args.limit,
                    apply=args.apply,
                    provider_id=args.provider_id,
                )
            )
        except Exception as exc:
            # Driver/provider errors can include DSNs, source text and credentials.
            result = {"status": "error", "error_type": type(exc).__name__}
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        sys.stdout.write(rendered)
    return 0 if result["status"] in {"dry_run", "completed"} and not result.get("failed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
