"""Stage 1 zero-provider-call evidence on an explicit disposable maintenance DB."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import random
import statistics
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from cygnusx.application.services.agent_memory_service import AgentMemoryService
from cygnusx.application.services.memory_embedding_service import MemoryEmbeddingService
from cygnusx.core.config import Settings
from cygnusx.infrastructure.database.models.agent_memory import AgentMemoryModel, MemoryFactModel
from cygnusx.infrastructure.memory.fact_store import MemoryFactCreate, PostgresFactStore
from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

OUT = Path('evidence/memory-stage1-v2')


def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str))


async def main():
    url = make_url(os.environ['MEMORY_MAINTENANCE_DATABASE_URL'])
    if url.database != 'cygnusx_maint' or url.get_backend_name() != 'postgresql':
        raise ValueError('Explicit disposable cygnusx_maint required')
    schema = 'stage1_' + uuid4().hex[:12]
    engine = create_async_engine(url.set(drivername='postgresql+asyncpg'),
        connect_args={'server_settings': {'search_path': schema + ',public'}})
    settings = Settings(_env_file=None, agent_memory_embedding_model='synthetic-current',
        memory_v2_enabled=True, memory_embedding_coverage_enabled=True,
        memory_embedding_coverage_interval_seconds=300)
    patches = [patch(p, return_value=settings) for p in (
        'cygnusx.application.services.agent_memory_service.get_settings',
        'cygnusx.application.services.memory_embedding_service.get_settings',
        'cygnusx.core.config.get_settings')]
    for p in patches:
        p.start()
    sqls = []

    @event.listens_for(engine.sync_engine, 'before_cursor_execute')
    def capture(conn, cursor, statement, parameters, context, executemany):
        sqls.append(statement)

    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA {schema}'))
            await conn.run_sync(MemoryFactModel.__table__.create)
            await conn.run_sync(AgentMemoryModel.__table__.create)
            versions = (await conn.execute(text("SELECT current_setting('server_version'), (SELECT extversion FROM pg_extension WHERE extname='vector'), (SELECT version_num FROM public.alembic_version)"))).one()
        save('environment.json', {'schema': schema, 'database': url.database,
            'postgres': versions[0], 'pgvector': versions[1], 'head': versions[2],
            'flags': {k: v for k, v in settings.model_dump().items() if k.startswith('memory_') or k == 'agent_memory_embedding_model'}})
        spec = importlib.util.spec_from_file_location('backfill_cli', 'scripts/backfill_memory_embeddings.py')
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        # Exercise the existing CLI main parser and run function, injecting only the explicit engine.
        client = AsyncMock(side_effect=AssertionError('Provider must never be constructed'))
        async with AsyncSession(engine) as db:
            await PostgresFactStore(db).insert(MemoryFactCreate('fixture-owner', 'a', 'project', 'synthetic missing'))
            await db.commit()
        sqls.clear()
        with patch.object(cli, 'create_async_engine', return_value=engine), patch(
            'cygnusx.infrastructure.ai_provider.litellm_provider.LiteLLMProvider', client):
            dry = await cli.run(url.render_as_string(hide_password=False), storage='facts',
                mode='missing', limit=100, apply=False)
        assert dry['status'] == 'dry_run' and dry['pending'] == 1 and dry['updated'] == 0
        assert client.call_count == 0
        save('B1.json', {'result': dry, 'provider_constructions': client.call_count,
            'write_statements_during_dry_run': [s.split()[0] for s in sqls if s.lstrip().upper().startswith(('UPDATE ', 'INSERT ', 'DELETE '))]})
        # Four degradation paths; actual _embed + actual FactStore persistence.
        outcomes = Counter()
        metric = SimpleNamespace(add=lambda n, labels: outcomes.update({labels['result']: n}))
        from loguru import logger
        logger.disable('cygnusx.application.services.agent_memory_service')
        faults = {'dimension_mismatch': [1.0], 'empty': [], 'non_finite': [float('nan')]*1024,
                  'provider_error': ConnectionError('synthetic endpoint unavailable')}
        checks = {}
        with patch('cygnusx.application.services.agent_memory_service._embedding_outcomes', metric):
            async with AsyncSession(engine) as db:
                for label, value in faults.items():
                    provider = SimpleNamespace(embeddings=AsyncMock(**(
                        {'side_effect': value} if isinstance(value, Exception) else {'return_value': value})))
                    v = await AgentMemoryService(db, provider)._embed('synthetic fault')
                    assert v == []
                    fact = await PostgresFactStore(db).insert(MemoryFactCreate(
                        'fixture-owner', 'a', 'project', 'synthetic fault ' + label,
                        embedding=v or None, embedding_model=settings.agent_memory_embedding_model))
                    row = await db.get(MemoryFactModel, fact.id)
                    assert row.embedding is None and row.embedding_model is None
                    checks[label] = {'embedding_null': True, 'model_null': True}
                await db.commit()
        assert outcomes == Counter({k: 1 for k in faults})
        save('A2.json', {'faults': checks, 'metrics': dict(outcomes), 'real_calls': 0,
                        'provider_error_injection': 'mock ConnectionError; no network endpoint request'})
        # Read-only coverage both storages and runtime task gate re-check.
        readings = []
        gauges = {n: SimpleNamespace(set=lambda value, attrs, n=n: readings.append(
            {'metric': n, 'value': value, 'storage': attrs['storage']})) for n in ('_mismatch','_coverage','_sample_time')}
        with patch.multiple('cygnusx.application.services.memory_embedding_service', **gauges):
            async with AsyncSession(engine) as db:
                await db.execute(text('SET TRANSACTION READ ONLY'))
                ro = await db.scalar(text('SHOW transaction_read_only'))
                facts = await MemoryEmbeddingService(db).coverage()
                legacy = await MemoryEmbeddingService(db, storage='legacy').coverage()
                assert ro == 'on' and legacy['coverage'] == 0 and legacy['active'] == 0
            from cygnusx.infrastructure.celery_app.tasks.memory import _collect_embedding_coverage
            factory = async_sessionmaker(engine)
            with patch('cygnusx.infrastructure.database.session.get_session_factory', return_value=factory), patch(
                'cygnusx.application.services.memory_runtime_policy.is_memory_runtime_enabled', AsyncMock(return_value=False)) as gate:
                closed = await _collect_embedding_coverage()
                assert closed['status'] == 'disabled' and gate.await_count == 1
            # Gate returns true in test; data read is real PG.
            with patch('cygnusx.infrastructure.database.session.get_session_factory', return_value=factory), patch(
                'cygnusx.application.services.memory_runtime_policy.is_memory_runtime_enabled', AsyncMock(return_value=True)) as gate:
                opened = await _collect_embedding_coverage()
                assert opened['status'] == 'collected' and gate.await_count == 1
            from cygnusx.infrastructure.celery_app.celery import celery_app
            schedule = celery_app.conf.beat_schedule['memory-embedding-coverage']
            assert schedule['schedule'] == 300 and schedule['options']['queue'] == 'analysis'
        save('C.json', {'read_only_transaction': ro, 'facts': facts, 'legacy_empty': legacy,
            'metrics': readings, 'gate_closed': closed, 'gate_open': opened,
            'schedule': schedule, 'task_gate': 'injected closed/open; real PG coverage'})
        # Local random generation, 10,000 independent 1024-dimensional vectors.
        rng = random.Random(20261021)
        async with engine.begin() as conn:
            for offset in range(0, 10000, 100):
                rows = [{'i': str(i), 'v': '[' + ','.join(f'{rng.uniform(-1,1):.6f}' for _ in range(1024)) + ']',
                         'm': 'synthetic-current' if i % 2 == 0 else 'synthetic-old'}
                        for i in range(offset, offset+100)]
                await conn.execute(text("""INSERT INTO memory_facts
                    (user_id,agent_id,project_id,scope,content,content_hash,embedding,embedding_model,
                     confidence,status,created_at)
                    VALUES ('perf-owner','a','p','project','synthetic needle',CAST(:i AS text),
                            CAST(:v AS vector),:m,0.8,'active',now())"""), rows)
            await conn.execute(text('ANALYZE memory_facts'))
        query = [rng.uniform(-1,1) for _ in range(1024)]
        perf = {}
        async with AsyncSession(engine) as db:
            store = PostgresFactStore(db)
            for filtered in (False, True):
                settings.memory_embedding_model_filter_enabled = filtered
                sqls.clear()
                durations = []
                for _ in range(50):
                    start = time.perf_counter()
                    result = await AgentMemoryService(db)._search_facts_merged(
                        'perf-owner', 'a', query, limit=10, query='', project_id='p')
                    durations.append((time.perf_counter()-start)*1000)
                # Capture the executed ORM FactStore SQL and use its actual SQL shape for EXPLAIN.
                vector_sql = next(s for s in sqls if '<=>' in s)
                plan_sql = """EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT * FROM memory_facts
                    WHERE user_id='perf-owner' AND agent_id='a' AND status='active'
                    AND (project_id IS NULL OR project_id='p') AND embedding IS NOT NULL"""
                if filtered:
                    plan_sql += " AND embedding_model='synthetic-current'"
                plan_sql += ' ORDER BY embedding <=> CAST(:v AS vector) LIMIT 10'
                plan = await db.scalar(text(plan_sql), {'v': json.dumps(query)})
                # Strip identifiers and content from plan output before evidence retention.
                rendered = json.dumps(plan).replace('perf-owner', '[fixture-owner]')
                save('D-plan-filter-' + str(filtered) + '.json', json.loads(rendered))
                perf[str(filtered)] = {'samples': 50, 'p50_ms': statistics.median(durations),
                    'p95_ms': sorted(durations)[47], 'min_ms': min(durations), 'max_ms': max(durations),
                    'hnsw_used': 'hnsw' in rendered, 'model_predicate_in_orm_sql': 'embedding_model =' in vector_sql,
                    'rows_returned': len(result), 'raw_ms': durations}
                if filtered:
                    assert 'embedding_model =' in vector_sql
                    assert all(f.embedding_model == settings.agent_memory_embedding_model for f in result)
            vectors, keywords = await store.hybrid_candidates('perf-owner','a',query,['needle'],
                embedding_model='synthetic-current',min_similarity=0.9,project_id='p')
            assert not vectors and keywords
            settings.memory_hybrid_retrieval_enabled = True
            settings.memory_hybrid_min_similarity = 0.9
            merged = await AgentMemoryService(db)._search_facts_merged('perf-owner','a',query,
                limit=10,query='needle',project_id='p')
            assert merged and all(f.project_id == 'p' for f in merged)
            perf['hybrid'] = {'vector_candidates_above_0_9': len(vectors),
                'keyword_candidates': len(keywords), 'merged': len(merged),
                'low_similarity_excluded': True, 'partition_preserved': True}
        save('D.json', {'random_rows': 10000, 'dimensions': 1024,
            'planner_settings': 'defaults; no enable_seqscan override', 'results': perf})
        save('summary.json', {'status': 'completed', 'real_embedding_calls': 0, 'schema': schema})
        print('zero-call evidence completed')
    finally:
        for p in patches:
            p.stop()
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
