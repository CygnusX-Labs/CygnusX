"""Read-only aggregate database verification after all synthetic cleanup."""
import asyncio
import acceptance_common as c
from sqlalchemy import func, select, text
from cygnusx.infrastructure.database.models.agent_memory import MemoryFactModel
from cygnusx.infrastructure.database.models.chat import ChatSessionModel
from cygnusx.infrastructure.database.models.knowledge_document import KbDocumentModel

async def main():
    async with c.factory() as db:
        await db.execute(text('SET TRANSACTION READ ONLY'))
        counts = [dict(r) for r in (await db.execute(select(
            MemoryFactModel.status, func.count().label('rows'),
            func.count().filter(MemoryFactModel.embedding.is_(None)).label('missing')
        ).group_by(MemoryFactModel.status).order_by(MemoryFactModel.status))).mappings()]
        vectors = [dict(r) for r in (await db.execute(text('''
            SELECT status, embedding_model, vector_dims(embedding) AS dimensions, count(*) AS rows
            FROM memory_facts GROUP BY status, embedding_model, vector_dims(embedding) ORDER BY status
        '''))).mappings()]
        sessions = await db.scalar(select(func.count()).select_from(ChatSessionModel).where(
            ChatSessionModel.title == 'MEMORY_GO_LIVE_V3_SYNTHETIC'))
        documents = await db.scalar(select(func.count()).select_from(KbDocumentModel).where(
            KbDocumentModel.doc_id.like('mgv3_doc_%')))
    assert sum(r['rows'] for r in counts) == 11 and all(r['missing'] == 0 for r in counts)
    assert all(r['dimensions'] == 1024 and r['embedding_model'] == 'Qwen/Qwen3-Embedding-8B' for r in vectors)
    assert sessions == documents == 0
    result = {'status':'passed', 'read_only':True, 'memory_status_counts':counts,
        'all_vectors':vectors, 'remaining_marked_synthetic_sessions':sessions,
        'remaining_marked_synthetic_documents':documents}
    c.save('final-database-state.json', result)
    print('{"status":"passed","rows":11,"missing":0,"synthetic_sessions":0,"synthetic_documents":0}')
    await c.engine.dispose()

try:
    asyncio.run(main())
except Exception as exc:
    print('{"status":"failed","error_type":"'+type(exc).__name__+'"}')
    raise SystemExit(2)
