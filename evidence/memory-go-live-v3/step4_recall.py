import asyncio,json,statistics,time,re
from uuid import uuid4
import acceptance_common as c
from sqlalchemy import select,text
from cygnusx.application.services.agent_memory_service import AgentMemoryService
from cygnusx.infrastructure.database.models.agent_memory import MemoryFactModel


def quantiles(values):
    ordered=sorted(values)
    def q(p): return ordered[min(len(ordered)-1,max(0,round((len(ordered)-1)*p)))]
    return {'min':ordered[0],'p05':q(.05),'p10':q(.1),'p50':q(.5),'p90':q(.9),'p95':q(.95),'max':ordered[-1]}

async def main():
    c.budget.STEP='real_recall_calibration'
    original=c.get_settings().memory_embedding_model_filter_enabled
    report={'status':'running','protocol':'D-group DB recall timing with precomputed real query embeddings; 50 SQL recall samples, 25 per model-filter mode','production_defaults_modified':False}
    try:
        async with c.factory() as db:
            facts=(await db.scalars(select(MemoryFactModel).where(MemoryFactModel.status=='active',MemoryFactModel.embedding.is_not(None)).order_by(MemoryFactModel.id))).all()
        assert facts
        templates=['请回顾我提到的{}。','我在{}方面有什么偏好？','之前关于{}我做过什么决定？','请记起我的{}要求。','继续讨论我以前说的{}。','我的{}习惯是什么？','你记得我对{}的要求吗？','请按我的{}偏好回答。','我之前如何描述{}？','总结我的{}背景。']
        queries=[]
        async with c.factory() as db:
            service=AgentMemoryService(db)
            for i,template in enumerate(templates):
                fact=facts[i%len(facts)]
                topic='、'.join((fact.keywords or [])[:3]) or fact.content[:16]
                vector=await service._embed(template.format(topic))
                assert len(vector)==1024
                queries.append((fact,vector))
        durations=[]; similarities=[]; target_similarities=[]; modes={}; hits=misses=0
        async with c.factory() as db:
            service=AgentMemoryService(db)
            for filtered in (False,True):
                c.get_settings().memory_embedding_model_filter_enabled=filtered
                timing=[]; modehits=0
                for i in range(25):
                    target,vector=queries[i%len(queries)]
                    start=time.perf_counter()
                    found=await service._search_facts_merged(target.user_id,target.agent_id,vector,limit=10,query='',project_id=target.project_id)
                    elapsed=(time.perf_counter()-start)*1000
                    durations.append(elapsed);timing.append(elapsed)
                    target_hits=[x for x in found if x.id==target.id]
                    hits+=bool(found);misses+=not bool(found);modehits+=bool(target_hits)
                    similarities.extend(x.similarity for x in found if x.similarity is not None)
                    target_similarities.extend(x.similarity for x in target_hits if x.similarity is not None)
                modes[str(filtered)]={'samples':25,'p50_ms':statistics.median(timing),'p95_ms':quantiles(timing)['p95'],'target_hits':modehits}
            target,vector=queries[0]
            other=await service._search_facts_merged(str(uuid4()),target.agent_id,vector,limit=10,query='',project_id=target.project_id)
            assert not other
            c.get_settings().memory_embedding_model_filter_enabled=original
            plan=await db.scalar(text('''EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT id FROM memory_facts
                WHERE user_id=:u AND agent_id=:a AND status='active' AND (project_id IS NULL OR project_id=:p)
                  AND embedding IS NOT NULL AND embedding_model=:m
                ORDER BY embedding <=> CAST(:v AS vector) LIMIT 10'''),
                {'u':target.user_id,'a':target.agent_id,'p':target.project_id,'m':c.get_settings().agent_memory_embedding_model,'v':json.dumps(vector)})
            rendered=re.sub(r"'[^']*'","'[redacted]'",json.dumps(plan))
            c.save('recall-real-plan.json',json.loads(rendered))
        report.update(status='passed',samples=50,unique_query_embeddings=len(queries),unique_active_facts=len(facts),p50_ms=statistics.median(durations),p95_ms=quantiles(durations)['p95'],hit_count=hits,miss_count=misses,negative_cross_user_probe={'queries':1,'misses':1},by_filter_mode=modes,raw_ms=durations,
            limitation='Small real active corpus; repeated queries are correlated. Does not establish production-sized HNSW behavior or independent semantic precision.')
        c.save('recall-real.json',report)
        scores=quantiles(target_similarities)
        recommendation=round(max(-1,min(.8,scores['p05']-.05)),2)
        distribution={'status':'measured','returned_hit_similarity':quantiles(similarities),'target_hit_similarity':scores,'measurements':len(similarities),'independent_query_fact_pairs':len(queries),'unique_active_facts':len(facts),
            'production_default':c.get_settings().memory_hybrid_min_similarity,'candidate_for_next_labeled_evaluation':recommendation,
            'basis':'Target-hit P05 minus 0.05 margin, capped at 0.8; proposal only, no settings changes',
            'limitation':'Insufficient independent labeled negatives; this is a calibration candidate, not a validated production threshold.'}
        c.save('similarity-distribution.json',distribution)
        (c.OUT/'threshold-recommendation.md').write_text('# min_similarity 标定建议（不修改生产默认）\n\n| 项目 | 实测/建议 |\n| --- | --- |\n'+''.join(f'| 命中相似度 {k} | {v:.4f} |\n' for k,v in scores.items())+f'| 后续标注评估候选阈值 | {recommendation:.2f} |\n| 生产当前值 | {distribution["production_default"]}（保持） |\n\n50 次 SQL 召回来自 10 个查询与 '+str(len(facts))+' 条活跃事实，重复样本有相关性。建议值按目标命中 P05 减 0.05 得到，须补独立负例与人工标注后再决定是否启用；当前不足以推荐直接修改生产阈值。\n')
        print(json.dumps({k:v for k,v in report.items() if k!='raw_ms'}))
    except Exception as exc:
        report.update(status='failed',error_type=type(exc).__name__);c.save('recall-real.json',report)
        print(json.dumps(report));return 2
    finally:
        c.get_settings().memory_embedding_model_filter_enabled=original
        await c.engine.dispose()
    return 0

raise SystemExit(asyncio.run(main()))
