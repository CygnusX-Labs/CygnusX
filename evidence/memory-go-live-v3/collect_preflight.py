"""Read-only Step 0 evidence; no Provider requests, writes, or maintenance DSN fallback."""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
KEYS = (
    'AGENT_MEMORY_EMBEDDING_MODEL',
    'AGENT_MEMORY_EMBEDDING_PROVIDER_ID',
    'AGENT_MEMORY_EMBEDDING_DIMENSIONS',
    'SILICONFLOW_API_KEY',
    'MEMORY_MAINTENANCE_DATABASE_URL',
)
INNER = r'''
import asyncio, json, os
from pathlib import Path
from uuid import UUID

keys = json.loads(os.environ['PREFLIGHT_KEY_NAMES'])
process_env = dict(
    part.split('=', 1)
    for part in Path('/proc/1/environ').read_bytes().decode().split('\0')
    if '=' in part
)
os.environ.clear()
os.environ.update(process_env)
os.chdir(os.readlink('/proc/1/cwd'))
result = {
    'pid': 1,
    'inspector_uid': os.getuid(),
    'comm': Path('/proc/1/comm').read_text().strip(),
    'env_key_presence': {key: bool(process_env.get(key, '').strip()) for key in keys},
    'settings_evidence': 'Settings reloaded in separate interpreter with PID 1 environment and cwd; not live object introspection',
    'env_file_exists_in_process_cwd': Path('.env').exists(),
}
try:
    from cygnusx.core.config import get_settings
    settings = get_settings()
    model = settings.agent_memory_embedding_model
    provider_id = settings.agent_memory_embedding_provider_id
    try:
        UUID(provider_id)
        uuid_valid = True
    except (ValueError, TypeError, AttributeError):
        uuid_valid = False
    result['settings'] = {
        'model': model,
        'provider_id': provider_id if uuid_valid else None,
        'provider_id_present': bool(provider_id),
        'provider_id_valid_uuid': uuid_valid,
        'dimensions': settings.agent_memory_embedding_dimensions,
    }
    result['settings_prerequisites_pass'] = bool(model and uuid_valid and settings.agent_memory_embedding_dimensions == 1024)
    async def inspect_provider():
        from sqlalchemy import text
        from sqlalchemy.engine import make_url
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool
        # Business DSN is used ONLY for a read-only Provider SELECT, never maintenance.
        engine = create_async_engine(
            make_url(settings.database_url).set(drivername='postgresql+asyncpg'),
            echo=False, poolclass=NullPool, connect_args={'timeout': 10},
        )
        try:
            async with engine.connect() as conn:
                await conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
                await conn.execute(text("SET LOCAL statement_timeout = '10s'"))
                await conn.execute(text("SET LOCAL lock_timeout = '2s'"))
                readonly = await conn.scalar(text('SHOW transaction_read_only'))
                selected = None
                if uuid_valid:
                    selected = (await conn.execute(text(
                        'SELECT id, name, model, is_active, is_default FROM ai_provider_configs WHERE id = :id'
                    ), {'id': UUID(provider_id)})).mappings().one_or_none()
                candidates = (await conn.execute(text(
                    'SELECT id, name, model, is_active, is_default FROM ai_provider_configs WHERE name = :name'
                ), {'name': 'provider-embedding-qwen3'})).mappings().all()
                return {
                    'transaction_read_only': readonly,
                    'selected_provider': dict(selected) if selected else None,
                    'yaml_named_candidates': [dict(row) for row in candidates],
                    'selected_provider_pass': bool(selected and selected['is_active'] and not selected['is_default']),
                    'scope': 'Provider metadata only; no memory/user content or credentials queried',
                }
        finally:
            await engine.dispose()
    try:
        result['database'] = asyncio.run(inspect_provider())
    except Exception as exc:
        result['database'] = {'status': 'unverified', 'error_type': type(exc).__name__}
except Exception as exc:
    result['settings_error_type'] = type(exc).__name__
print('PREFLIGHT_JSON:' + json.dumps(result, default=str))
'''


