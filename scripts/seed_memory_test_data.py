#!/usr/bin/env python3
"""Create synthetic memory fixtures in an explicitly selected disposable DB.

The default mode is a plan-only dry run.  ``--apply`` is required before any
write and the DSN must be supplied with ``--dsn``; no application setting or
DATABASE_URL fallback is consulted.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from cygnusx.infrastructure.database.models.agent_memory import (
    MemoryBlockModel,
    MemoryFactModel,
)
from cygnusx.infrastructure.database.models.ai_provider import AIProviderConfigModel
from cygnusx.infrastructure.database.models.chat import ChatMessageModel, ChatSessionModel
from sqlalchemy import insert, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


def _facts() -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    rows: list[dict[str, Any]] = []
    scopes = ("profile", "preference", "project", "summary", "episode")
    for user_no in (1, 2):
        for index, scope in enumerate(scopes):
            content = f"synthetic fixture u{user_no} {scope} {index}"
            rows.append(
                {
                    "user_id": f"stage0-user-{user_no}",
                    "agent_id": f"stage0-agent-{(user_no - 1) * 2 + index % 2 + 1}",
                    "project_id": f"stage0-project-{(index % 2) + 1}" if scope == "project" else None,
                    "scope": scope,
                    "content": content,
                    "content_hash": hashlib.sha256(content.encode()).hexdigest(),
                    "keywords": ["synthetic", scope],
                    "source_session_id": f"stage0-session-{user_no}",
                    "source_message_ids": [f"stage0-message-{user_no}-{index}"],
                    "importance": (index % 8) + 1,
                    "recall_count": index,
                    "confidence": 0.9,
                    "status": "inactive" if index == 4 else "active",
                    "created_at": now - timedelta(days=index * 30),
                }
            )
    return rows


async def _apply(dsn: str) -> dict[str, int]:
    url = make_url(dsn)
    if url.get_backend_name() != "postgresql":
        raise ValueError("--dsn must use PostgreSQL")
    engine = create_async_engine(url.set(drivername="postgresql+asyncpg"), pool_size=1, max_overflow=0)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            users = {"stage0-user-1", "stage0-user-2"}
            blocks = [
                {
                    "user_id": user,
                    "agent_id": agent,
                    "block_name": name,
                    "content": f"synthetic {name} fixture",
                    "char_limit": 2000,
                    "version": 1,
                    "status": "active",
                }
                for user in users
                for agent in ("stage0-agent-1", "stage0-agent-2")
                for name in ("profile", "preferences", "current_focus")
            ]
            for row in blocks:
                existing = await session.scalar(
                    select(MemoryBlockModel.id).where(
                        MemoryBlockModel.user_id == row["user_id"],
                        MemoryBlockModel.agent_id == row["agent_id"],
                        MemoryBlockModel.block_name == row["block_name"],
                        MemoryBlockModel.project_id.is_(None),
                    )
                )
                if existing is None:
                    await session.execute(insert(MemoryBlockModel).values(**row))
            fact_rows = _facts()
            for row in fact_rows:
                existing = await session.scalar(
                    select(MemoryFactModel.id).where(
                        MemoryFactModel.user_id == row["user_id"],
                        MemoryFactModel.agent_id == row["agent_id"],
                        MemoryFactModel.content_hash == row["content_hash"],
                    )
                )
                if existing is None:
                    await session.execute(insert(MemoryFactModel).values(**row))
            provider = await session.scalar(
                select(AIProviderConfigModel).where(AIProviderConfigModel.name == "stage0-provider")
            )
            if provider is None:
                provider = AIProviderConfigModel(
                    name="stage0-provider",
                    model="stage0-stub",
                    base_url="http://127.0.0.1:9",
                    api_key="",
                    is_active=True,
                    is_default=False,
                )
                session.add(provider)
                await session.flush()
            sessions = 0
            messages = 0
            for user_no in (1, 2):
                for session_no in range(3):
                    session_id = f"stage0-session-{user_no}-{session_no}"
                    existing_session = await session.scalar(
                        select(ChatSessionModel).where(ChatSessionModel.session_id == session_id)
                    )
                    if existing_session is not None:
                        continue
                    chat_session = ChatSessionModel(
                        session_id=session_id,
                        user_id=f"stage0-user-{user_no}",
                        project_id=f"stage0-project-{(session_no % 2) + 1}",
                        model_id=provider.id,
                        title="stage0 synthetic session",
                        message_count=6,
                        mode="agentteams" if session_no == 2 else "chat",
                    )
                    session.add(chat_session)
                    sessions += 1
                    for message_no in range(6):
                        session.add(
                            ChatMessageModel(
                                message_id=f"stage0-message-{user_no}-{session_no}-{message_no}",
                                session_id=session_id,
                                role="user" if message_no % 2 == 0 else "assistant",
                                content=f"synthetic stage0 message {message_no}",
                            )
                        )
                        messages += 1
            await session.commit()
            return {"blocks": len(blocks), "facts": len(fact_rows), "sessions": sessions, "messages": messages}
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True, help="Explicit disposable PostgreSQL DSN")
    parser.add_argument("--apply", action="store_true", help="Write synthetic fixtures")
    args = parser.parse_args()
    plan = {
        "status": "apply" if args.apply else "dry-run",
        "users": 2,
        "agents": 4,
        "projects": 2,
        "sessions": 6,
        "messages": 36,
        "facts": len(_facts()),
        "dsn": "[redacted]",
    }
    if not args.apply:
        print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
        return 0
    try:
        result = asyncio.run(_apply(args.dsn))
    except Exception as exc:  # Never echo DSN, SQL, or row content.
        print(json.dumps({"status": "blocked", "error_type": type(exc).__name__}))
        return 2
    print(json.dumps({**plan, **result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
