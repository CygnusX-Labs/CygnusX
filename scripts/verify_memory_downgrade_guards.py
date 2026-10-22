"""Re-run existing downgrade guards in an isolated schema; explicit test DSN only."""
import asyncio
import importlib.util
import json
import os
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


async def main() -> None:
    url = make_url(os.environ['MEMORY_TEST_DATABASE_URL'])
    if not (url.database or '').startswith('memory_acceptance_test'):
        raise ValueError('Dedicated memory_acceptance_test database required')
    engine = create_async_engine(url.set(drivername='postgresql+asyncpg'))
    schema = 'guard_' + uuid4().hex
    cases = [
        ('0-B3a', 'memory_focus_project01_scope_focus_blocks.py',
         'memory_blocks', 'project_id TEXT', "INSERT INTO memory_blocks VALUES ('synthetic')"),
        ('0-B3b', 'memory_consolidate01_add_consolidation_ledger.py',
         'memory_consolidation_runs', 'kind TEXT',
         "INSERT INTO memory_consolidation_runs VALUES ('synthetic')"),
        ('0-B3c', 'memory_episode01_expand_fact_content.py',
         'memory_facts', 'content VARCHAR(1200)',
         "INSERT INTO memory_facts VALUES (repeat('x',301))"),
        ('0-B3d', 'memory_consolidate_rollback01.py',
         'memory_consolidation_runs', 'kind TEXT, rolled_back_at TIMESTAMPTZ',
         "INSERT INTO memory_consolidation_runs VALUES ('rollback',now())"),
    ]
    try:
        for case, filename, table, columns, insert in cases:
            async with engine.begin() as conn:
                await conn.execute(text(f'CREATE SCHEMA {schema}'))
                await conn.execute(text(f'SET LOCAL search_path TO {schema},public'))
                await conn.execute(text(f'CREATE TABLE {table} ({columns})'))
                await conn.execute(text(insert))
                spec = importlib.util.spec_from_file_location('guard', 'alembic/versions/' + filename)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                def run(sync, module=module):
                    module.op = Operations(MigrationContext.configure(sync))
                    try:
                        module.downgrade()
                    except RuntimeError as exc:
                        return {'exception': type(exc).__name__, 'message': str(exc)}
                    raise AssertionError('Guard did not reject downgrade')

                result = await conn.run_sync(run)
                count = await conn.scalar(text(f'SELECT count(*) FROM {table}'))
                assert count == 1
                print(json.dumps({'case': case, **result, 'before': 1, 'after': count}))
                await conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
