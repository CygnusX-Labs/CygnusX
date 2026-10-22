"""Real service writes/recall with synthetic ownership and guaranteed cleanup."""
import asyncio
import json
from uuid import uuid4

import acceptance_common as c
from sqlalchemy import delete,select,text
from cygnusx.application.services.agent_memory_service import AgentMemoryService
from cygnusx.application.services.knowledge_index_service import KnowledgeIndexService
from cygnusx.application.services.vector_retrieval_service import VectorRetrievalService
from cygnusx.infrastructure.database.models.agent_memory import MemoryBlockModel,MemoryFactModel,MemoryRecallBatchModel
from cygnusx.infrastructure.database.models.knowledge_document import KbDocumentModel
from cygnusx.infrastructure.database.models.knowledge_chunk import KbChunkModel
from cygnusx.infrastructure.database.models.knowledge_base import KnowledgeBaseModel

async def main():
    user=str(uuid4()); project='mgv3_'+uuid4().hex[:20]
    doc='mgv3_doc_'+uuid4().hex[:20]; kb='mgv3_kb_'+uuid4().hex[:20]
    report={'synthetic_only':True,'database':'omichub','status':'running','checks':{},'real_embedding_source':'configured SiliconFlow Provider via LiteLLMProvider'}
    c.budget.STEP='synthetic_write_recall'
    try:
        facts=[('profile','验收合成用户研究植物单细胞转录组，常用参考基因组 TAIR10。',None),
               ('preference','验收合成偏好：分析结论先提供中文 Markdown 表格，再给简短解释。',None),
               ('project','验收合成项目 Orion 使用 GRCh38，只比较处理组与对照组。',project)]
        ids=[]
        async with c.factory() as db:
            service=AgentMemoryService(db)
            for scope,content,proj in facts:
                result=await service.save_memory(user_id=user,agent_id='agent-general',project_id=proj,content=content,scope=scope,keywords=['验收合成',scope])
                ids.append(int(result['memory']['id']))
            await db.commit()
        async with c.factory() as db:
            rows=(await db.scalars(select(MemoryFactModel).where(MemoryFactModel.user_id==user))).all()
            assert len(rows)==3
            for row in rows:
                assert row.embedding is not None and len(row.embedding)==1024
                assert row.embedding_model==c.get_settings().agent_memory_embedding_model
                if row.scope in ('profile','preference'): assert row.agent_id=='' and row.project_id is None
            report['checks']['write']={'rows':3,'vector_dimensions':1024,'model_labels_match':True,'shared_profile_preference':True}
        # A new DB session and service object represent the next conversation's recall.
        async with c.factory() as db:
            service=AgentMemoryService(db)
            checks=[]
            queries=['我研究什么，参考基因组是什么？','我希望分析结论采用什么格式？','Orion 项目采用什么参考基因组？']
            for i,query in enumerate(queries):
                result=await service.search_memory(user_id=user,agent_id='agent-general',project_id=project,query=query,limit=10)
                assert str(ids[i]) in {x['id'] for x in result['memories']}
                checks.append({'scope':facts[i][0],'target_hit':True})
            report['checks']['cross_session']=checks
            for i in (0,1):
                result=await service.search_memory(user_id=user,agent_id='agent-data',query=queries[i],limit=10)
                assert str(ids[i]) in {x['id'] for x in result['memories']}
            report['checks']['cross_agent_profile_preference']=True
            result=await service.search_memory(user_id=str(uuid4()),agent_id='agent-general',project_id=project,query=queries[2],limit=10)
            assert result['count']==0
            result=await service.search_memory(user_id=user,agent_id='agent-general',project_id='another_synthetic_project',query=queries[2],limit=10)
            assert str(ids[2]) not in {x['id'] for x in result['memories']}
            report['checks']['cross_user_and_project_isolation']=True
        async with c.factory() as db:
            db.add(KnowledgeBaseModel(id=kb,name='MEMORY_GO_LIVE_V3_SYNTHETIC',project_id=project))
            await db.flush()
            document=KbDocumentModel(doc_id=doc,title='Orion 合成验收说明',category='acceptance',file_path='synthetic-memory-go-live.md',status=1,project_id=project,kb_id=kb)
            db.add(document); await db.flush()
            count=await KnowledgeIndexService(db).index_document(document,'# Orion 合成验收\nOrion 合成项目使用 GRCh38，样本按处理组与对照组比较。')
            await db.commit()
            chunks=(await db.scalars(select(KbChunkModel).where(KbChunkModel.document_id==doc))).all()
            assert count>=1 and all(x.embedding is not None and len(x.embedding)==1024 and x.embedding_model==c.get_settings().agent_memory_embedding_model for x in chunks)
        async with c.factory() as db:
            found=await VectorRetrievalService(db).search_knowledge(query='Orion 合成项目参考基因组 GRCh38',project_id=project,limit=10)
            assert doc in {x.doc_id for x in found}
            report['checks']['knowledge']={'chunks':count,'paired_vector_and_model':True,'search_hit':True}
        async with c.factory() as db:
            result=await AgentMemoryService(db).forget_memory(user_id=user,agent_id='agent-general',memory_id=str(ids[2]))
            assert result['forgotten']; await db.commit()
        async with c.factory() as db:
            found=await AgentMemoryService(db).search_memory(user_id=user,agent_id='agent-general',project_id=project,query=queries[2],limit=10)
            assert str(ids[2]) not in {x['id'] for x in found['memories']}
            report['checks']['forget_not_recalled']=True
        report['status']='passed'
    except Exception as exc:
        report.update(status='failed',error_type=type(exc).__name__)
    finally:
        async with c.factory() as db:
            await db.execute(delete(KbChunkModel).where(KbChunkModel.document_id==doc))
            await db.execute(delete(KbDocumentModel).where(KbDocumentModel.doc_id==doc))
            await db.execute(delete(KnowledgeBaseModel).where(KnowledgeBaseModel.id==kb))
            await db.execute(delete(MemoryFactModel).where(MemoryFactModel.user_id==user))
            await db.execute(delete(MemoryBlockModel).where(MemoryBlockModel.user_id==user))
            await db.execute(delete(MemoryRecallBatchModel).where(MemoryRecallBatchModel.user_id==user))
            await db.commit()
            remaining=await db.scalar(select(__import__('sqlalchemy').func.count()).select_from(MemoryFactModel).where(MemoryFactModel.user_id==user))
            assert remaining==0
        report['cleanup']='synthetic facts, blocks, KB and recall receipts removed; owner facts absence verified'
        c.save('e2e-write-recall.json',report)
        await c.engine.dispose()
    print(json.dumps(report,ensure_ascii=False))
    return 0 if report['status']=='passed' else 2

raise SystemExit(asyncio.run(main()))
