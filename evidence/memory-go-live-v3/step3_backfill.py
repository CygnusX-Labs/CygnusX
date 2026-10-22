import asyncio
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import UUID

import acceptance_common as c

spec=importlib.util.spec_from_file_location('backfill_cli',Path.cwd()/'scripts/backfill_memory_embeddings.py')
cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)

async def main():
    phase=sys.argv[1]
    planfile=c.OUT/'backfill-plan.json'
    reportfile=c.OUT/'backfill.json'
    report=json.loads(reportfile.read_text()) if reportfile.exists() else {'status':'preparing','batches':[],'failed_rows':[]}
    c.budget.STEP='historical_backfill_'+phase
    dsn=os.environ['MEMORY_MAINTENANCE_DATABASE_URL']
    if phase in ('dry','dry-tail'):
        root=Path(tempfile.mkdtemp(prefix='cygnusx-memory-facts-backup-'));os.chmod(root,0o700)
        backup=root/'memory_facts.dump'
        with backup.open('wb') as stream:
            os.chmod(backup,0o600)
            p=subprocess.run(['docker','exec','cygnusx-db','sh','-c','exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t public.memory_facts -Fc --no-owner --no-acl'],stdout=stream,stderr=subprocess.PIPE,timeout=60)
        assert p.returncode==0 and backup.stat().st_size>0
        with backup.open('rb') as stream:
            p=subprocess.run(['docker','exec','-i','cygnusx-db','pg_restore','--list'],stdin=stream,capture_output=True,timeout=30)
        assert p.returncode==0 and b'TABLE DATA public memory_facts' in p.stdout
        limit=10 if phase=='dry' else 1
        result=await cli.run(dsn,storage='facts',mode='missing',limit=limit,apply=False)
        assert result['status']=='dry_run'
        if phase=='dry-tail': assert result['pending']<=1
        plan={'status':'dry_run','phase':phase,'database':'omichub','limit':limit,'pending':result['pending'],'planned_updates':min(limit,result['pending']),
            'target_model':result['target_model'],'dry_run':result,'backup_path':str(backup),'backup_size_bytes':backup.stat().st_size,
            'backup_sha256':hashlib.sha256(backup.read_bytes()).hexdigest(),'backup_toc_verified':True}
        c.save('backfill-plan.json',plan)
        report['latest_plan']=plan
        if phase=='dry':
            env=dict(os.environ);env['MEMORY_MAINTENANCE_DATABASE_URL']='postgresql+asyncpg://invalid:never_used@127.0.0.1:1/not_authorized'
            p=subprocess.run([sys.executable,'scripts/backfill_memory_embeddings.py','--apply','--confirm-database','omichub'],env=env,capture_output=True,text=True,timeout=15)
            outcome=json.loads(p.stdout)
            assert p.returncode==2 and outcome['error_type']=='ValueError'
            report['wrong_target_apply_guard']={'status':'passed','exit_code':p.returncode,'result':outcome,'protection':'independent target-name confirmation; rejected before connection and Provider construction','network_calls':0}
            report['initial_missing']=result['pending']
        report['status']='dry_run_ready'
        c.save('backfill.json',report)
        print(json.dumps({'phase':phase,'pending':plan['pending'],'planned_updates':plan['planned_updates'],'limit':limit,'backup_verified':True,'target_model':plan['target_model']}))
    elif phase in ('apply','apply-tail'):
        plan=json.loads(planfile.read_text())
        assert plan['phase']==('dry' if phase=='apply' else 'dry-tail')
        backup=Path(plan['backup_path'])
        assert backup.exists() and hashlib.sha256(backup.read_bytes()).hexdigest()==plan['backup_sha256']
        current=await cli.run(dsn,storage='facts',mode='missing',limit=plan['limit'],apply=False)
        assert current['pending']==plan['pending'] and current['target_model']==plan['target_model']
        result=await cli.run(dsn,storage='facts',mode='missing',limit=plan['limit'],apply=True,provider_id=UUID(c.get_settings().agent_memory_embedding_provider_id),confirm_database='omichub')
        assert result['status']=='completed' and result['failed']==0 and result['updated']==plan['planned_updates']
        report['batches'].append({'phase':phase,'result':result,'backup_path':str(backup),'dry_run_pending':plan['pending']})
        report['total_updated']=sum(x['result']['updated'] for x in report['batches'])
        report['status']='passed' if result['after']['pending']==0 else 'tail_pending'
        report['failed_rows']=[]
        c.save('backfill.json',report)
        print(json.dumps({'phase':phase,'updated':result['updated'],'failed':result['failed'],'remaining':result['after']['pending'],'coverage':result['after']['coverage']}))
    else: raise ValueError('Unknown phase')
    await c.engine.dispose()

try: asyncio.run(main())
except Exception as exc:
    print(json.dumps({'status':'failed','error_type':type(exc).__name__}))
    raise SystemExit(2)
