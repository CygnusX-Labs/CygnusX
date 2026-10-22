"""Bounded real Qwen pilot on three published documents in a disposable PG schema."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from dotenv import load_dotenv
from sqlalchemy import event, func, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
load_dotenv(ROOT / '.env', override=True)
assert os.environ.get('MEMORY_MAINTENANCE_DATABASE_URL'), 'Explicit source DSN required'
source_url = make_url(os.environ['MEMORY_MAINTENANCE_DATABASE_URL'])
assert source_url.database == 'omichub' and source_url.host in ('db', '127.0.0.1')
if source_url.host == 'db':
    source_info = json.loads(subprocess.check_output(['docker', 'inspect', 'cygnusx-db']))[0]
    binding = next(x for x in source_info['NetworkSettings']['Ports']['5432/tcp'] if x['HostIp'] == '127.0.0.1')
    source_url = source_url.set(host='127.0.0.1', port=int(binding['HostPort']))

container = 'cygnusx-memory-stage0-postgres-1'
info = json.loads(subprocess.check_output(['docker', 'inspect', container]))[0]
assert info['State']['Running'] and info['Config']['Image'].startswith('pgvector/pgvector:')
env = dict(x.split('=', 1) for x in info['Config']['Env'] if '=' in x)
binding = next(x for x in info['NetworkSettings']['Ports']['5432/tcp'] if x['HostIp'] == '127.0.0.1')
target_url = URL.create('postgresql+asyncpg', username=env['POSTGRES_USER'], password=env['POSTGRES_PASSWORD'], host='127.0.0.1', port=int(binding['HostPort']), database='cygnusx_maint')
assert target_url.database == 'cygnusx_maint' and target_url.port == 55432
assert (source_url.host, source_url.port, source_url.database) != (target_url.host, target_url.port, target_url.database)
os.environ['DATABASE_URL'] = target_url.render_as_string(hide_password=False)
os.environ['TELEMETRY_ENABLED'] = 'false'
os.environ['OTEL_SDK_DISABLED'] = 'true'
os.environ['SERVICE_NAME'] = 'knowledge_qwen_pilot'
from loguru import logger
logger.remove()
logging.disable(logging.CRITICAL)
from cygnusx.core.config import get_settings
get_settings.cache_clear()
from cygnusx.application.services.knowledge_index_service import KnowledgeIndexService
from cygnusx.application.services.vector_retrieval_service import VectorRetrievalService
from cygnusx.infrastructure.ai_provider.litellm_provider import LiteLLMProvider
from cygnusx.infrastructure.database.base import Base
from cygnusx.infrastructure.database.models.knowledge_base import KnowledgeBaseModel
from cygnusx.infrastructure.database.models.knowledge_document import KbDocumentModel
from cygnusx.infrastructure.database.models.knowledge_revision import DocRevisionModel
from cygnusx.infrastructure.database.models.knowledge_chunk import KbChunkModel
from cygnusx.infrastructure.database.repositories.ai_provider_repository import SqlAlchemyAIProviderConfigRepository

MODEL = 'Qwen/Qwen3-Embedding-8B'
settings = get_settings()
assert settings.agent_memory_embedding_model == MODEL and settings.agent_memory_embedding_dimensions == 1024
PROVIDER = UUID(settings.agent_memory_embedding_provider_id)
SAMPLES = [
    ('qc-20f99f087681', 'FAST5', '纳米孔测序的 FAST5 文件用什么结构保存原始电流信号？'),
    ('qc-34bc4b0f06ac', 'TOML', '用键值对和分节表达配置的 TOML 文件格式是什么？'),
    ('qc-f876cff3d623', 'bwtool', '怎样用 bwtool 对 bigWig 信号做区间处理和数据提取？'),
]
assert len({x[0] for x in SAMPLES}) == 3
SCHEMA = 'kb_qwen_pilot_' + uuid4().hex[:12]
assert re.fullmatch(r'kb_qwen_pilot_[0-9a-f]{12}', SCHEMA)
source_engine = create_async_engine(source_url.set(drivername='postgresql+asyncpg'), echo=False, poolclass=NullPool,
    connect_args={'server_settings': {'default_transaction_read_only': 'on', 'statement_timeout': '20000'}})
target_engine = create_async_engine(target_url, echo=False, poolclass=NullPool,
    connect_args={'server_settings': {'search_path': SCHEMA + ',public', 'statement_timeout': '30000'}})
source_factory = async_sessionmaker(source_engine, expire_on_commit=False)
target_factory = async_sessionmaker(target_engine, expire_on_commit=False)


def save(name, data):
    (OUT/name).write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + '\n')


def install_accounting():
    import fcntl
    import httpx
    prior = json.loads((ROOT/'evidence/memory-go-live-v3/call-ledger.json').read_text())
    assert not any(row['status'] == 'in_flight_counted' for row in prior['calls'])
    ledger = OUT/'call-ledger.json'
    assert not ledger.exists(), 'Existing pilot calls must not be reset'
    save('call-ledger.json', {'status':'running', 'baseline':prior['total'], 'baseline_file':'evidence/memory-go-live-v3/call-ledger.json',
        'limits':{'embedding':150,'extraction':20}, 'pilot_limit_embedding':12, 'pilot_calls':0,
        'total':dict(prior['total']), 'calls':[], 'billing_amount':None})
    def update(callback):
        with (OUT/'call-ledger.lock').open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            data=json.loads(ledger.read_text()); value=callback(data)
            temp=ledger.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');temp.replace(ledger)
            return value
    original = httpx.AsyncClient.send
    async def send(client, request, *args, **kwargs):
        path=request.url.path.rstrip('/')
        if path.endswith('/chat/completions'):
            raise RuntimeError('Extraction/chat calls forbidden in this pilot')
        if not path.endswith('/embeddings'):
            return await original(client, request, *args, **kwargs)
        payload=json.loads(request.content)
        assert payload.get('dimensions') == 1024 and MODEL in payload.get('model','')
        def reserve(data):
            assert data['pilot_calls'] < data['pilot_limit_embedding'] and data['total']['embedding'] < data['limits']['embedding']
            data['pilot_calls']+=1;data['total']['embedding']+=1
            identity=len(data['calls'])+1
            data['calls'].append({'id':identity,'status':'in_flight_counted','model':payload['model'],
                'dimensions_parameter':1024,'started_at_utc':datetime.now(timezone.utc).isoformat()})
            return identity
        identity=update(reserve); started=time.perf_counter()
        try:
            response=await original(client,request,*args,**kwargs)
            await response.aread(); data=response.json()
            fields={'status':'received','http_status':response.status_code,'duration_ms':round((time.perf_counter()-started)*1000,2),
                'usage':{k:v for k,v in (data.get('usage') or {}).items() if isinstance(v,(int,float))}}
            embedding_rows=data.get('data') or []
            fields['returned_dimensions']=[len(r.get('embedding') or []) for r in embedding_rows]
            update(lambda d: d['calls'][identity-1].update(fields))
            return response
        except Exception as exc:
            update(lambda d:d['calls'][identity-1].update(status='error',error_type=type(exc).__name__))
            raise
    httpx.AsyncClient.send=send


async def source_snapshot():
    async with source_factory() as db:
        assert await db.scalar(text('SHOW transaction_read_only')) == 'on'
        return dict((await db.execute(text('''SELECT
            (SELECT count(*) FROM kb_documents) AS documents,
            (SELECT count(*) FROM doc_revisions) AS revisions,
            (SELECT count(*) FROM kb_chunks) AS chunks,
            (SELECT count(embedding) FROM kb_chunks) AS vectors'''))).mappings().one())


async def read_sources():
    async with source_factory() as db:
        config=await SqlAlchemyAIProviderConfigRepository(db).get_by_id(PROVIDER)
        assert config and config.is_active and not config.is_default and config.model == MODEL
        rows=(await db.execute(text('''SELECT d.doc_id,d.file_path,r.content
            FROM kb_documents d JOIN doc_revisions r ON r.id=d.current_rev
            JOIN knowledge_bases b ON b.id=d.kb_id
            WHERE d.status=1 AND b.ai_searchable AND b.is_enabled AND d.doc_id=ANY(:ids)'''),
            {'ids':[x[0] for x in SAMPLES]})).mappings().all()
    assert len(rows) == 3
    by_id={r['doc_id']:dict(r) for r in rows}
    plan=[]
    for identity,label,query in SAMPLES:
        row=by_id[identity]; chunks=KnowledgeIndexService._split(row['content'])
        assert chunks and len(chunks)<=3
        assert not re.search(r'(?:sk-[A-Za-z0-9_-]{16,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|AKIA[A-Z0-9]{16})',row['content']), 'Source contains credential-like text; not sent'
        plan.append({'source_doc_id':identity,'label':label,'source_path':row['file_path'],
            'characters':len(row['content']),'planned_chunks':len(chunks),
            'content_sha256':hashlib.sha256(row['content'].encode()).hexdigest()})
    assert sum(p['planned_chunks'] for p in plan)==6
    return config,by_id,plan


async def main():
    mode=sys.argv[1]
    assert mode in ('dry','apply')
    config,sources,documents=await read_sources()
    plan={'status':'dry_run','model':MODEL,'dimensions':1024,'documents':documents,
        'planned_index_embeddings':6,'planned_query_embeddings':3,'max_http_attempts':12,
        'target_database':'cygnusx_maint','target_container':container,
        'scope':'three existing published document bodies copied to disposable isolated schema; no source attachments',
        'source_business_db_read_only':True,'production_rows_written':0,'cleanup':'drop only the new random pilot schema'}
    if mode=='dry':
        save('plan.json',plan)
        print(json.dumps({'status':'dry_run','documents':[{'label':d['label'],'chunks':d['planned_chunks']} for d in documents],
            'planned_embedding_calls':9,'max_http_attempts':12,'source_read_only':True,'target_database':'cygnusx_maint'}))
        return
    assert plan==json.loads((OUT/'plan.json').read_text()), 'Source changed after displayed dry-run'
    install_accounting()
    before=await source_snapshot()
    sql_counts={'vector_queries':0,'keyword_queries':0}
    @event.listens_for(target_engine.sync_engine, 'before_cursor_execute')
    def count_sql(conn,cursor,statement,parameters,context,executemany):
        if '<=>' in statement and 'kb_chunks' in statement:sql_counts['vector_queries']+=1
        if ' ILIKE ' in statement.upper() and 'kb_chunks' in statement:sql_counts['keyword_queries']+=1
    user_id=uuid4();kb_id='qwen-pilot';created=False
    report={'status':'running','model':MODEL,'dimensions':1024,'source_snapshot_before':before,
        'target_database':'cygnusx_maint','schema':SCHEMA,'documents':[], 'calls_limit':12,
        'scope':plan['scope'],'production_rows_written':0,'cleanup':'pending'}
    provider=LiteLLMProvider(config)
    class ValidatedClient:
        async def embeddings(self,content,model=''):
            assert model==MODEL
            values=await provider.embeddings(content,model=model)
            assert len(values)==1024 and all(math.isfinite(float(v)) for v in values)
            return values
    client=ValidatedClient()
    try:
        async with target_engine.begin() as conn:
            assert await conn.scalar(text('SELECT current_database()'))=='cygnusx_maint'
            version=await conn.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
            assert version
            report['target_pgvector_version']=version
            await conn.execute(text('CREATE SCHEMA '+SCHEMA));created=True
            await conn.execute(text('CREATE TABLE users (id uuid PRIMARY KEY)'))
            await conn.run_sync(lambda sync:Base.metadata.create_all(sync,tables=[KnowledgeBaseModel.__table__,KbDocumentModel.__table__,DocRevisionModel.__table__,KbChunkModel.__table__],checkfirst=False))
            await conn.execute(text('INSERT INTO users(id) VALUES (:id)'),{'id':user_id})
        async with target_factory() as db:
            db.add(KnowledgeBaseModel(id=kb_id,name='Qwen pilot',show_in_lab=False,ai_searchable=True,is_enabled=True))
            await db.flush()
            indexer=KnowledgeIndexService(db,embedding_client=client)
            for identity,label,query in SAMPLES:
                content=sources[identity]['content']
                document=KbDocumentModel(doc_id='pilot-'+label.lower(),title=label,category='pilot',file_path='',status=1,created_by=user_id,kb_id=kb_id)
                db.add(document);await db.flush()
                revision=DocRevisionModel(document_id=document.id,content=content,edited_by=user_id,status=1,edit_summary='bounded real embedding pilot')
                db.add(revision);await db.flush();document.current_rev=revision.id
                count=await indexer.index_document(document,content,include_unreferenced_assets=False)
                assert count==next(p['planned_chunks'] for p in documents if p['source_doc_id']==identity)
                report['documents'].append({'label':label,'chunks':count,'source_doc_id':identity})
            await db.commit()
        async with target_factory() as db:
            rows=(await db.execute(text('''SELECT embedding_model,vector_dims(embedding) AS dimensions,
                count(*) AS rows,count(DISTINCT document_id) AS documents FROM kb_chunks
                GROUP BY embedding_model,vector_dims(embedding)'''))).mappings().all()
            assert len(rows)==1 and rows[0]['embedding_model']==MODEL and rows[0]['dimensions']==1024 and rows[0]['rows']==6 and rows[0]['documents']==3
            report['committed_vector_verification']=[dict(r) for r in rows]
        outcomes=[]
        for identity,label,query in SAMPLES:
            async with target_factory() as db:
                start=time.perf_counter()
                hits=await VectorRetrievalService(db,embedding_client=client).search_knowledge(query=query,limit=3)
                assert hits and hits[0].doc_id=='pilot-'+label.lower(), 'Expected source is not top semantic hit'
                outcomes.append({'label':label,'top1_matches_expected':True,'top1_doc_id':hits[0].doc_id,
                    'top1_cosine_similarity':round(hits[0].score,6),'result_count':len(hits),
                    'query_and_sql_duration_ms':round((time.perf_counter()-start)*1000,2)})
        assert sql_counts=={'vector_queries':3,'keyword_queries':0}
        report['recall']=outcomes;report['sql_paths']=sql_counts
        calls_before_replay=json.loads((OUT/'call-ledger.json').read_text())['pilot_calls']
        async with target_factory() as db:
            for identity,label,query in SAMPLES:
                document=(await db.scalars(select(KbDocumentModel).where(KbDocumentModel.doc_id=='pilot-'+label.lower()))).one()
                changed,count=await KnowledgeIndexService(db,embedding_client=client).ensure_document_indexed(document,sources[identity]['content'],include_unreferenced_assets=False)
                assert changed is False
            await db.commit()
        calls_after_replay=json.loads((OUT/'call-ledger.json').read_text())['pilot_calls']
        assert calls_before_replay==calls_after_replay
        report['unchanged_replay']={'documents_skipped':3,'extra_embedding_calls':0}
        report['status']='passed'
    except Exception as exc:
        report.update(status='failed',error_type=type(exc).__name__)
    finally:
        if created:
            async with target_engine.begin() as conn:
                await conn.execute(text('DROP SCHEMA IF EXISTS '+SCHEMA+' CASCADE'))
            async with target_engine.connect() as conn:
                assert await conn.scalar(text('SELECT count(*) FROM pg_namespace WHERE nspname=:name'),{'name':SCHEMA})==0
            report['cleanup']='verified pilot schema absent'
        after=await source_snapshot();report['source_snapshot_after']=after
        report['source_snapshot_unchanged']=before==after
        assert before==after
        ledger=json.loads((OUT/'call-ledger.json').read_text())
        assert not any(row['status']=='in_flight_counted' for row in ledger['calls'])
        ledger['status']='completed' if report['status']=='passed' else 'failed'
        ledger['remaining_cumulative']={k:ledger['limits'][k]-ledger['total'][k] for k in ledger['limits']}
        save('call-ledger.json',ledger)
        report['real_embedding_http_attempts']=ledger['pilot_calls']
        report['cumulative_calls']=ledger['total']
        save('result.json',report)
    assert report['status']=='passed', 'Pilot failed; sanitized result.json retained'
    print(json.dumps({k:report[k] for k in ('status','documents','real_embedding_http_attempts','committed_vector_verification','recall','sql_paths','unchanged_replay','source_snapshot_unchanged','cleanup')},ensure_ascii=False))

async def entry():
    try:await main()
    finally:
        await source_engine.dispose();await target_engine.dispose()

try:asyncio.run(entry())
except Exception as exc:
    print(json.dumps({'status':'failed','error_type':type(exc).__name__}))
    raise SystemExit(2)
