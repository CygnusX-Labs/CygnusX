import asyncio,json
import acceptance_common as c
from cygnusx.application.services.memory_embedding_service import MemoryEmbeddingService

async def main():
    async with c.factory() as db:
        coverage=await MemoryEmbeddingService(db).coverage()
    assert coverage['coverage']==1.0 and coverage['active']>0
    settle=json.loads((c.OUT/'settle-e2e.json').read_text())
    recall=json.loads((c.OUT/'recall-real.json').read_text())
    r={'status':'measured','coverage':coverage,'acceptance_process_otel_gauge':c.metric_snapshot(),
       'settle_metrics_from_real_extraction_and_fault_injection':settle['metrics'],
       'recall_protocol_counts':{'hit':recall['hit_count'],'miss':recall['miss_count']+recall['negative_cross_user_probe']['misses'],'samples':recall['samples']+1},
       'production_flags':{'memory_embedding_coverage_enabled':c.get_settings().memory_embedding_coverage_enabled},
       'scope':'Coverage and settle values collected from actual OTel SDK instruments in real acceptance processes; recall hit/miss are verifier counts, not a newly claimed production metric',
       'production_exporter_verification':'pending: not inferred from local OTel SDK measurements'}
    c.save('metrics.json',r)
    await c.engine.dispose()
    print(json.dumps({'coverage':coverage['coverage'],'active':coverage['active'],'settle_metric_names':[x['name'] for x in settle['metrics']],'recall':r['recall_protocol_counts']}))
asyncio.run(main())
