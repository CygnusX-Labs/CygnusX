"""Read-only source acceptance probes: SQLite fixture, no broker/network."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from cygnusx.application.schemas.download import DownloadRequest
from cygnusx.infrastructure.database.models.task import TaskModel
from cygnusx.infrastructure.download import reliability
from tests.unit.test_download_s4b0_reliability import (
    download_env as download_env, env as env, imports as imports,
    registry as registry, sandbox_thread_wakeup as sandbox_thread_wakeup,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

async def test_sr02_exact_target_three_sequential_aliases(env):
    keys = ['s4-residual-a', 's4-residual-b', 's4-residual-c']
    responses = [await env.submit(str(env.owner), DownloadRequest(
        accession='SRR123', request_key=key), project_id=env.project) for key in keys]
    await env.db.commit()
    assert len({response.id for response in responses}) == 1
    row = await env.db.get(TaskModel, responses[0].id)
    expected = [reliability.intent_digest(str(env.owner), str(env.project),
        {'download_request_key': key}) for key in keys]
    assert row.parameters['_download_request_keys'] == expected
    assert row.id == responses[0].id
    print('SR02 exact target aliases=3 sequence preserved; NOT PG concurrency')

async def test_sr03_exact_105_union_and_disjoint_101_legacy(env):
    queued_ids, legacy_ids = {uuid4() for _ in range(105)}, {uuid4() for _ in range(101)}
    for task_id in queued_ids | legacy_ids:
        legacy = task_id in legacy_ids
        env.db.add(TaskModel(id=task_id, user_id=env.owner, flow_id='ebi_download',
            name='legacy' if legacy else 'queued', status='queued',
            parameters={} if legacy else {'_download_reliability': {'version': 1}},
            updated_at=datetime.now(UTC)-timedelta(hours=2 if legacy else 1)))
    await env.db.commit()
    batches = []
    for count in [100, 5, 0]:
        env.send.reset_mock()
        result = await reliability.reconcile_download_tasks(env.db)
        ids = [call.args[0] for call in env.send.call_args_list]
        assert result['dispatched'] == count == len(ids)
        assert len(set(ids)) == len(ids)
        batches.append(set(ids))
    first, second, third = batches
    assert first.isdisjoint(second) and not third
    assert first | second == {str(task_id) for task_id in queued_ids}
    assert (first | second).isdisjoint({str(task_id) for task_id in legacy_ids})
    print('SR03 batches=100+5+0 union=105 duplicate=0 legacy=101 excluded; ISOLATED')
