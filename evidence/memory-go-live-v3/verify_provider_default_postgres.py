"""Exercise old/new repositories on a disposable schema in the existing isolated PG."""
import asyncio
import json
import subprocess
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from cygnusx.infrastructure.database.models.ai_provider import AIProviderConfigModel
from cygnusx.infrastructure.database.repositories.ai_provider_repository import (
    SqlAlchemyAIProviderConfigRepository,
)

OUT = Path(__file__).resolve().parent


async def main():
    info = json.loads(subprocess.check_output(['docker', 'inspect', 'cygnusx-memory-stage0-postgres-1']))[0]
    env = dict(x.split('=',1) for x in info['Config']['Env'] if '=' in x)
    bindings = info['NetworkSettings']['Ports']['5432/tcp']
    port = next(x['HostPort'] for x in bindings if x['HostIp'] in ('127.0.0.1', '0.0.0.0'))
    url = URL.create('postgresql+asyncpg', username=env['POSTGRES_USER'], password=env['POSTGRES_PASSWORD'],
                     host='127.0.0.1', port=int(port), database='cygnusx_maint')
    schema = 'provider_switch_' + uuid4().hex[:12]
    engine = create_async_engine(url, echo=False, connect_args={'server_settings':{'search_path':schema+',public'}})
    report = {'database':'cygnusx_maint','schema':schema,'isolation':'existing disposable Stage 0 PostgreSQL; main business DB not used',
              'real_model_calls':0,'cleanup':'pending'}
    old_code = subprocess.check_output(['git', 'show', 'HEAD:src/cygnusx/infrastructure/database/repositories/ai_provider_repository.py'],text=True)
    namespace={'__name__':'provider_repository_before_wiring_fix'}
    exec(compile(old_code,'HEAD:ai_provider_repository.py','exec'),namespace)
    old_repository=namespace['SqlAlchemyAIProviderConfigRepository']
    new_id=UUID('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa')
    old_id=UUID('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb')
    try:
        async with engine.begin() as conn:
            await conn.execute(text('CREATE SCHEMA '+schema))
            await conn.run_sync(AIProviderConfigModel.__table__.create)
            await conn.execute(text('CREATE UNIQUE INDEX uq_ai_provider_configs_default ON ai_provider_configs (is_default) WHERE is_default = TRUE'))
        async with AsyncSession(engine) as db:
            db.add_all([
                AIProviderConfigModel(id=new_id,name='synthetic-new',model='synthetic',is_default=False),
                AIProviderConfigModel(id=old_id,name='synthetic-old',model='synthetic',is_default=True,is_active=False),
            ])
            await db.commit()
        async with AsyncSession(engine) as db:
            try:
                await old_repository(db).set_default(new_id)
                await db.commit()
                report['before']='unexpected_success'
            except IntegrityError:
                await db.rollback()
                report['before']='IntegrityError reproduced on actual partial unique index'
        async with AsyncSession(engine) as db:
            await SqlAlchemyAIProviderConfigRepository(db).set_default(new_id)
            await db.commit()
            await SqlAlchemyAIProviderConfigRepository(db).set_default(new_id)
            await db.commit()
        async with AsyncSession(engine) as db:
            defaults=(await db.execute(text('SELECT id FROM ai_provider_configs WHERE is_default'))).scalars().all()
            old_active=await db.scalar(text('SELECT is_active FROM ai_provider_configs WHERE id=:id'),{'id':old_id})
            assert defaults==[new_id] and old_active is False
        assert report['before'].startswith('IntegrityError')
        report.update(after='passed',single_default=True,old_active_unchanged=True,repeated_sync='passed')
    finally:
        async with engine.begin() as conn:
            await conn.execute(text('DROP SCHEMA IF EXISTS '+schema+' CASCADE'))
        async with engine.connect() as conn:
            remaining=await conn.scalar(text('SELECT count(*) FROM pg_namespace WHERE nspname=:schema'),{'schema':schema})
            assert remaining==0
        report['cleanup']='verified schema absent'
        await engine.dispose()
        (OUT/'provider-default-postgres.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


asyncio.run(main())
