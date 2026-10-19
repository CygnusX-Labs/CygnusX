import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import redis.asyncio as redis

from cygnusx.application.services import research_data_service as service

URL = 'redis://127.0.0.1:32768/0'

async def worker():
    client = redis.from_url(URL, decode_responses=True)
    grants = []
    original_eval = client.eval
    async def observed_eval(*args):
        delay = await original_eval(*args)
        if int(delay) == 0:
            scores = await client.zrange('provider-rate:string:v12-5', 0, -1, withscores=True)
            grants.append({'redis_grant_ms': int(scores[0][1]), 'pid': os.getpid()})
        return delay
    client.eval = observed_eval
    service.get_redis = lambda: client
    try:
        for _ in range(2):
            await asyncio.wait_for(service._string_rate_limit(), timeout=20)
        return grants
    finally:
        await client.aclose()

async def main():
    client = redis.from_url(URL, decode_responses=True)
    assert await client.ping()
    await client.delete('provider-rate:string:v12-5')
    processes = [await asyncio.create_subprocess_exec(sys.executable, __file__, '--worker', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE) for _ in range(4)]
    outputs = await asyncio.gather(*(p.communicate() for p in processes))
    grants = []
    for p, (out, err) in zip(processes, outputs):
        if p.returncode:
            raise RuntimeError(err.decode())
        grants.extend(json.loads(out))
    grants.sort(key=lambda x: x['redis_grant_ms'])
    intervals = [b['redis_grant_ms'] - a['redis_grant_ms'] for a,b in zip(grants, grants[1:])]
    assert len(grants) == 8 and len({g['pid'] for g in grants}) == 4
    assert min(intervals) >= 1000, intervals
    await client.delete('provider-rate:string:v12-5')
    await client.aclose()
    subprocess.run(['docker', 'stop', 'cygnusx-mcp-string-rate-check-20261019'], check=True, stdout=subprocess.DEVNULL)
    failed_client = redis.from_url(URL, socket_connect_timeout=1, socket_timeout=1)
    service.get_redis = lambda: failed_client
    result = await service.execute_research('cygnusx_string_resolve', {'identifier':'TP53', 'taxon_id':9606, 'limit':1})
    await failed_client.aclose()
    assert result['success'] is False and 'ConnectionError' in result['summary'], result
    evidence = {'captured_at_utc':datetime.now(UTC).isoformat(), 'scope':'real isolated Redis, four independent OS processes calling production _string_rate_limit; no provider HTTP request', 'workers':4, 'grants_per_worker':2, 'grants':grants, 'intervals_ms':intervals, 'minimum_interval_ms':min(intervals), 'shared_rate_limit_passed':True, 'redis_unavailable_service_success':result['success'], 'redis_unavailable_error_class':'ConnectionError', 'provider_calls':0, 'production_services_touched':False, 'temporary_container_removed':True, 'limitations':['Limiter admission timestamps only; not an authenticated platform REST or MCP wire test.', 'Does not prove scheduling delay between limiter admission and HTTP request start.']}
    Path('evidence/mcp-external-validation-2026-10-18/string-redis-multiprocess-2026-10-19.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(evidence))

if __name__ == '__main__':
    print(json.dumps(asyncio.run(worker()))) if '--worker' in sys.argv else asyncio.run(main())
