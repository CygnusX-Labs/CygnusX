"""Common real-acceptance transport and accounting. Only explicit maintenance DSN."""
import json
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

OUT=Path(__file__).resolve().parent
load_dotenv(Path.cwd()/'.env',override=True)
assert os.environ.get('MEMORY_MAINTENANCE_DATABASE_URL'), 'Explicit maintenance DSN required'
url=make_url(os.environ['MEMORY_MAINTENANCE_DATABASE_URL'])
assert url.database=='omichub' and url.get_backend_name()=='postgresql'
if url.host=='db':
    info=json.loads(subprocess.check_output(['docker','inspect','cygnusx-db']))[0]
    bindings=info['NetworkSettings']['Ports']['5432/tcp']
    mapping=next(x for x in bindings if x['HostIp']=='127.0.0.1')
    url=url.set(host='127.0.0.1',port=int(mapping['HostPort']))
# All provider/session lookups deliberately use the same explicit maintenance target.
# No fallback to DATABASE_URL occurs. Only the Docker transport is mapped to loopback.
os.environ['MEMORY_MAINTENANCE_DATABASE_URL']=url.render_as_string(hide_password=False)
os.environ['DATABASE_URL']=url.render_as_string(hide_password=False)
os.environ['SERVICE_NAME']='memory_acceptance'
os.environ['OTEL_SDK_DISABLED']='false'
os.environ['TELEMETRY_ENABLED']='false'
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
metric_reader=InMemoryMetricReader()
metrics.set_meter_provider(MeterProvider(metric_readers=[metric_reader]))
from cygnusx.core.config import get_settings
get_settings.cache_clear()
from loguru import logger
logger.remove()
import logging
logging.disable(logging.CRITICAL)
import budget
budget.install_http_accounting()
from sqlalchemy.ext.asyncio import async_sessionmaker,create_async_engine
from sqlalchemy.pool import NullPool
engine=create_async_engine(url.set(drivername='postgresql+asyncpg'),echo=False,poolclass=NullPool)
factory=async_sessionmaker(engine,expire_on_commit=False)

def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False,default=str)+'\n')


def metric_snapshot():
    result=[]
    data=metric_reader.get_metrics_data()
    if data is None: return result
    for resource in data.resource_metrics:
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                if not metric.name.startswith('memory.'): continue
                for point in metric.data.data_points:
                    value=getattr(point,'value',None)
                    if value is None: value=getattr(point,'count',None)
                    result.append({'name':metric.name,'value':value,'attributes':dict(point.attributes or {})})
    return result
