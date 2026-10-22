"""Real isolated HTTP/PostgreSQL/Redis acceptance; never enables compute gates."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import httpx

OUT = Path(__file__).resolve().parent
HANDLE = json.loads((OUT / 'runtime-handle.json').read_text())
PRIVATE = Path(HANDLE['private_root'])
ENV = json.loads((PRIVATE / 'environment.json').read_text())
assert ENV['DATASET_DISCOVERY_READONLY'] == 'true'
os.environ.update(ENV)
CTX = json.loads((PRIVATE / 'context.json').read_text())
records = []


def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + '\n')


def call(api, method, path, expected, **kwargs):
    response = api.request(method, path, **kwargs)
    data = response.json()
    records.append({'method': method, 'path': path, 'expected': expected, 'status': response.status_code, 'response': data})
    save('part-b-http.json', records)
    assert response.status_code == expected, (path, response.status_code, data)
    return data


async def seed(project_id):
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from cygnusx.infrastructure.database.models.file import FileRecordModel, SampleModel
    from cygnusx.infrastructure.database.models.chat import ChatSessionModel
    from cygnusx.infrastructure.database.models.project import ProjectModel
    from cygnusx.infrastructure.storage import get_path_factory
    engine = create_async_engine(ENV['DATABASE_URL'])
    owner = UUID(CTX['ids']['lineage_owner'])
    denied = UUID(CTX['ids']['lineage_denied'])
    async with AsyncSession(engine) as db:
        project = await db.get(ProjectModel, UUID(project_id))
        content = b'@controlled-read\nACGT\n+\nIIII\n'
        factory = get_path_factory()
        path = factory.user_root(str(owner)) / 'raw_data' / 'sample1_R1.fastq'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        file = FileRecordModel(user_id=owner, original_name=path.name,
            storage_path=path.relative_to(factory.data_root).as_posix(), size=len(content),
            checksum=hashlib.sha256(content).hexdigest(), file_type='fastq', directory='', source='upload')
        db.add(file)
        await db.flush()
        pair = path.with_name('sample1_R2.fastq')
        pair.write_bytes(content)
        r2 = FileRecordModel(user_id=owner, original_name=pair.name,
            storage_path=pair.relative_to(factory.data_root).as_posix(), size=len(content),
            checksum=hashlib.sha256(content).hexdigest(), file_type='fastq', directory='', source='upload')
        db.add(r2)
        await db.flush()
        sample = SampleModel(user_id=owner, name='explicit-pilot', file_ids=[str(file.id), str(r2.id)])
        db.add(sample)
        unbound = ChatSessionModel(session_id=str(uuid4()), user_id=str(owner), project_id=None,
                                  model_id=UUID(CTX['ids']['provider_id']))
        # Persisted unbound session is a controlled legacy fixture, never inferred.
        denied_project = ProjectModel(user_id=denied, name='denied-pilot', slug='denied-pilot', status='active')
        db.add(denied_project)
        await db.flush()
        denied_session = ChatSessionModel(session_id=str(uuid4()), user_id=str(denied), project_id=str(denied_project.id),
                                         model_id=UUID(CTX['ids']['provider_id']))
        db.add(unbound); db.add(denied_session)
        await db.flush()
        result = {'file_id': str(file.id), 'file_ids': sample.file_ids, 'sample_id': str(sample.id), 'unbound_session': unbound.session_id,
                  'denied_session': denied_session.session_id, 'project_slug': project.slug}
        await db.commit()
    await engine.dispose()
    save('input-fixture.json', {**result, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest(),
         'fixture': 'owned preregistered FileRecord + Sample; no historical Task attribution'})
    return result


async def query():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    engine = create_async_engine(ENV['DATABASE_URL'])
    queries = {
        'lineage': '''SELECT d.id AS dataset_id,d.user_id,d.project_id,d.assay_type,
          v.id AS version_id,v.number,v.source_snapshot,v.handoff,
          l.id AS link_id,l.state,l.task_id,l.confirmation_id,l.parameters_hash,l.handoff_hash,
          l.normalized_request,l.execution_binding,
          r.id AS run_id,r.request_key,r.status AS run_status,r.task_id AS run_task_id,r.plan_digest,r.plan_json
          FROM datasets d JOIN dataset_versions v ON v.dataset_id=d.id
          LEFT JOIN dataset_analysis_links l ON l.version_id=v.id
          LEFT JOIN platform_runs r ON r.request_key='dataset:'||l.id::text
          ORDER BY d.created_at''',
        'invocations': 'SELECT id,owner_id,project_id,conversation_id,capability_id,request_id,status,confirmation_id,preview FROM agent_tool_invocations',
        'samples': 'SELECT version_id,sample_id,sample_key,file_record_ids,user_annotation,mapping_status FROM dataset_samples',
        'run_events': 'SELECT run_id,task_id,status,sequence,payload FROM platform_run_events ORDER BY sequence',
        'users': 'SELECT id,username,status,disabled_modules FROM users ORDER BY username',
    }
    result = {}
    async with engine.connect() as db:
        for name, sql in queries.items():
            result[name] = {'sql': sql, 'rows': [dict(row) for row in (await db.execute(text(sql))).mappings()]}
        result['counts'] = {name: await db.scalar(text('SELECT count(*) FROM ' + name)) for name in
            ['datasets','dataset_versions','dataset_analysis_links','platform_runs','tasks','reports','research_plans','project_export_jobs']}
    await engine.dispose()
    return result


with httpx.Client(base_url=CTX['base_url'], timeout=45) as api:
    def login(name):
        response = api.post('/auth/login', data={'username': name, 'password': CTX['owner_password']})
        response.raise_for_status()
        return 'Bearer ' + response.json()['access_token']
    owner_auth, denied_auth, other_auth = [login(name) for name in ['lineage_owner','lineage_denied','lineage_other']]
    api.headers['Authorization'] = owner_auth
    setup_path = PRIVATE / 'pilot-setup.json'
    if setup_path.exists():
        setup = json.loads(setup_path.read_text()); project, fixture = setup['project'], setup['fixture']
    else:
        project = call(api, 'POST', '/projects', 201, json={'name': 'explicit-session-lineage-pilot'})
        fixture = asyncio.run(seed(project['id']))
        setup = {'project': project, 'fixture': fixture}
        setup_path.write_text(json.dumps(setup))
    if 'session' in setup:
        session = setup['session']
    else:
        session = call(api, 'POST', '/chat/sessions', 200, json={'project_id': project['id'], 'model_id': CTX['ids']['provider_id'], 'title': 'Explicit FASTQ pilot'})
        setup['session'] = session
        setup_path.write_text(json.dumps(setup))
    sid = session['session_id']
    endpoint = '/agent-tools/sessions/' + sid + '/invoke'
    args = {'request_key': str(uuid4()), 'name': 'Explicit FASTQ PLAN_ONLY', 'samples': [
        {'sample_id': fixture['sample_id'], 'sample_key': 'sample1', 'file_record_ids': fixture.get('file_ids', [fixture['file_id']]), 'group': 'control'}],
        'parameters': {'genome_version': 'hg38', 'species': 'Homo sapiens', 'library_types': 'fr-unstranded'}}
    if 'args' in setup:
        args = setup['args']
    else:
        setup['args'] = args
        setup_path.write_text(json.dumps(setup))
    payload = {'capability_id': 'analysis.prepare_from_session_files', 'arguments': args}
    call(api, 'POST', '/agent-tools/sessions/'+fixture['unbound_session']+'/invoke', 422, json=payload)
    call(api, 'POST', '/agent-tools/sessions/'+fixture['denied_session']+'/invoke', 403, json=payload, headers={'Authorization': denied_auth})
    call(api, 'POST', endpoint, 404, json=payload, headers={'Authorization': other_auth})
    for forged in [{'project_id': str(uuid4())}, {'owner_id': CTX['ids']['lineage_other']}, {'approved': True}]:
        call(api, 'POST', endpoint, 422, json={**payload, 'arguments': {**args, **forged}})
    before = asyncio.run(query())
    baseline_datasets = setup.get('baseline_datasets', 0)
    assert before['counts']['datasets'] <= baseline_datasets + 1, before['counts']
    save('paired-negative-before-registration-db.json', before)
    first = call(api, 'POST', endpoint, 200, json=payload)['result']
    assert first['state'] in {'REVIEW_REQUIRED', 'PREPARED'}
    ds, version = first['dataset_id'], first['dataset_version_id']
    version_path = f"/projects/{project['id']}/datasets/{ds}/versions/{version}"
    if first['state'] == 'REVIEW_REQUIRED':
        assert first['handoff_frozen'] is False
        save('review-required-db.json', asyncio.run(query()))
        call(api, 'POST', version_path+'/review', 200, json={'assay_type': 'bulk_rnaseq', 'reason': 'Human JWT explicit FASTQ assay review for isolated PLAN_ONLY pilot'})
        call(api, 'POST', version_path+'/samples/sample1/review', 200, json={'group': 'control'})
    prepared = call(api, 'POST', endpoint, 200, json=payload)['result']
    assert prepared['handoff_frozen'] and prepared['mode'] == 'PLAN_ONLY'
    repeated = call(api, 'POST', endpoint, 200, json=payload)['result']
    for key in ['dataset_id','dataset_version_id','analysis_proposal_id','run_id','handoff_hash']:
        assert repeated[key] == prepared[key], key
    call(api, 'POST', endpoint, 409, json={**payload, 'arguments': {**args, 'name': 'changed'}})
    proposal = version_path+'/analysis-proposals/'+prepared['analysis_proposal_id']
    approved = call(api, 'POST', proposal+'/approve', 200)
    call(api, 'POST', proposal+'/execute', 403)
    link_view = call(api, 'GET', proposal, 200)
    confirmation_id = link_view.get('confirmation_id') or prepared.get('confirmation_id')
    if not confirmation_id:
        evidence = asyncio.run(query())
        confirmation_id = evidence['lineage']['rows'][0]['confirmation_id']
    call(api, 'POST', '/runs/'+prepared['run_id']+'/confirm', 403, json={'confirmation_id': confirmation_id, 'user_confirmed': True})
    inventory = call(api, 'GET', f"/projects/{project['id']}/delivery-inventory", 200)
    assert inventory['datasets'] and not inventory['export_enabled']
    final = asyncio.run(query())
    assert final['counts'] == {'datasets':baseline_datasets+1,'dataset_versions':baseline_datasets+1,'dataset_analysis_links':1,'platform_runs':1,'tasks':0,'reports':0,'research_plans':0,'project_export_jobs':0}, final['counts']
    row = next(r for r in final['lineage']['rows'] if r['link_id'] is not None)
    assert row['handoff']['validation']['worker_paths_verified'] is False
    assert row['handoff_hash'] == prepared['handoff_hash'] == row['handoff']['manifest_hash']
    assert row['task_id'] is None and row['run_task_id'] is None
    assert row['request_key'] == 'dataset:'+str(row['link_id'])
    assert row['normalized_request']['request']['idempotency_key'] == row['request_key']
    assert str(row['user_id']) == CTX['ids']['lineage_owner'] and str(row['project_id']) == project['id']
    save('part-b-db-evidence.json', final)
    save('part-b-inventory.json', inventory)
    save('part-b-summary.json', {'session_id':sid,'project_id':project['id'], 'result':prepared,'approval':approved,'counts':final['counts'], 'compute_executed':False, 'acceptance_by':'user'})
    print('HTTP requests:', len(records), '; DB counts:', final['counts'])