def collect() -> dict:
    from dotenv import dotenv_values

    sources = {'host_process': {key: bool(os.getenv(key, '').strip()) for key in KEYS}}
    for filename in ('.env', '.env.test'):
        path = Path.cwd() / filename
        values = dotenv_values(path) if path.exists() else {}
        sources[filename] = {key: bool(str(values.get(key) or '').strip()) for key in KEYS}
    report = {
        'captured_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'blocked',
        'scope': 'Step 0 only; stop before Steps 1-7 if any prerequisite fails',
        'local_key_presence_only': sources,
        'containers': [],
        'blockers': [],
        'real_calls': {'embedding': 0, 'extraction': 0},
        'database_mutations': 0,
        'production_defaults_modified': False,
    }
    for name in ('cygnusx-web', 'cygnusx-worker'):
        inspected = subprocess.run(['docker', 'inspect', name], capture_output=True, text=True)
        if inspected.returncode:
            report['blockers'].append(name + ': container inspect failed')
            continue
        info = json.loads(inspected.stdout)[0]
        entry = {
            'name': name,
            'started_at': info['State']['StartedAt'],
            'running': info['State']['Running'],
            'health': info['State'].get('Health', {}).get('Status'),
            'compose_service': info['Config']['Labels'].get('com.docker.compose.service'),
            'compose_config_files': info['Config']['Labels'].get('com.docker.compose.project.config_files'),
        }
        uid_probe = subprocess.run(
            ['docker', 'exec', name, 'python', '-c',
             "from pathlib import Path; print(next(s.split()[1] for s in Path('/proc/1/status').read_text().splitlines() if s.startswith('Uid:')))"],
            capture_output=True, text=True, timeout=10,
        )
        process_uid = uid_probe.stdout.strip()
        if not process_uid.isdigit():
            report['blockers'].append(name + ': could not determine process UID')
            report['containers'].append(entry)
            continue
        exec_user = ['--user', process_uid] if name == 'cygnusx-worker' else []
        proc = subprocess.run(
            ['docker', 'exec', *exec_user, '-i', '-e', 'PREFLIGHT_KEY_NAMES=' + json.dumps(KEYS), name, 'python', '-'],
            input=INNER, capture_output=True, text=True, timeout=45,
        )
        lines = [s for s in proc.stdout.splitlines() if s.startswith('PREFLIGHT_JSON:')]
        if proc.returncode or not lines:
            entry['process_check'] = {'status': 'unverified', 'exit_code': proc.returncode}
            report['blockers'].append(name + ': process Settings/Provider inspection failed')
        else:
            entry['process_check'] = json.loads(lines[-1].split(':', 1)[1])
            check = entry['process_check']
            if not check.get('settings_prerequisites_pass'):
                report['blockers'].append(name + ': process-derived embedding Settings incomplete or invalid')
            if not check['env_key_presence']['SILICONFLOW_API_KEY']:
                report['blockers'].append(name + ': SILICONFLOW_API_KEY absent from PID 1 environment')
            if not check.get('database', {}).get('selected_provider_pass'):
                report['blockers'].append(name + ': configured UUID Provider active/non-default not proven')
        logs = subprocess.run(
            ['docker', 'logs', '--timestamps', '--since', info['State']['StartedAt'], name],
            capture_output=True, text=True, timeout=30,
        )
        all_lines = (logs.stdout + '\n' + logs.stderr).splitlines()
        embedding_lines = [line for line in all_lines if re.search(r'embedding', line, re.I)]
        errors = [line for line in embedding_lines if re.search(r'\berror\b|\bcritical\b|\bfatal\b', line, re.I)]
        entry['startup_logs'] = {
            'exit_code': logs.returncode,
            'since': info['State']['StartedAt'],
            'lines_scanned': len(all_lines),
            'embedding_lines': len(embedding_lines),
            'embedding_error_lines': len(errors),
            'raw_logs_retained': False,
            'no_embedding_error': logs.returncode == 0 and not errors,
            'limitation': 'Docker-retained logs since current container start; absence of errors does not prove configuration enabled',
        }
        if logs.returncode or errors:
            report['blockers'].append(name + ': embedding ERROR present or logs unavailable')
        report['containers'].append(entry)
    maintenance_visible = any(s['MEMORY_MAINTENANCE_DATABASE_URL'] for s in sources.values()) or any(
        c.get('process_check', {}).get('env_key_presence', {}).get('MEMORY_MAINTENANCE_DATABASE_URL', False)
        for c in report['containers']
    )
    report['maintenance_dsn_visible'] = maintenance_visible
    if not maintenance_visible:
        report['blockers'].append('Explicit MEMORY_MAINTENANCE_DATABASE_URL absent from checked sources; no DATABASE_URL fallback')
    report['status'] = 'passed' if not report['blockers'] else 'blocked'
    return report


if __name__ == '__main__':
    result = collect()
    OUT.joinpath('preflight.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'blockers': result['blockers'], 'real_calls': result['real_calls']}, ensure_ascii=False))
    raise SystemExit(0 if result['status'] == 'passed' else 2)
