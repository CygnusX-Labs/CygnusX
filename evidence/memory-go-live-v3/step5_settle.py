import asyncio,json,copy
from datetime import datetime,timedelta,timezone
from uuid import uuid4

import acceptance_common as c
from sqlalchemy import delete,func,select
from cygnusx.infrastructure.database.models.agent_memory import MemoryFactModel,MemoryBlockModel,MemorySettlementModel,MemoryRecallBatchModel
from cygnusx.infrastructure.database.models.chat import ChatSessionModel,ChatMessageModel
from cygnusx.infrastructure.database.models.agent import AgentTemplateModel
from cygnusx.infrastructure.database.repositories.ai_provider_repository import SqlAlchemyAIProviderConfigRepository
from cygnusx.infrastructure.ai_provider.litellm_provider import LiteLLMProvider
from cygnusx.infrastructure.celery_app.tasks.memory import _settle_session_memory_v2

async def main():
    user=str(uuid4());sid='mgv3_settle_'+uuid4().hex[:24]
    settings=c.get_settings();production_model=settings.memory_extraction_model
    report={'status':'running','synthetic_only':True,'session_marker':'MEMORY_GO_LIVE_V3_SYNTHETIC','production_defaults_modified':False}
    original_chat=LiteLLMProvider.chat
    async def append(messages,offset):
        ids=[]
        async with c.factory() as db:
            for i,(role,content) in enumerate(messages):
                mid='mgv3_msg_'+uuid4().hex
                db.add(ChatMessageModel(message_id=mid,session_id=sid,role=role,content=content,created_at=datetime.now(timezone.utc)+timedelta(seconds=offset+i),metadata_json={'memory_go_live_synthetic':True}))
                ids.append(mid)
            await db.commit()
        return ids
    async def state():
        async with c.factory() as db:
            session=await db.scalar(select(ChatSessionModel).where(ChatSessionModel.session_id==sid))
            count=await db.scalar(select(func.count()).select_from(MemorySettlementModel).where(MemorySettlementModel.session_id==sid))
            facts=(await db.scalars(select(MemoryFactModel).where(MemoryFactModel.user_id==user,MemoryFactModel.scope!='episode',MemoryFactModel.status=='active'))).all()
            return {'cursor':session.last_settled_message_id,'settlements':count,'facts':len(facts),'all_fact_vectors_valid':all(x.embedding is not None and len(x.embedding)==1024 and x.embedding_model==settings.agent_memory_embedding_model for x in facts)}
    def failures():
        return sum(x['value'] for x in c.metric_snapshot() if x['name']=='memory.settle_extract_failed')
    try:
        async with c.factory() as db:
            assert await __import__('cygnusx.application.services.memory_runtime_policy',fromlist=['is_memory_runtime_enabled']).is_memory_runtime_enabled(db)
            config=await SqlAlchemyAIProviderConfigRepository(db).get_default()
            agent=await db.scalar(select(AgentTemplateModel.agent_id).where(AgentTemplateModel.agent_id=='agent-general'))
            if agent is None: agent=await db.scalar(select(AgentTemplateModel.agent_id).limit(1))
            assert config and agent
            # Production model settings are used unchanged for this final verification.
            report['test_flag_diff']={}
            report['configured_extraction_model']=production_model
            report['actual_provider_model']=config.model
            report['model_override_limitation']='Current _build_kwargs uses the Provider model; chat(model=...) override is not applied. Existing chat behavior preserved.'
            db.add(ChatSessionModel(session_id=sid,user_id=user,agent_id=agent,model_id=config.id,title='MEMORY_GO_LIVE_V3_SYNTHETIC',mode='chat',status='active',sandbox_meta={'memory_go_live_synthetic':True},message_count=4))
            await db.commit()
        first=await append([('user','我长期偏好所有分析结论先用中文 Markdown 表格展示，再给简短说明。'),('assistant','我会按这个格式呈现分析结论。'),('user','这也是我后续每次分析都希望保持的输出习惯。'),('assistant','已明确你的持久输出偏好。')],0)
        c.budget.STEP='settle_first_real_success'
        result=await _settle_session_memory_v2(sid)
        after=await state()
        assert result['status']=='settled' and result['facts']>=1 and after['facts']>=1 and after['cursor']==first[-1] and after['settlements']==1 and after['all_fact_vectors_valid']
        report['first_success']={'result':result,'cursor_advanced':True,'settlement_persisted':True,'facts_persisted':after['facts'],'fact_vectors_valid':True}
        second=await append([('user','另外，我长期偏好统计图使用色盲友好配色，并避免红绿色直接对照。'),('assistant','我会使用适合色盲阅读的配色。'),('user','请将这个作为今后报告的持续偏好。'),('assistant','好的，后续报告会遵循该配色要求。')],10)
        before=await state();before_metric=failures()
        injected={'count':0}
        async def corrupt_once(self,*args,**kwargs):
            response=await original_chat(self,*args,**kwargs)
            response=copy.deepcopy(response)
            response['choices'][0]['message']['content']='CONTROLLED_NON_JSON_EXTRACTION_FAULT'
            injected['count']+=1
            return response
        c.budget.STEP='settle_controlled_non_json_fault_after_real_response'
        LiteLLMProvider.chat=corrupt_once
        try: failed=await _settle_session_memory_v2(sid)
        finally: LiteLLMProvider.chat=original_chat
        unchanged=await state();after_metric=failures()
        assert injected['count']==1 and failed['status']=='error' and unchanged==before and after_metric-before_metric==1
        report['injected_failure']={'real_extraction_response_received_before_corruption':True,'injection_count':1,'result_status':failed['status'],'cursor_unchanged':True,'no_new_settlement':True,'no_new_facts':True,'memory.settle_extract_failed_delta':after_metric-before_metric}
        c.budget.STEP='settle_retry_same_interval_real_success'
        recovered=await _settle_session_memory_v2(sid)
        final=await state()
        assert recovered['status']=='settled' and recovered['facts']>=1 and final['cursor']==second[-1] and final['settlements']==2 and final['facts']>before['facts'] and final['all_fact_vectors_valid']
        report['recovery']={'result':recovered,'same_interval_reprocessed':True,'cursor_advanced':True,'settlements':2,'all_fact_vectors_valid':True}
        report['metrics']=c.metric_snapshot()
        report['status']='passed'
    except Exception as exc:
        report.update(status='failed',error_type=type(exc).__name__)
        try: report['observed_state']={k:v for k,v in (await state()).items() if k!='cursor'}
        except Exception: pass
        report['metrics']=c.metric_snapshot()
    finally:
        LiteLLMProvider.chat=original_chat
        settings.memory_extraction_model=production_model
        async with c.factory() as db:
            # Remove supersession links only within this synthetic owner before deletion.
            from sqlalchemy import update
            await db.execute(update(MemoryFactModel).where(MemoryFactModel.user_id==user).values(superseded_by=None))
            await db.execute(delete(MemoryFactModel).where(MemoryFactModel.user_id==user))
            await db.execute(delete(MemoryBlockModel).where(MemoryBlockModel.user_id==user))
            await db.execute(delete(MemorySettlementModel).where(MemorySettlementModel.session_id==sid))
            await db.execute(delete(ChatMessageModel).where(ChatMessageModel.session_id==sid))
            await db.execute(delete(ChatSessionModel).where(ChatSessionModel.session_id==sid))
            await db.execute(delete(MemoryRecallBatchModel).where(MemoryRecallBatchModel.user_id==user))
            await db.commit()
            remaining=await db.scalar(select(func.count()).select_from(ChatSessionModel).where(ChatSessionModel.session_id==sid))
            assert remaining==0
        report['cleanup']='synthetic chat, messages, settlements, facts, blocks and recall receipts removed; session absence verified'
        c.save('settle-e2e.json',report)
        await c.engine.dispose()
    print(json.dumps(report,ensure_ascii=False))
    return 0 if report['status']=='passed' else 2

raise SystemExit(asyncio.run(main()))
