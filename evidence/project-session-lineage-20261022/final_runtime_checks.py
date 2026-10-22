"""Final-source checks against the same isolated records; no compute gate changes."""
import asyncio
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import httpx

OUT = Path(__file__).resolve().parent
PRIVATE = Path(json.loads((OUT / 'runtime-handle.json').read_text())['private_root'])
ENV = json.loads((PRIVATE / 'environment.json').read_text())
os.environ.update(ENV)
CTX = json.loads((PRIVATE / 'context.json').read_text())
SETUP = json.loads((PRIVATE / 'pilot-setup.json').read_text())
SUMMARY = json.loads((OUT / 'part-b-summary.json').read_text())
RESULT = SUMMARY['result']
records = []


def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + '\n')


async def update(kind, value):
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from cygnusx.infrastructure.database.models.project import ProjectModel
    from cygnusx.infrastructure.database.models.user import UserModel
    engine = create_async_engine(ENV['DATABASE_URL'])
    async with AsyncSession(engine) as db:
        if kind == 'project_status':
            obj = await db.get(ProjectModel, UUID(SUMMARY['project_id']))
            obj.status = value
        else:
            obj = await db.get(UserModel, UUID(CTX['ids']['lineage_owner']))
            setattr(obj, kind, value)
        await db.commit()
    await engine.dispose()


async def check_worker_and_db():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from cygnusx.application.services.agent_tool_gateway import WRITE_RUNTIME_ACCEPTED, digest
    from cygnusx.application.services.research_execution_binding import check_inputs
    from cygnusx.application.services.tool_confirmation_service import get_tool_confirmation_service
    from cygnusx.core.exceptions import ValidationError
    from cygnusx.infrastructure.database.models.dataset import DatasetAnalysisLinkModel
    engine = create_async_engine(ENV['DATABASE_URL'])
    async with AsyncSession(engine) as db:
        link = await db.get(DatasetAnalysisLinkModel, UUID(RESULT['analysis_proposal_id']))
        try:
            await check_inputs(db, UUID(CTX['ids']['lineage_owner']), link)
        except ValidationError as exc:
            assert exc.code == 'WORKER_PATHS_NOT_VERIFIED'
            records.append({'check': 'real DB-backed worker input guard', 'code': exc.code})
        else:
            raise AssertionError('Worker input guard did not block')
        assert WRITE_RUNTIME_ACCEPTED is False
        frozen = await check_inputs(db, UUID(CTX['ids']['lineage_owner']), link, require_worker=False)
        assert frozen['validation']['worker_paths_verified'] is False
        assert digest({**frozen, 'manifest_hash': None}) == RESULT['handoff_hash']
        approval = await get_tool_confirmation_service().get_status(CTX['ids']['lineage_owner'], link.confirmation_id)
        assert approval.status == 'APPROVED'
        save('three-gate-evidence.json', {'source_WRITE_RUNTIME_ACCEPTED': WRITE_RUNTIME_ACCEPTED,
            'config': {key: ENV[key] for key in ['AGENT_ANALYSIS_WRITE_ENABLED','ANALYSIS_SUBMIT_FROM_DATASET']},
            'worker_paths_verified': frozen['validation']['worker_paths_verified'],
            'worker_guard_error': 'WORKER_PATHS_NOT_VERIFIED', 'frozen_digest_unchanged': True,
            'confirmation': {'confirmation_id': approval.confirmation_id, 'status': approval.status, 'used': False}})
        rows = (await db.execute(text('''SELECT d.id AS dataset_id,d.user_id,d.project_id,v.id AS version_id,
            v.review_annotations,v.source_snapshot,v.handoff,l.id AS analysis_link_id,l.state,l.task_id,
            l.confirmation_id,l.normalized_request,r.id AS run_id,r.request_key,r.task_id AS run_task_id
            FROM datasets d JOIN dataset_versions v ON v.dataset_id=d.id
            JOIN dataset_analysis_links l ON l.version_id=v.id
            JOIN platform_runs r ON r.request_key='dataset:'||l.id::text'''))).mappings().all()
        counts = {name: await db.scalar(text('SELECT count(*) FROM '+name)) for name in
            ['datasets','dataset_versions','dataset_analysis_links','platform_runs','tasks','reports','research_plans','project_export_jobs']}
        assert counts == SUMMARY['counts']
        save('final-db-evidence.json', {'rows': [dict(r) for r in rows], 'counts': counts})
    await engine.dispose()


