"""Explicit inactive-only, backed-up and dry-run-bound historical maintenance."""
import asyncio
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from uuid import UUID

import acceptance_common as c
from sqlalchemy import text

spec = importlib.util.spec_from_file_location('historical_cli', Path.cwd()/'scripts/backfill_memory_embeddings.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
STATES = ('archived', 'superseded')

async def snapshot():
    async with c.engine.connect() as db:
        rows = (await db.execute(text("""
            SELECT id, status, embedding IS NULL AS missing,
                   embedding_model, vector_dims(embedding) AS dimensions,
                   md5((to_jsonb(f)-'embedding'-'embedding_model')::text) AS unchanged
            FROM memory_facts f ORDER BY id
        """))).mappings().all()
    rows = [dict(r) for r in rows]
    fingerprints = [(r['id'], r['unchanged']) for r in rows]
    return rows, hashlib.sha256(json.dumps(fingerprints).encode()).hexdigest()

async def main():
    phase = sys.argv[1]
    assert phase in ('dry', 'apply')
    c.budget.STEP = 'historical_inactive_backfill'
    dsn = os.environ['MEMORY_MAINTENANCE_DATABASE_URL']
    rows, fingerprint = await snapshot()
    planfile = c.OUT/'historical-backfill-plan.json'
    if phase == 'dry':
        historical = [r for r in rows if r['status'] in STATES]
        assert len(historical) == 10 and all(r['missing'] for r in historical)
        root = Path(tempfile.mkdtemp(prefix='cygnusx-memory-historical-backup-'))
        os.chmod(root, 0o700)
        backup = root/'memory_facts.dump'
        with backup.open('wb') as stream:
            os.chmod(backup, 0o600)
            p = subprocess.run(['docker','exec','cygnusx-db','sh','-c',
                'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t public.memory_facts -Fc --no-owner --no-acl'],
                stdout=stream, stderr=subprocess.PIPE, timeout=60)
        assert p.returncode == 0 and backup.stat().st_size > 0
        with backup.open('rb') as stream:
            p = subprocess.run(['docker','exec','-i','cygnusx-db','pg_restore','--list'],
                stdin=stream, capture_output=True, timeout=30)
        assert p.returncode == 0 and b'TABLE DATA public memory_facts' in p.stdout
        result = await cli.run(dsn, storage='facts', mode='missing', limit=10,
            apply=False, statuses=STATES)
        assert result['status'] == 'dry_run' and result['pending'] == 10
        plan = {'status':'dry_run', 'database':'omichub', 'limit':10, 'planned_updates':10,
            'selection_statuses':list(STATES), 'state_counts':dict(Counter(r['status'] for r in historical)),
            'dry_run':result, 'unchanged_columns_fingerprint':fingerprint,
            'backup_path':str(backup), 'backup_size_bytes':backup.stat().st_size,
            'backup_sha256':hashlib.sha256(backup.read_bytes()).hexdigest(), 'backup_toc_verified':True,
            'preservation':'Every column except embedding and embedding_model; no status transitions'}
        c.save('historical-backfill-plan.json', plan)
        print(json.dumps({k:plan[k] for k in ('status','database','limit','planned_updates','selection_statuses','state_counts','backup_toc_verified')}))
    else:
        plan = json.loads(planfile.read_text())
        backup = Path(plan['backup_path'])
        assert hashlib.sha256(backup.read_bytes()).hexdigest() == plan['backup_sha256']
        assert fingerprint == plan['unchanged_columns_fingerprint']
        current = await cli.run(dsn, storage='facts', mode='missing', limit=10,
            apply=False, statuses=STATES)
        assert current == plan['dry_run']
        result = await cli.run(dsn, storage='facts', mode='missing', limit=10,
            apply=True, statuses=STATES, confirm_database='omichub',
            provider_id=UUID(c.get_settings().agent_memory_embedding_provider_id))
        assert result['updated'] == 10 and result['failed'] == result['skipped'] == result['remaining_pending'] == 0
        after, after_fingerprint = await snapshot()
        assert after_fingerprint == fingerprint
        assert len(after) == 11 and all(not r['missing'] and r['dimensions'] == 1024 and
            r['embedding_model'] == current['target_model'] for r in after)
        verification = {'status':'passed', 'result':result, 'backup_path':str(backup),
            'backup_sha256':plan['backup_sha256'], 'dry_run_plan':'historical-backfill-plan.json',
            'all_non_embedding_columns_unchanged':True,
            'final_state_counts':dict(Counter(r['status'] for r in after)),
            'all_rows':11, 'all_vectors_1024_and_correct_model':True, 'failed_rows':[]}
        c.save('historical-backfill.json', verification)
        report = json.loads((c.OUT/'backfill.json').read_text())
        report['status'] = 'passed'
        report['historical_backfill_status'] = 'passed'
        report['historical_batch'] = verification
        report['total_updated'] = sum(b['result']['updated'] for b in report['batches']) + result['updated']
        report['historical_scope_pending'] = False
        report['original_historical_requirement'] = '10 inactive NULL facts now have correct vectors; archived/superseded states and all other fields preserved'
        report['failed_rows'] = []
        c.save('backfill.json', report)
        print(json.dumps({'status':'passed','updated':10,'remaining_selected':0,'all_rows':11,
            'states_preserved':True,'all_non_embedding_columns_unchanged':True,'active_coverage':result['after']['coverage']}))
    await c.engine.dispose()

try:
    asyncio.run(main())
except Exception as exc:
    print(json.dumps({'status':'failed','error_type':type(exc).__name__}))
    raise SystemExit(2)
