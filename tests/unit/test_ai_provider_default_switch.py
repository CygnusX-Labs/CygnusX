"""Default changes must respect the immediate partial unique index in one transaction."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy import Index, create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from cygnusx.infrastructure.database.models.ai_provider import AIProviderConfigModel
from cygnusx.infrastructure.database.repositories.ai_provider_repository import (
    SqlAlchemyAIProviderConfigRepository,
)

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_switch_default_clears_old_before_enabling_new() -> None:
    engine = create_engine("sqlite://")
    table = AIProviderConfigModel.__table__
    # Reproduce the PostgreSQL partial unique index, including an inactive old default.
    index = Index(
        "test_provider_single_default",
        table.c.is_default,
        unique=True,
        sqlite_where=table.c.is_default.is_(True),
    )
    try:
        with engine.begin() as connection:
            table.create(connection)
        with Session(engine, expire_on_commit=False) as db:
            new_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
            old_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
            db.add_all(
                [
                    AIProviderConfigModel(
                        id=new_id, name="new", model="new-model", is_default=False
                    ),
                    AIProviderConfigModel(
                        id=old_id,
                        name="old",
                        model="old-model",
                        is_default=True,
                        is_active=False,
                    ),
                ]
            )
            db.commit()
            # Adapt only the await boundary; all ORM flushes and constraints run on real SQLite.
            async_db = cast(
                AsyncSession,
                SimpleNamespace(
                    execute=AsyncMock(side_effect=db.execute),
                    flush=AsyncMock(side_effect=db.flush),
                ),
            )
            repository = SqlAlchemyAIProviderConfigRepository(async_db)
            await repository.set_default(new_id)
            db.commit()
            rows = db.scalars(select(AIProviderConfigModel)).all()
            assert [row.id for row in rows if row.is_default] == [new_id]
            assert next(row for row in rows if row.id == old_id).is_active is False
            # An idempotent startup sync must also preserve the invariant.
            await repository.set_default(new_id)
            db.commit()
            db.refresh(next(row for row in rows if row.id == new_id))
            assert sum(row.is_default for row in rows) == 1
    finally:
        table.indexes.remove(index)
        engine.dispose()
