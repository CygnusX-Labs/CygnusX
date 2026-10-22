"""Additional zero-call checks against the retained Stage 1 schema."""
import asyncio
import importlib.util
import json
import math
import os
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cygnusx.application.services.agent_memory_service import AgentMemoryService
from cygnusx.core.config import Settings
from cygnusx.infrastructure.memory.fact_store import MemoryFactCreate, PostgresFactStore
from scripts.verify_memory_stage1_zero import OUT, save
from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


async def main():
    url = make_url(os.environ['MEMORY_MAINTENANCE_DATABASE_URL'])
    assert url.database == 'cygnusx_maint'
    schema = json.loads((OUT/'environment.json').read_text())['schema']
    assert schema.startswith('stage1_') and schema.replace('_', '').isalnum()
    engine = create_async_engine(url.set(drivername='postgresql+asyncpg'),
        connect_args={'server_settings': {'search_path': schema + ',public'}})
    settings = Settings(_env_file=None, agent_memory_embedding_model='synthetic-current',
        memory_embedding_model_filter_enabled=True, memory_hybrid_retrieval_enabled=True,
        memory_hybrid_min_similarity=0.9)
    statements = []

    @event.listens_for(engine.sync_engine, 'before_cursor_execute')
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    try:
        spec = importlib.util.spec_from_file_location('cli','scripts/backfill_memory_embeddings.py')
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        client = Mock(side_effect=AssertionError('No Provider allowed'))
        with patch('cygnusx.application.services.agent_memory_service.get_settings',return_value=settings), patch(
            'cygnusx.application.services.memory_embedding_service.get_settings',return_value=settings):
            with patch.object(cli,'create_async_engine',return_value=engine),patch(
                'cygnusx.infrastructure.ai_provider.litellm_provider.LiteLLMProvider',client):
                statements.clear()
                dry = await cli.run(url.render_as_string(hide_password=False),storage='facts',mode='missing',limit=100,apply=False)
                writes = [s.split()[0] for s in statements if s.strip().upper().startswith(('UPDATE ','INSERT ','DELETE '))]
                assert not writes and client.call_count == 0 and dry['updated'] == 0
                save('B1.json',{'result':dry,'provider_constructions':client.call_count,'write_statements_during_dry_run':writes})
            q = [1.0]+[0.0]*1023
            async with AsyncSession(engine) as db:
                store = PostgresFactStore(db)
                high = await store.insert(MemoryFactCreate('rrf-owner','a','project','synthetic needle high',project_id='p',embedding=q,embedding_model='synthetic-current'))
                old = await store.insert(MemoryFactCreate('rrf-owner','a','project','synthetic needle old',project_id='p',embedding=q,embedding_model='synthetic-old'))
                low = await store.insert(MemoryFactCreate('rrf-owner','a','project','synthetic orthogonal',project_id='p',embedding=[0.0,1.0]+[0.0]*1022,embedding_model='synthetic-current'))
                await db.commit()
                v,k = await store.hybrid_candidates('rrf-owner','a',q,['needle'],embedding_model='synthetic-current',min_similarity=0.9,project_id='p')
                assert [x.id for x in v] == [high.id] and old.id in {x.id for x in k}
                assert low.id not in {x.id for x in v}
                merged = await AgentMemoryService(db)._search_facts_merged('rrf-owner','a',q,query='needle',limit=10,project_id='p')
                assert {x.id for x in merged} == {high.id,old.id}
                expected = {}
                for lane in (v,k):
                    for rank,f in enumerate(lane,1):
                        expected[f.id] = expected.get(f.id,0)+1/(settings.memory_hybrid_rrf_k+rank)
                maximum = 2/(settings.memory_hybrid_rrf_k+1)
                assert all(math.isclose(f.similarity,expected[f.id]/maximum) for f in merged)
                save('D-hybrid.json',{'vector_current_only':True,'old_model_keyword_only':True,'low_vector_excluded':True,'rrf_scores_match_independent_formula':True,'merged_count':len(merged),'min_similarity':0.9})
                # Verify server-side readonly actually rejects DML.
                await db.rollback()
                await db.execute(text('SET TRANSACTION READ ONLY'))
                try:
                    await db.execute(text('UPDATE memory_facts SET importance=importance WHERE false'))
                except Exception as exc:
                    rejected = type(exc).__name__
                    await db.rollback()
                else:
                    raise AssertionError('Read-only DML not rejected')
                save('C-readonly.json',{'dml_rejected':True,'error_type':rejected})
                from cygnusx.application.services.knowledge_index_service import (
                    KnowledgeIndexService,
                )
                from cygnusx.application.services.vector_retrieval_service import (
                    VectorRetrievalService,
                )
                from cygnusx.infrastructure.database.models.knowledge_chunk import KbChunkModel
                from sqlalchemy import select
                for table in ('knowledge_bases', 'kb_documents', 'kb_chunks'):
                    await db.execute(text(f'CREATE TABLE {table} (LIKE public.{table} INCLUDING ALL)'))
                await db.execute(text("""INSERT INTO kb_documents
                    (id,doc_id,title,category,file_path,status,created_at,updated_at)
                    VALUES (gen_random_uuid(),'stage1-synthetic','Synthetic','test','stage1-no-assets.md',1,now(),now())"""))
                settings.agent_memory_embedding_model = ''
                forbidden = SimpleNamespace(embeddings=Mock(side_effect=AssertionError('No model call')))
                doc = SimpleNamespace(doc_id='stage1-synthetic',file_path='stage1-no-assets.md')
                with patch('cygnusx.application.services.knowledge_index_service.get_settings',return_value=settings):
                    count = await KnowledgeIndexService(db,forbidden).index_document(doc,'# Synthetic\nneedle synthetic fixture',include_unreferenced_assets=False)
                await db.commit()
                rows = (await db.scalars(select(KbChunkModel))).all()
                assert count == 1 and all(r.embedding is None and r.embedding_model is None for r in rows)
                with patch('cygnusx.core.config.get_settings',return_value=settings):
                    hits = await VectorRetrievalService(db,forbidden).search_knowledge(query='needle')
                assert hits and forbidden.embeddings.call_count == 0
                save('E-no-config.json',{'chunks':count,'paired_null':True,'keyword_hits':len(hits),'provider_calls':0})

    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