with httpx.Client(base_url='http://127.0.0.1:18014/api/v1', timeout=30) as api:
    response = api.post('/auth/login', data={'username': CTX['owner_username'], 'password': CTX['owner_password']})
    response.raise_for_status()
    api.headers['Authorization'] = 'Bearer '+response.json()['access_token']
    def call(method, path, expected, **kwargs):
        response = api.request(method, path, **kwargs)
        record = {'method':method,'path':path,'expected':expected,'status':response.status_code,'response':response.json()}
        records.append(record); save('final-http-checks.json', records)
        assert response.status_code == expected, record
        return response.json()
    sid = SETUP['session']['session_id']
    endpoint = f'/agent-tools/sessions/{sid}/invoke'
    payload = {'capability_id':'analysis.prepare_from_session_files','arguments':SETUP['args']}
    first = call('POST', endpoint, 200, json=payload)['result']
    assert first['run_id'] == RESULT['run_id']
    # Real concurrent retries serialize on the actual owned ChatSession row.
    async def concurrent():
        async with httpx.AsyncClient(base_url='http://127.0.0.1:18014/api/v1', headers=dict(api.headers), timeout=45) as client:
            replies = await asyncio.gather(client.post(endpoint,json=payload),client.post(endpoint,json=payload))
            assert [r.status_code for r in replies] == [200,200]
            assert all(r.json()['result']['analysis_proposal_id'] == RESULT['analysis_proposal_id'] for r in replies)
            save('concurrent-retry-http.json', [{'status':r.status_code,'response':r.json()} for r in replies])
    asyncio.run(concurrent())
    call('POST', endpoint, 422, json={**payload,'project_id':str(uuid4())})
    bad_samples=[{**SETUP['args']['samples'][0],'group_confirmed':True}]
    call('POST', endpoint, 422, json={**payload,'arguments':{**SETUP['args'],'samples':bad_samples}})
    for module in ['files','tasks','reports']:
        try:
            asyncio.run(update('disabled_modules',[module]))
            call('POST', endpoint, 403, json=payload)
            capabilities=call('GET',f"/projects/{SUMMARY['project_id']}/capability-status",200)
            assert not capabilities['research_plan']['allowed']
            assert not capabilities['research_delivery_read']['allowed']
            for surface in ['research-plans','research-delivery','delivery-inventory']:
                call('GET',f"/projects/{SUMMARY['project_id']}/{surface}",403)
        finally:
            asyncio.run(update('disabled_modules',[]))
    try:
        asyncio.run(update('status','inactive'))
        call('GET',f"/projects/{SUMMARY['project_id']}/capability-status",401)
    finally:
        asyncio.run(update('status','active'))
    try:
        asyncio.run(update('project_status','archived'))
        call('POST', endpoint, 403, json=payload)
    finally:
        asyncio.run(update('project_status','active'))
    call('POST','/tasks',409,json={'flow_id':'rna_seq','name':'forged run alias','parameters':{},'sample_sheet':[],
        'idempotency_key':'run:'+RESULT['run_id']})
    proposal=f"/projects/{SUMMARY['project_id']}/datasets/{RESULT['dataset_id']}/versions/{RESULT['dataset_version_id']}/analysis-proposals/{RESULT['analysis_proposal_id']}"
    view = call('GET', proposal, 200)
    assert view['state'] == 'APPROVED' and view['task_id'] is None
    call('POST', proposal+'/execute',403)
    original = json.loads((OUT/'part-b-db-evidence.json').read_text())
    link=next(r for r in original['lineage']['rows'] if r['link_id'] is not None)
    call('POST', '/runs/'+RESULT['run_id']+'/confirm',403,json={'confirmation_id':link['confirmation_id'],'user_confirmed':True})
    call('GET',f"/projects/{SUMMARY['project_id']}/delivery-inventory",200)
asyncio.run(check_worker_and_db())
save('final-http-checks.json',records)
print('Final-source HTTP checks:',len(records),'; worker guard blocked; shared approval remains APPROVED; no Task.')
